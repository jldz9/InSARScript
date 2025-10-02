#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import netrc
import time
import getpass
from pathlib import Path

from asf_search.exceptions import ASFSearchError
from asf_search import ASFProduct
from collections import defaultdict
from colorama import Fore, Style
from dateutil.parser import isoparse
from hyp3_sdk import HyP3, Batch
from hyp3_sdk.exceptions import AuthenticationError, HyP3Error
from tqdm import tqdm

def select_pairs(search_results: list[ASFProduct], 
                dt_targets:tuple[int] =(6, 12, 24, 36, 48, 72, 96) ,
                dt_tol:int=3,
                dt_max:int=120,
                pb_max:int=150,
                min_degree:int=3,
                max_degree:int=999,
                force_connect: bool = True,
                restrict_within_list: bool = True):
    
    """
    Select interfergrom pairs based on temporalBaseline and perpendicularBaseline'
    :param search_results: The list of ASFProduct from asf_search 
    :param dt_targets: The prefered temporal spacings to make interfergrams
    :param dt_tol: The tolerance in days adds to temporal spacings for flexibility
    :param dt_max: The maximum temporal baseline [days]
    :param pb_max: The maximum perpendicular baseline [m]
    :param min_degree: The minimum number of connections
    :param max_degree: The maximum number of connections
    :param force_connect: if connections are less than min_degree with given dt_targets, will force to use pb_max to search for additional pairs. Be aware this could leads to low quality pairs.
    :param restrict_within_list: if True, will connect pairs even if they are not in the provided search results list and add into pairs.
    """
    if len(search_results) < 2 and restrict_within_list is True:
        raise ValueError(f'Need at least 2 products to form pairs, got {len(search_results)}, if you want to connect outside the search results, set restrict_within_list=False')
    prods = sorted(search_results, key=lambda p: p.properties['startTime'])
    ids = {p.properties['sceneName'] for p in prods}
    id_time = {p.properties['sceneName']: p.properties['startTime'] for p in prods}
    # 1) Build pairwise baseline table with caching (N stacks; each pair filled once)
    B = {} # (earlier,later) -> (|dt_days|, |bperp_m|)
    for ref in tqdm(prods, desc="Finding pairs", position=0, leave=True):
        rid = ref.properties['sceneName']
        print(f'looking for paris for {rid}')
        for attempt in range(1, 11):
            try:
                stacks = ref.stack()
                break
            except ASFSearchError as e: 
                if attempt == 10:
                    raise 
                time.sleep(0.5 * 2**(attempt-1))
                
        for sec in stacks:
            sid = sec.properties['sceneName']
            if sid not in ids or sid == rid:
                continue
            a, b = sorted((rid, sid), key=lambda k: id_time[k])
            if (a,b) in B:
                continue
            dt = abs(10000 if sec.properties['temporalBaseline'] is None else sec.properties['temporalBaseline'])
            bp = abs(10000 if sec.properties['perpendicularBaseline'] is None else sec.properties['perpendicularBaseline'])
            
            B[(a,b)] = (dt, bp)

    # 2) First-cut keep by Δt/Δ⊥
    def pass_rules(dt, bp):
        near = any(abs(dt -t)<= dt_tol for t in dt_targets)
        return near and dt <= dt_max and bp <= pb_max
    
    pairs = {e for e, (dt, bp) in B.items() if pass_rules(dt, bp)}

    # 3) Enforce connectivity: degree ≥ MIN_DEGREE (add nearest-time links under PB cap)
    if force_connect is True:
        neighbors = defaultdict(set)

        for a, b in pairs:
            neighbors[a].add(b)
            neighbors[b].add(a)

        names = [p.properties['sceneName'] for p in prods]
        for n in names:
            if len(neighbors[n]) >= min_degree:
                continue
            cands = sorted((m for m in names if m != n), key=lambda m: abs((isoparse(id_time[m]) - isoparse(id_time[n])).days))
            for m in cands:
                a, b = sorted((n, m), key=lambda k: id_time[k])
                dtbp = B.get((a, b))
                if not dtbp:
                    continue
                _, bp = dtbp
                if bp > pb_max:
                    continue
                if (a, b) not in pairs:
                    pairs.add((a, b))
                    neighbors[a].add(b); neighbors[b].add(a)
                if len(neighbors[n]) >= min_degree:
                    break

        for n in names:
            while len(neighbors[n]) > max_degree:
                # Rank this node’s pairs by "badness" = (dt, pb), descending
                ranked = sorted(
                    [(m, *B.get(tuple(sorted((n, m))), (99999, 99999))) for m in neighbors[n]],
                    key=lambda x: (x[1], x[2]),  # sort by dt, then pb
                    reverse=True
                )
                worst, _, _ = ranked[0]  # worst neighbor
                a, b = sorted((n, worst), key=lambda k: id_time[k])
                if (a, b) in pairs:
                    pairs.remove((a, b))
                neighbors[a].discard(b)
                neighbors[b].discard(a)
    
    return sorted(pairs)

class Hyp3_InSAR_Processor:
    """Hyp3 processor for interferogram generation online."""
    def __init__(self,
                pairs: list[str, str] | tuple[str, str] | list[tuple[str, str]] | None=None, 
                include_look_vectors:bool=True,
                include_inc_map:bool=True,
                looks:str='20x4',
                include_dem :bool=True,
                include_wrapped_pahse :bool=False,
                apply_water_mask :bool=True,
                include_displacement_maps:bool=True,
                phase_filter_parameter :float=0.6,
                out_dir:str = '~/tmp',
                job_name_prefix:str="ifg",
                job_ids: dict[str, list[str]] | None=None,
                earthdata_credentials_pool: dict[str, str] | None=None
                ):
        """
        Hyp3 processor for interferogram generation.
        :param pairs: A single pair of (reference, secondary) granule ids or a list of tuples contains (reference, secondary) granule ids.
        :param include_look_vectors: Whether to include look vectors in the output.
        :param include_inc_map: Whether to include incidence map in the output.
        :param looks: The looks to use for the output.
        :param include_dem: Whether to include DEM in the output.
        :param include_wrapped_phase: Whether to include wrapped phase in the output.
        :param apply_water_mask: Whether to apply water mask in the output.
        :param include_displacement_maps: Whether to include displacement maps in the output.
        :param phase_filter_parameter: The phase filter parameter to use.
        :param out_dir: The output directory for the results.
        :param job_name_prefix: The job name prefix to use.
        :param job_ids: A list of job IDs to use.
        :param earthdata_credentials_pool: A dictionary containing a pool of Earthdata credentials with format {'username': 'passowrd'}
        """
      
        self.out_dir : Path = Path(out_dir).expanduser().resolve()
        self.include_look_vectors: bool = include_look_vectors
        self.include_inc_map: bool = include_inc_map
        self.looks: str = looks
        self.include_dem: bool = include_dem
        self.include_wrapped_phase: bool = include_wrapped_pahse
        self.apply_water_mask: bool = apply_water_mask
        self.include_displacement_maps: bool = include_displacement_maps
        self.phase_filter_parameter: float = phase_filter_parameter
        self.pairs = pairs
        self.job_name_prefix = job_name_prefix
        self.job_ids = defaultdict(list)
        if job_ids is not None:
            for user, ids in job_ids.items():
                self.job_ids[user].extend(ids)
        self._hyp3_authorize(pool=earthdata_credentials_pool)

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
            self._pool_index = 0
        else:
            self._auth_pool = False
            self._username_pool = [self._username]
            self._password_pool = [self._password]
            self._pool_index = 0

    def submit(self):
        """
        Submit InSAR job pairs to HyP3.
        """
        batchs = defaultdict(Batch)
        if isinstance(self.pairs, (list, tuple)) and all(isinstance(p, str) for p in self.pairs):
            pairs = [(self.pairs[0], self.pairs[1])]
        elif isinstance(self.pairs, (list, tuple)) and all(isinstance(p, tuple) for p in self.pairs):
            pairs = self.pairs

        for (ref_id, sec_id) in tqdm(pairs, desc="Submitting jobs"):
            for attempt in range(len(self._username_pool)):
                try:
                    job = self.client.submit_insar_job(
                        granule1=ref_id,
                        granule2=sec_id,
                        name= f"{self.job_name_prefix}_{ref_id.split('_')[5]}_{sec_id.split('_')[5]}",
                        include_look_vectors=self.include_look_vectors,
                        include_inc_map = self.include_inc_map,
                        looks = self.looks,
                        include_dem=self.include_dem,
                        include_wrapped_phase=self.include_wrapped_phase,
                        apply_water_mask=self.apply_water_mask,
                        include_displacement_maps=self.include_displacement_maps,
                        phase_filter_parameter=self.phase_filter_parameter
                    )
                    batchs[self._username_pool[self._pool_index]] += job
                    time.sleep(0.1)
                    print(f"{Fore.GREEN} Pair ({ref_id} - {sec_id}) submitted successfully.")
                    break
                except HyP3Error as e:
                        print(f"{Fore.YELLOW}Rate limit exceeded on {self._username_pool[self._pool_index]}")
                        if self._auth_pool is True:
                            self._pool_index = (self._pool_index + 1) % len(self._username_pool)
                            for retry in range(3):
                                try:
                                    self.client = HyP3(username=self._username_pool[self._pool_index], password=self._password_pool[self._pool_index])
                                    break
                                except AuthenticationError:
                                    continue
                            print(f"{Fore.GREEN}Switching to next credentials: {self._username_pool[self._pool_index]}\n")
                            time.sleep(0.1)
                            if attempt == len(self._username_pool)-1:
                                raise RuntimeError(f'All credentials in the pool have been rate limited, please try later.')
                            continue
                        elif self._auth_pool is False:
                            raise
        self.job_ids = defaultdict(list)
        for username, batch in batchs.items():
            for job in batch.jobs:
                self.job_ids[username].append(job.job_id)
        self.batchs = batchs
        return batchs
    
    def retry(self):
        """
        Sometime Hyp3 jobs fail due to various reasons, this function will retry failed jobs in the stored batchs.
        """
        if not hasattr(self, 'failed_jobs') or self.batchs is None:
            batch = self.refresh()
        if len(self.failed_jobs) == 0:
            print(f'No failed jobs found.')
            return
        bool_params = [
            "include_look_vectors",
            "include_inc_map",
            "include_dem",
            "include_wrapped_phase",
            "include_los_displacement",
            "include_displacement_maps",
            "apply_water_mask",
        ]
        for key in bool_params:
            values = [job.job_parameters[key] for job in self.failed_jobs]
            if all(values):
                setattr(self, key, True)
            elif not any(values):   # all False
                setattr(self, key, False)
            else:
                raise ValueError(
                    f"Inconsistent {key} in failed jobs, "
                    "please create a new Hyp3_GAMMA_Processor instance with the pairs and correct parameters to resubmit."
                )
        looks = [job.job_parameters["looks"] for job in self.failed_jobs]
        if all(l == looks[0] for l in looks):
            self.looks = looks[0]
        else:
            raise ValueError("Inconsistent looks in failed jobs.")
        self.pairs = [(job.job_parameters['granules'][0], job.job_parameters['granules'][1]) for job in self.failed_jobs]
        _ = self.submit()
        retry_path = self.out_dir.joinpath('hyp3_retry_jobs.json')
        if Path(retry_path).is_file():
            timestamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
            retry_path = self.out_dir.joinpath(f'hyp3_retry_jobs_{timestamp}.json')
            print(f"{Fore.YELLOW}hyp3_retry_jobs.json already exists, saving to {retry_path} instead.")
        self.save(retry_path)

    def refresh(self, batchs:dict|None=None):
        """Refresh job statuses from HyP3 for the provided batch or the stored job_ids."""
        tmp_batchs = defaultdict(Batch)
        failed_jobs = []
        if batchs is None:
            if not self.job_ids:
                raise ValueError(f'No jobs exist and no batch provided, did you submitted or loaded a job?')
            for username, job_ids in self.job_ids.items():
                self.client = HyP3(username=username, password=self._password_pool[self._username_pool.index(username)])
                all_jobs = self.client.find_jobs()
                jobs = Batch([j for j in all_jobs if j.job_id in job_ids])
                tmp_batchs[username] += jobs
        else:
            # normalize to latest state from server
            for username, batch in batchs.items():
                self.client = HyP3(username=username, password=self._password_pool[self._username_pool.index(username)])
                all_jobs = self.client.find_jobs()
                jobs = Batch([j for j in all_jobs if j.job_id in [job.job_id for job in batch.jobs]])
                tmp_batchs[username] += jobs
        for username, batch in tmp_batchs.items():
            print(f'Username: {username}')
            f = [job for job in batch.jobs if job.status_code == "FAILED"]
            if len(f) > 0:
                print(f'{Fore.YELLOW}Failed jobs found for {username}, please use .retry() to resubmit failed jobs')
                failed_jobs += f
                for f_job in f:
                    print(f'Failed jobs: {f_job.job_id}')
            for job in batch.jobs:
                print(f'{Style.BRIGHT}Name:{Style.RESET_ALL}{job.name} {Style.BRIGHT}Job ID:{Style.RESET_ALL}{job.job_id} {Style.BRIGHT}Job type:{Style.RESET_ALL}{job.job_type} {Style.BRIGHT}Status:{Style.RESET_ALL}{job.status_code}')
        self.batchs = tmp_batchs
        self.failed_jobs = failed_jobs
        return tmp_batchs

    def download(self, batchs: dict[Batch] | None = None) -> Path:
        if batchs is None:
            b = self.refresh()
        else:
            b = self.refresh(batchs)
        out = self.out_dir
        out.mkdir(parents=True, exist_ok=True)
        exist = out.rglob("*.zip")
        exist_name = [p.name for p in exist]
        for username, batch in b.items():
            succeeded = [job for job in batch.jobs if job.status_code == "SUCCEEDED"]
            if len(succeeded) == 0:
                print(f'{Fore.YELLOW}No succeeded jobs found for {username}, will skip download')
                continue
            elif len(succeeded) > 0:
                for job in tqdm(succeeded, desc="Downloading:", position=0):
                    if all(j['filename'] in exist_name for j in job.files):
                        print(f'{Fore.YELLOW}{job.name} exist under {out}, will skip download')
                        continue
                    self.client = HyP3(username=username, password=self._password_pool[self._username_pool.index(username)])
                    job.download_files(location=str(out))
        return out

    def save(self, path: str | None = None) -> Path:
        """ ---- persistence (resume later) ----"""
        if hasattr(self, 'batchs') is False or self.batchs is None:
            raise ValueError(f'No batchs exist to save, did you submitted or refreshed a job?')
        if path is None:
            path : Path = self.out_dir.joinpath('hyp3_jobs.json')
        else:
            path : Path = Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            path.unlink()
        payload = {"job_ids": self.job_ids, "out_dir": self.out_dir.as_posix()}
        path.write_text(json.dumps(payload, indent=2))
        print(f'Batch file saved under {path}, you may resume using Hyp3_InSAR_Processor.load(path: "file path")')
        return path
    
    @classmethod
    def load(cls, path: str = "hyp3_jobs.json", save_path : str | None = None, earthdata_credentials_pool: dict | None = None) -> "Hyp3_InSAR_Processor":
        path = Path(path).expanduser().resolve()
        data = json.loads(path.read_text())
        if save_path is not None:
            save_path = Path(save_path).expanduser().resolve()
        else:
            save_path = Path(data['out_dir']).expanduser().resolve()
        save_path.mkdir(parents=True, exist_ok=True)
        return cls(out_dir=save_path.as_posix(), job_ids=data["job_ids"], earthdata_credentials_pool=earthdata_credentials_pool)

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
        

