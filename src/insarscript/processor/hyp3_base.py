import json
import netrc
import os
import requests
import sys
import time
import threading
import getpass
import zipfile  
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collections import defaultdict
from colorama import Fore, Style
from dateutil.parser import isoparse
from hyp3_sdk import HyP3, Batch, Job
from hyp3_sdk.exceptions import AuthenticationError, HyP3Error
from tqdm import tqdm

from insarscript.core import Hyp3Processor, Hyp3_Base_Config


class Hyp3Base(Hyp3Processor):
    """
    Base class for HyP3 interactions. 
    Handles Authentication, Job Submission Logic (Queueing/Credits), 
    Monitoring, Downloading, and Persistence.
    """
    default_config = Hyp3_Base_Config
    
    def __init__(self, config: Hyp3_Base_Config | None = None):
        super().__init__(config)
        self.config = config
        self._current_client_user = None 
        self._hyp3_authorize(pool=self.config.earthdata_credentials_pool)
        
        
        # 1. Load Saved Jobs
        if self.config.saved_job_path is not None:
            print(f"{Fore.GREEN}Loading job IDs from {self.config.saved_job_path}...\n")
            job_path = Path(self.config.saved_job_path)
            if job_path.is_file():  
                data = json.loads(job_path.read_text())
                self.job_ids = defaultdict(list, data.get("job_ids", {}))
                
                if not self.job_ids:
                    raise ValueError(f"{Fore.RED}No job found in {self.config.saved_job_path}.\n")
                
                # Update output_dir from save file if present, else use config
                saved_out = data.get("out_dir")
                self.output_dir = Path(saved_out).resolve() if saved_out else self.config.output_dir
            else:
                raise ValueError(f"{Fore.RED}Job file {self.config.saved_job_path} not found.\n")
        else:
            self.job_ids = defaultdict(list)
            self.output_dir = self.config.output_dir

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.batchs = defaultdict(list)
        self.failed_jobs = []
        self.cost = 1 # Default cost, override in subclass

    def _hyp3_authorize(self, pool: dict[str, str] | None = None):
        """Authorize the HyP3 client."""
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
            self._username, _, self._password = netrc.netrc(Path.home().joinpath(".netrc")).authenticators('urs.earthdata.nasa.gov')
        
        self._current_client_user = self._username
        
        if pool and len(pool) > 0:
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
        netrc_path = Path.home().joinpath('.netrc')
        if not netrc_path.is_file():            
            print(f"{Fore.RED}No .netrc file found. Will prompt login.\n")
            return False
        with netrc_path.open() as f:
            if keyword in f.read():
                return True
            print(f"{Fore.RED}No machine name {keyword} found in .netrc. Will prompt login.\n")
            return False
    
    def _submit_job_queue(self, job_queue: list[dict]):
        """
        Generic submitter. Takes a list of prepared job dictionaries and handles
        credit checking, batching, and user rotation.
        """
        batchs = defaultdict(list)
        self.job_ids = defaultdict(list)
        total_jobs = len(job_queue)
        
        with tqdm(total=total_jobs, desc="Submitting jobs", unit="job") as pbar:
            while job_queue:
                username = self._username_pool[self._user_index]
                
                # Ensure client matches current pool user
                if  self._current_client_user != username:
                    self.client = HyP3(username=username, password=self._password_pool[self._user_index])
                    self._current_client_user = username

                try:
                    credits = self.client.check_credits()
                except Exception as e:
                    pbar.write(f"{Fore.RED}Error checking credits for {username}: {e}")
                    credits = 0

                max_jobs_allowed = int(credits // self.cost)

                if max_jobs_allowed > 0:
                    chunk_size = min(max_jobs_allowed, len(job_queue), self.config.submission_chunk_size)
                    jobs_to_submit = job_queue[:chunk_size]

                    pbar.write(f"{Fore.GREEN}User {username}: Submitting {len(jobs_to_submit)} jobs")

                    try:
                        batch = self.client.submit_prepared_jobs(jobs_to_submit)
                        batchs[username].extend(batch)
                        for j in batch:
                            self.job_ids[username].append(j.job_id)
                        
                        job_queue = job_queue[chunk_size:]
                        pbar.update(chunk_size)
                    except HyP3Error as e:
                         pbar.write(f"{Fore.RED}Submission failed for {username}: {e}")
                         max_jobs_allowed = 0 # Force switch

                # If queue still exists but user is out of credits/failed
                if job_queue and max_jobs_allowed <= 0:
                    if self._auth_pool and (self._user_index + 1 < len(self._username_pool)):
                        pbar.write(f"{Fore.YELLOW}User {username} exhausted. Switching account...")
                        self._user_index += 1
                        # Retry auth for next user
                        for _ in range(3):
                            try:
                                _u_next = self._username_pool[self._user_index]
                                _p_next = self._password_pool[self._user_index]
                                self.client = HyP3(username=_u_next, password=_p_next)
                                self._current_client_user = _u_next
                                break
                            except AuthenticationError:
                                pbar.write(f"{Fore.RED}Auth failed for {self._username_pool[self._user_index]}, retrying...")
                                continue
                    else:
                        pbar.write(f"{Fore.RED}All accounts exhausted. {len(job_queue)} jobs remain.")
                        # Save remaining to avoid total loss?
                        sys.exit(1)
             
        print(f"{Fore.GREEN}All jobs submitted successfully.")
        self.batchs = batchs
        return batchs
    
    def check_credits(self):
        """Check remaining credits for all users."""
        if self._auth_pool:
            for i, username in enumerate(self._username_pool):
                try:
                    tmp_client = HyP3(username=username, password=self._password_pool[i])
                    credits = tmp_client.check_credits()
                    print(f"{Fore.CYAN}Remaining credits for {username}: {credits}{Fore.RESET}")
                except AuthenticationError:
                    print(f"{Fore.RED}Authentication failed for {username}. Skipping...{Fore.RESET}")
        else:
            credits = self.client.check_credits()
            print(f"{Fore.CYAN}Remaining credits for {self._username_pool[self._user_index]}: {credits}{Fore.RESET}")
    
    def refresh(self):
        """Refresh job statuses."""
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
                    start_date = datetime.now(timezone.utc) - timedelta(days=20) 
                    skeleton_jobs = self.client.find_jobs(start=start_date)
                    updated_batch = Batch([job for job in skeleton_jobs if job.job_id in data])
                
                refreshed_batchs[username] = updated_batch
                failures = [job for job in updated_batch.jobs if job.status_code == "FAILED"]
                self.failed_jobs.extend(failures)
                
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
            # Reconstruct job dict from failed job object
            prepared_dict = {
                'job_type': job.job_type,
                'job_parameters': job.job_parameters,
                'name': job.name
            }
            job_queue.append(prepared_dict)
        print(f"{Fore.YELLOW}Attempting to resubmit {len(job_queue)} failed jobs...{Fore.RESET}")

        results = self._submit_job_queue(job_queue)
        
        ts = time.strftime("%Y%m%dt%H%M%S")
        retry_path = self.output_dir / f'hyp3_retry_jobs_{ts}.json'
        self.save(retry_path)
        return results
    
    def save(self, save_path: Path | str | None = None):
        if hasattr(self, 'batchs') and self.batchs:
            job_ids_to_save = {user: [job.job_id for job in batch] for user, batch in self.batchs.items()}
            
            if save_path is None:
                path = self.output_dir.joinpath('hyp3_jobs.json')
            else:
                path = Path(save_path).expanduser().resolve()
            
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                path.unlink()
            
            payload = {"job_ids": job_ids_to_save, "out_dir": self.output_dir.as_posix()}
            with open(path, 'w') as f:
                json.dump(payload, f, indent=2)
            print(f'Batch file saved under {path}. Resume later by loading this file path in to saved_job_path.')
            return path
        else:
            raise ValueError(f'No batches exist to save. Did you submit or refresh a job?')
    
    def download(self):
        if not self.batchs and self.job_ids:
            print(f"{Fore.CYAN}Loaded from file — refreshing job statuses...{Style.RESET_ALL}")
            self.batchs = self.refresh()

        if not self.batchs:
            raise ValueError(f"{Fore.RED}No jobs found. Call submit or load jobs first.")
        
        exist_files = {p.name: p for p in self.output_dir.glob('*.zip')}
        stop_event = threading.Event()
        def _is_valid_zip(path: Path) -> bool:
            """Check ZIP magic bytes at start and EOCD signature at end. No file reading."""
            try:
                with open(path, 'rb') as f:
                    # Check ZIP magic bytes at start (PK header)
                    if f.read(4) != b'PK\x03\x04':
                        return False
                    # Check End-of-Central-Directory signature at end
                    f.seek(-22, 2)
                    return f.read(4) == b'PK\x05\x06'
            except OSError:
                return False
            
        
        def _download_file(url: str, dest: Path) -> None:
            """
            Stream-download a single file with a per-file tqdm bar.
            Returns (filename, success, error_message).
            """
            if stop_event.is_set():
                raise InterruptedError("Download cancelled by user.")
            tmp_path = dest.parent.joinpath(dest.name + '.part')
            try:
                with requests.get(url, stream=True, timeout=60) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get('content-length', 0))
                    with open(tmp_path, 'wb') as f, tqdm(
                        desc=dest.name,
                        total=total,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        leave=False,
                        position=None,
                    ) as bar:
                        for chunk in resp.iter_content(chunk_size=1024 * 256):
                            if stop_event.is_set():
                                raise InterruptedError("Download cancelled by user.")
                            f.write(chunk)
                            bar.update(len(chunk))
                tmp_path.rename(dest)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

        overall_results = {"downloaded": 0, "skipped": 0, "failed": 0, "corrupt": 0}
        
        for username, batch in self.batchs.items():
            print(f"{Fore.CYAN}{Style.BRIGHT}User: {username} ({len(batch)} jobs){Style.RESET_ALL}")
            succeeded = [job for job in batch.jobs if job.status_code == "SUCCEEDED"]

            if not succeeded:
                print("No succeeded jobs found, skipping.")
                continue
            
            tasks: list[tuple[str, str, Path]] = [] # (url, dest_path)

            for job in succeeded:
                if not job.files:
                    continue
                for file_meta in job.files:
                    fname = Path(file_meta['filename']).name
                    dest = self.output_dir / fname
                    url = file_meta.get('url') or file_meta.get('s3_uri') or file_meta.get('download_url')

                    # Skip if already exists AND is a valid ZIP
                    if fname in exist_files:
                        if _is_valid_zip(exist_files[fname]):
                            if self.config.skip_existing:
                                print(f"{Fore.YELLOW}  ✓ {fname} already exists and is valid, skipping.{Style.RESET_ALL}")
                                overall_results["skipped"] += 1
                                continue

                    # File exists but is corrupt — re-download
                        else:
                            print(f"{Fore.RED}  ✗ {fname} exists but is corrupt, re-downloading.{Style.RESET_ALL}")
                            exist_files[fname].unlink(missing_ok=True)
                            overall_results["corrupt"] += 1

                    if url:
                        tasks.append((url, dest))

            if not tasks:
                print(f"{Fore.YELLOW}  Nothing to download for {username}.{Style.RESET_ALL}")
                continue

            print(f"{Fore.GREEN}  Downloading {len(tasks)} file(s) with "
                f"{self.config.max_workers} threads...{Style.RESET_ALL}")

            try:
                with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                    futures = {executor.submit(_download_file, url, dest): dest for url, dest in tasks}
                    with tqdm(total=len(futures), desc=f"  {username}", unit="file") as pbar:
                        for future in as_completed(futures):
                            dest = futures[future]
                            fname = dest.name
                            try:
                                future.result()
                                if _is_valid_zip(dest):
                                    tqdm.write(f"{Fore.GREEN}  ✓ {fname} downloaded and verified.{Style.RESET_ALL}")
                                    overall_results["downloaded"] += 1
                                else:
                                    tqdm.write(f"{Fore.RED}  ✗ {fname} failed ZIP check, deleting.{Style.RESET_ALL}")
                                    dest.unlink(missing_ok=True)
                                    overall_results["failed"] += 1
                            except InterruptedError:                          # NEW: raised by stop_event
                                tqdm.write(f"{Fore.YELLOW}  ⚠ {fname} cancelled.{Style.RESET_ALL}")
                                overall_results["failed"] += 1
                            except Exception as e:
                                tqdm.write(f"{Fore.RED}  ✗ {fname} failed: {e}{Style.RESET_ALL}")
                                overall_results["failed"] += 1
                            pbar.update(1)

            # NEW block: catches Ctrl+C, signals all threads, waits for clean shutdown
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Ctrl+C detected — cancelling downloads...{Style.RESET_ALL}")
                stop_event.set()
                executor.shutdown(wait=True, cancel_futures=True)
                print(f"{Fore.YELLOW}Downloads stopped. Partial files cleaned up.{Style.RESET_ALL}")
                break    # NEW: stop processing remaining users too

        print(f"\n{Fore.CYAN}{Style.BRIGHT}Download Summary:{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}Downloaded : {overall_results['downloaded']}{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}Skipped    : {overall_results['skipped']}{Style.RESET_ALL}")
        print(f"  {Fore.RED}Failed     : {overall_results['failed']}{Style.RESET_ALL}")
        return self.output_dir
                
    def watch(self, refresh_interval: int = 300):
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
                
                for username, batch in self.batchs.items():
                    total_jobs += len(batch)
                    active_jobs += len(batch.filter_jobs(status_code=['RUNNING', 'PENDING']))
                    failed_jobs += len(batch.filter_jobs(status_code='FAILED'))
                    succeeded_jobs += len(batch.filter_jobs(status_code='SUCCEEDED'))
                
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Progress: {Fore.CYAN}{succeeded_jobs}/{total_jobs} Done{Fore.RESET} | "
                    f"{Fore.YELLOW}{active_jobs} Running{Fore.RESET} | "
                    f"{Fore.RED}{failed_jobs} Failed{Fore.RESET}", end='\r')

                if active_jobs == 0 and total_jobs > 0:
                    print(f"\n{Fore.GREEN}All jobs processed!{Fore.RESET}")
                    break

                time.sleep(refresh_interval)
        except KeyboardInterrupt:
            print(f"{Fore.YELLOW}Stopped watching by user.{Fore.RESET}")

