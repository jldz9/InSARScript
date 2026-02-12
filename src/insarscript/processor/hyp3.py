import json
import netrc
import os
import sys
import time
import getpass
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asf_search.exceptions import ASFSearchError
from asf_search import ASFProduct
from collections import defaultdict
from colorama import Fore, Style
from dateutil.parser import isoparse
from hyp3_sdk import HyP3, Batch, Job
from hyp3_sdk.exceptions import AuthenticationError, HyP3Error
from tqdm import tqdm


from insarscript.core import Hyp3Processor, Hyp3_InSAR_Base_Config


class Hyp3_InSAR(Hyp3Processor):
    name = "Hyp3_InSAR"
    default_config = Hyp3_InSAR_Base_Config

    def __init__(self, config=None):
        super().__init__(config)
        self._hyp3_authorize(pool=self.config.earthdata_credentials_pool)
        self.cost = self.client.costs()['INSAR_GAMMA']['cost_table'][f'{self.config.looks}']
        if self.config.saved_job_path is not None:
            print(f"{Fore.GREEN}Loading job IDs from {self.config.saved_job_path}...\n")
            job_path = Path(self.config.saved_job_path).expanduser().resolve()
            if job_path.is_file():  
                data = json.loads(job_path.read_text())
                self.job_ids = defaultdict(list, data.get("job_ids", {}))
                
                if not self.job_ids:
                    raise ValueError(f"{Fore.RED}No job found in {self.config.saved_job_path}. Either the job file is empty or the path is incorrect.\n")
                self.output_dir = Path(data.get("out_dir", self.config.output_dir)).expanduser().resolve()
            else:
                raise ValueError(f"{Fore.RED}Job file {self.config.saved_job_path} not found. Please check the path and try again.\n")
        else:
            self.job_ids = defaultdict(list)
            self.output_dir = Path(self.config.output_dir).expanduser().resolve()

    def _hyp3_authorize(self, pool: dict[str, str] | None = None):
        """Authorize the HyP3 client.
        param pool: A dictionary containing a pool of Earthdata credentials with format {'username': 'passowrd'}
        """
        self._has_asf_netrc = self._check_netrc(keyword='machine urs.earthdata.nasa.gov')
        if not self._has_asf_netrc:
            while True:
                self._username = input("Enter your ASF username: ")
                self._password = getpass.getpass("Enter your ASF password: ")
                try:
                    self.client = HyP3(username=self._username, password=self._password)
                except AuthenticationError:
                    print(f"{Fore.RED}Authentication failed. Please check your credentials and try again.\n")
                    continue
                print(f"{Fore.GREEN}Authentication successful.\n")
                netrc_path = Path.home().joinpath(".netrc")
                hyp3_entry = f"\nmachine urs.earthdata.nasa.gov\n    login {self._username}\n    password {self._password}\n"
                with open(netrc_path, 'a') as f:
                    f.write(hyp3_entry)
                print(f"{Fore.GREEN}Credentials saved to {netrc_path}.\n")
                break
        else:
            self.client = HyP3()
            self._username,_,self._password = netrc.netrc(Path.home().joinpath(".netrc")).authenticators('urs.earthdata.nasa.gov')
        if pool is not None and isinstance(pool, dict) and len(pool) > 0:
            self._username_pool = list(pool.keys())
            self._password_pool = list(pool.values())
            self._username_pool.insert(0, self._username)
            self._password_pool.insert(0, self._password)
            self._auth_pool = True
            self._user_index = 0
        else:
            self._auth_pool = False
            self._username_pool = [self._username]
            self._password_pool = [self._password]
            self._user_index = 0

    def _check_netrc(self, keyword: str) -> bool:
        """Check if .netrc file exists in the home directory."""
        netrc_path = Path.home().joinpath('.netrc')
        if not netrc_path.is_file():            
            print(f"{Fore.RED}No .netrc file found in your home directory. Will prompt login.\n")
            return False
        else: 
            with netrc_path.open() as f:
                content = f.read()
                if keyword in content:
                    return True
                else:
                    print(f"{Fore.RED}no machine name {keyword} found .netrc file. Will prompt login.\n")
                    return False
    
    def _submit_job_queue(self, job_queue: list[dict]):
        """
        Job submit helper.
        """
        
        batchs = defaultdict(list)
        self.job_ids = defaultdict(list)
        total_jobs = len(job_queue)
        with tqdm(total=total_jobs, desc="Submitting jobs", unit="job") as pbar:
            while job_queue:
                username = self._username_pool[self._user_index]
                credits = self.client.check_credits()
                max_jobs_allowed = credits // self.cost

                if max_jobs_allowed > 0:
                    chunk_size = min(max_jobs_allowed, len(job_queue), 200)
                    jobs_to_submit = job_queue[:chunk_size]
                    print(f"{Fore.GREEN}User {username}: Submitting {len(jobs_to_submit)} jobs")
                    batch = self.client.submit_prepared_jobs(jobs_to_submit)
                    batchs[username].extend(batch)
                    for j in batch:
                        self.job_ids[username].append(j.job_id)
                    job_queue = job_queue[chunk_size:]

                elif job_queue:
                    if self._auth_pool and (self._user_index + 1 < len(self._username_pool)):
                        print(f"{Fore.YELLOW}User {username} exhausted. Switching to next account...")
                        self._user_index += 1
                        for retry in range(3):
                            try:
                                self.client = HyP3(username=self._username_pool[self._user_index], 
                                                password=self._password_pool[self._user_index])
                                break
                            except AuthenticationError:
                                print(f"{Fore.RED}Auth failed for {self._username_pool[self._user_index]}, retrying...")
                                continue
                    else:
                        print(f"{Fore.RED}All accounts exhausted. {len(job_queue)} jobs remain.")
                        sys.exit(1)
             
        print(f"{Fore.GREEN}All jobs submitted successfully.")
        self.batchs = batchs
        return batchs
    
    def check_credits(self):
        """Check remaining credits for the current user."""
        if self._auth_pool:
            for i, username in enumerate(self._username_pool):
                try:
                    self.client = HyP3(username=username, password=self._password_pool[i])
                    credits = self.client.check_credits()
                    print(f"{Fore.CYAN}Remaining credits for {username}: {credits}{Fore.RESET}")
                except AuthenticationError:
                    print(f"{Fore.RED}Authentication failed for {username}. Skipping...{Fore.RESET}")
        else:
            credits = self.client.check_credits()
            print(f"{Fore.CYAN}Remaining credits for {self._username_pool[self._user_index]}: {credits}{Fore.RESET}")
    
    def submit(self):
        """Submit InSAR jobs to HyP3 based on the provided configuration."""
        if isinstance(self.config.pairs, (list, tuple)) and all(isinstance(p, str) for p in self.config.pairs):
                pairs = [(self.config.pairs[0], self.config.pairs[1])]
        elif isinstance(self.config.pairs, (list, tuple)) and all(isinstance(p, tuple) for p in self.config.pairs):
            pairs = self.config.pairs
        else:
            raise ValueError(f"{Fore.RED}Invalid pairs format. Please provide a list of tuples or a tuple of two strings.\n")
        
        job_queue: list[dict] = []
        
        for (ref_id, sec_id) in pairs:
            job = self.client.prepare_insar_job(
                granule1=ref_id,
                granule2=sec_id,
                name= f"{self.config.name_prefix}_{ref_id.split('_')[5]}_{sec_id.split('_')[5]}",
                include_look_vectors=self.config.include_look_vectors,
                include_inc_map = self.config.include_inc_map,
                looks = self.config.looks,
                include_dem=self.config.include_dem,
                include_wrapped_phase=self.config.include_wrapped_phase,
                apply_water_mask=self.config.apply_water_mask,
                include_displacement_maps=self.config.include_displacement_maps,
                phase_filter_parameter=self.config.phase_filter_parameter
            )
            
            job_queue.append(job)
        batchs = self._submit_job_queue(job_queue)
        self.batchs = batchs
        return batchs

    def refresh(self):
        """Refresh job statuses from HyP3 for the provided batch or the stored job_ids."""
        user_job_map = defaultdict(list)
        if hasattr(self, 'batchs') and self.batchs:
            for username, jobs in self.batchs.items():
                user_job_map[username] = [j.job_id for j in jobs]
        elif self.job_ids:
            user_job_map = self.job_ids
        else:
            raise ValueError(f"{Fore.RED}No jobs found. Call submit() or load() first.")
                
        refreshed_batchs = defaultdict(Batch)
        self.failed_jobs = []
        for username, data in user_job_map.items():
            if not data:
                continue

            print(f"{Fore.CYAN}{Style.BRIGHT}User: {username} ({len(data)} jobs){Style.RESET_ALL}")
            try: 
                password = self._password_pool[self._username_pool.index(username)]
                self.client = HyP3(username=username, password=password)
                if isinstance(data[0], Job):
                    batch_to_refresh = Batch(data)
                    updated_batch = self.client.refresh(batch_to_refresh)
                else:
                    start_date = datetime.now(timezone.utc) - timedelta(days=20) # Hyp3 won't preserve job for more than 14 days, so we set 20 days to be safe and not collect all jobs to slow down API
                    skeleton_jobs = self.client.find_jobs(start=start_date)
                    updated_batch = Batch([job for job in skeleton_jobs if job.job_id in data])
                refreshed_batchs[username] = updated_batch
                failures = [job for job in updated_batch.jobs if job.status_code == "FAILED"]
                self.failed_jobs.extend(failures)
                #TODO might need to figure out auto align title with job status in future for different Job name and job id
                print(f"\n{Style.BRIGHT}{'  ' :<3} {'JOB NAME':<{35}} {'JOB ID':<{37}}  {'STATUS'}{Style.RESET_ALL}")
                for job in updated_batch:
                    color = Fore.GREEN if job.status_code == 'SUCCEEDED' else \
                            Fore.RED if job.status_code == 'FAILED' else Fore.YELLOW
                    
                    print(f"  - {job.name:<35} {job.job_id:<12} | {color}{job.status_code}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Failed to refresh {username}: {e}{Style.RESET_ALL}")
                continue
            self.batchs = refreshed_batchs
        return refreshed_batchs
    
    def retry(self):
        if not hasattr(self, 'failed_jobs') or not self.failed_jobs:
            print(f"{Fore.CYAN}No failed jobs in memory. Refreshing status...{Fore.RESET}")
            self.refresh()
        if not self.failed_jobs:
            print(f"{Fore.GREEN}No failed jobs to retry.{Fore.RESET}")
            return
        
        job_queue = []
        for job in self.failed_jobs:
            prepared_dict = {
            'job_type': job.job_type,
            'job_parameters': job.job_parameters,
            'name': job.name
        }
            job_queue.append(prepared_dict)
        print(f"{Fore.YELLOW}Attempting to resubmit {len(job_queue)} failed jobs...{Fore.RESET}")

        results = self._submit_job_queue(job_queue)
        retry_filename = 'hyp3_retry_jobs.json'
        retry_path = self.output_dir/ retry_filename
        if retry_path.exists():
                ts = time.strftime("%Y%m%dt%H%M%S")
                retry_path = self.output_dir / f'hyp3_retry_jobs_{ts}.json'
                print(f"{Fore.YELLOW}Existing retry file found, saving to {retry_path.name}")

        self.save(retry_path)
        return results
    
    def save(self, save_path: Path | str | None = None):
        """persistence (resume later)"""
        if hasattr(self, 'batchs') and self.batchs:
            job_ids_to_save = {user: [job.job_id for job in batch] for user, batch in self.batchs.items()}
            if save_path is None:
                path : Path = self.output_dir.joinpath('hyp3_jobs.json')
            else:
                path : Path = Path(save_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                path.unlink()
            payload = {"job_ids": job_ids_to_save, "out_dir": self.output_dir.as_posix()}
            with open(path, 'w') as f:
                json.dump(payload, f, indent=2)
            print(f'Batch file saved under {path}, you may resume later by loading this file path in to saved_job_path.')
            return path
        else:
            raise ValueError(f'No batchs exist to save, did you submitted or refreshed a job?')
    
    def download(self):
        """Download completed products for the provided batch or the stored job_ids."""
        if not hasattr(self, 'batchs'):
            self.batchs = self.refresh()
            if not self.batchs:
                raise ValueError(f"{Fore.RED}No jobs found. Call submit or load jobs first.")
        # Check duplicate downlaod 
        exist_files = list(self.output_dir.glob('*.zip'))
        exist_name = [p.name for p in exist_files]
        for username, batch in self.batchs.items():
            print(f"{Fore.CYAN}{Style.BRIGHT}User: {username} ({len(batch)} jobs){Style.RESET_ALL}")
            succeeded = [job for job in batch.jobs if job.status_code == "SUCCEEDED"]
            if len(succeeded) > 0:
                for job in tqdm(succeeded, desc="Downloading:", position=0):
                    if all(j['filename'] in exist_name for j in job.files):
                        print(f'{Fore.YELLOW}{job.name} exist under {self.output_dir}, will skip download')
                        continue
                    self.client = HyP3(username=username, password=self._password_pool[self._username_pool.index(username)])    
                    job.download_files(location=str(self.output_dir))
            else:
                print(f'{Fore.YELLOW}No succeeded jobs found for {username}, will skip download')
        return self.output_dir
    
    def watch(self, refresh_interval: int = 300):
        """Continuously watch job status and download when completed."""
        print(f"{Fore.GREEN}Watching job status every {refresh_interval} seconds. Press Ctrl+C to stop.{Fore.RESET}")
        
        try:
            while True:
                with open(os.devnull, 'w') as f, redirect_stdout(f):
                    self.refresh()
                    self.download()
                total_jobs = 0
                active_jobs = 0
                failed_jobs = 0
                succeeded_jobs = 0
                time.sleep(refresh_interval)
                for username, batch in self.batchs.items():
                    total_jobs += len(batch)
                    active_jobs += len(batch.filter_jobs(status_code=['RUNNING', 'PENDING']))
                    failed_jobs += len(batch.filter_jobs(status_code='FAILED'))
                    succeeded_jobs += len(batch.filter_jobs(status_code='SUCCEEDED'))
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Progress: {Fore.CYAN}{succeeded_jobs}/{total_jobs} Done{Fore.RESET} | "
                    f"{Fore.YELLOW}{active_jobs} Running{Fore.RESET} | "
                    f"{Fore.RED}{failed_jobs} Failed{Fore.RESET}", end='\r')

                if active_jobs == 0:
                    print(f"\n{Fore.GREEN}All jobs processed!{Fore.RESET}")
                    break

                time.sleep(refresh_interval)
        except KeyboardInterrupt:
            print(f"{Fore.YELLOW}Stopped watching by user.{Fore.RESET}")