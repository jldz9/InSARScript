#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import time
from dataclasses import dataclass, field

from asf_search.exceptions import ASFSearchError
from asf_search import ASFProduct
from collections import defaultdict
from colorama import Fore, Style
from dateutil.parser import isoparse
from hyp3_sdk import HyP3, Batch
from pathlib import Path

def select_pairs(search_results: list[ASFProduct], 
                 dt_targets:tuple[int] =(6, 12, 24, 36, 48, 72, 96) ,
                 dt_tol:int=3,
                 dt_max:int=120,
                 pb_max:int=150,

                 min_degree:int=3):
    
    """
    Select interfergrom pairs based on temporalBaseline and perpendicularBaseline'
    :param search_results: The list of ASFProduct from asf_search 
    :param dt_targets: The prefered temporal spacings to make interfergrams
    :param dt_tol: The tolerance in days adds to temporal spacings for flexibility
    :param dt_max: The maximum temporal baseline [days]
    :param pb_max: The maximum perpendicular baseline [m]
    :param min_degree: The minimum number of connections
    """
    prods = sorted(search_results, key=lambda p: p.properties['startTime'])
    ids = {p.properties['sceneName'] for p in prods}
    id_time = {p.properties['sceneName']: p.properties['startTime'] for p in prods}
    # 1) Build pairwise baseline table with caching (N stacks; each pair filled once)
    B = {} # (earlier,later) -> (|dt_days|, |bperp_m|)
    for ref in prods:
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
            dt = abs(sec.properties['temporalBaseline'])
            bp = abs(sec.properties['perpendicularBaseline'])
            
            B[(a,b)] = (dt, bp)

    # 2) First-cut keep by Δt/Δ⊥
    def pass_rules(dt, bp):
        near = any(abs(dt -t)<= dt_tol for t in dt_targets)
        return near and dt <= dt_max and bp <= pb_max
    
    pairs = {e for e, (dt, bp) in B.items() if pass_rules(dt, bp)}

    # 3) Enforce connectivity: degree ≥ MIN_DEGREE (add nearest-time links under PB cap)

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
    return sorted(pairs)

@dataclass
class Hyp3InSAR:
    # User should have Earthdata urs.earthdata.nasa.gov in .netrc
    
    job_ids: list[str] = field(default_factory=list)
    out_dir:str ="products_hyp3",
    name_prefix:str ="ifg",

    def submit(self,
        pairs,
        include_look_vectors:bool = False, 
        include_inc_map:bool =False,
        looks:str='20x4',
        include_dem :bool= False,
        include_wrapped_pahse :bool= False,
        apply_water_mask :bool= True,
        include_displacement_maps:bool=True,
        phase_filter_parameter :float= 0.6
        ):

        batch=Batch()
        self.client = HyP3()
        for ref_id, sec_id in pairs:
            job = self.client.submit_insar_job(
                granule1=ref_id,
                granule2=sec_id,
                name= f'{self.name_prefix}_{ref_id.split('_')[5]}_{sec_id.split('_')[5]}',
                include_look_vectors=include_look_vectors,
                include_inc_map = include_inc_map,
                looks =looks,
                include_dem=include_dem,
                include_wrapped_phase=include_wrapped_pahse,
                apply_water_mask=apply_water_mask,
                include_displacement_maps=include_displacement_maps,
                phase_filter_parameter=phase_filter_parameter
            )
            batch += job
        self.job_ids.extend([j.job_id for j in batch.jobs])
        self.batch = batch
        return batch
    
    def refresh(self, batch=None):
        """Refresh job statuses from HyP3 for the provided batch or the stored job_ids."""
        b = Batch()
        if batch is None:
            if not self.job_ids:
                raise ValueError(f'No Job exist and no batch provided, did you submitted a job?')
            for j in self.job_ids:
                job = self.client.get_job_by_id(j)
                b += job
        else:
            # normalize to latest state from server
            for j in batch.jobs:
                job = self.client.get_job_by_id(j.job_id)
                b += job
        for job in b.jobs:
            print(f'{Style.BRIGHT}Name:{Style.RESET_ALL}{job.name} {Style.BRIGHT}Job ID:{Style.RESET_ALL}{job.job_id} {Style.BRIGHT}Job type:{Style.RESET_ALL}{job.job_type} {Style.BRIGHT}Status:{Style.RESET_ALL}{job.status_code}')
        return b
         
    def download(self, batch: Batch | None = None, *, subdir: str | None = None) -> Path:
        b = self.refresh(batch)
        out = Path(self.out_dir if subdir is None else Path(self.out_dir, subdir))
        out.mkdir(parents=True, exist_ok=True)
        b.filter_jobs(succeeded=True).download_files(location=str(out))
        return out

    def save(self, path: str = "hyp3_jobs.json") -> str:
        """ ---- persistence (resume later) ----"""
        payload = {"job_ids": self.job_ids, "out_dir": self.out_dir, "name_prefix": self.name_prefix}
        Path(path).write_text(json.dumps(payload, indent=2))
        print(f'Batch file saved under {path}, you may resume using Hyp3InSAR.load(path: "file path")')
        return path
    
    @classmethod
    def load(cls, path: str = "hyp3_jobs.json") -> "Hyp3InSAR":
        data = json.loads(Path(path).read_text())
        print('Batch file loaded')
        return cls(out_dir=data["out_dir"], name_prefix=data["name_prefix"], job_ids=data["job_ids"])

