#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import json
from pathlib import Path
from pprint import pformat
from dateutil.parser import isoparse


import tomllib, tomli_w
from box import Box as Config
from colorama import Fore

from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent/'config.toml'        
    config_path = Path(config_path)
    if config_path.is_file():
        try:
            with open(config_path, 'rb') as f:
                toml = tomllib.load(f)
                cfg = Config(toml)
                return cfg
        except Exception as e:
                raise ValueError(f"Error loading config file with error {e}, is this a valid config file in TOML format?")
    else:
        raise FileNotFoundError(f"Config file not found under {config_path}")

def quick_look_dis(
    bbox : list[float] = [126.451, 45.272, 127.747, 45.541],
    path: int | None = None,
    frame: int | None = None,
    year: int | list[int]= [2019,2020],
    flight_direction: str = "ascending",
    processor: str = "hyp3",
    output_dir = "out",
    credit_pool: dict = None
):
    """
    Quick look for slow ground displacement.
    This method will generate a few quick look interferograms:
    4 pairs of year-wide interferograms that cover temporal baseline of ~360 days during summer time (June, July, August, early September before harvest)
    e.g.: June 2024 - June 2025
    3 pairs of 60-120 days season interferogram from June to early September
    June -> Aug
    July -> Sep
    June -> Sep

    2 pairs of 12-36 days short term for coherence check
    
    """
    if isinstance(year, int):
        year = [year]
    elif isinstance(year, list):
        year = year
    else:
        raise TypeError("Invalid type for year parameter, should be int of a list of ints, e.g. 2020 or [2020, 2021]")
    if flight_direction.lower() in ["asc", "ascending"]:
        AscendingflightDirection = True
    elif flight_direction.lower() in ["desc", "descending","des"]:
        AscendingflightDirection = False
    else:
        raise ValueError("Invalid flight_direction parameter, should be 'ascending' or 'descending'")

    output_dir = Path(output_dir).joinpath('quick_look').expanduser().resolve()

    for y in year:
        print(f"{Fore.GREEN}Processing year: {y}")
        process_path = output_dir.joinpath(f"{y}")

        slc_early = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=str(y)+ "-06-01",
            end=str(y)+ "-09-12",
            output_dir=process_path.as_posix(),
            path=path,
            frame=frame
        )
        slc_later = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=str(y+1)+ "-06-01",
            end=str(y+1)+ "-09-12",
            output_dir=process_path.as_posix(),
            path=path,
            frame=frame
        )
        result_slc_early = slc_early.search()
        
        result_slc_late = slc_later.search()
        slc = {k: result_slc_early.get(k, []) + result_slc_late.get(k, []) for k in set(result_slc_early) | set(result_slc_late)}

     
        for key, r in slc.items():
            if len(r) <= 2:
                print(f"{Fore.YELLOW}Not enough ascending SLCs found for Path{key[0]} Frame{key[1]}, skip.")
                continue
            slc_path = process_path/f"quicklook_p{key[0]}f{key[1]}"
            slc_path.mkdir(parents=True, exist_ok=True)
            pairs = select_pairs(
                r,
                dt_targets=(12,24,60,84,96,108,360),
                dt_tol=3,
                dt_max=400, 
                pb_max=150,
                min_degree=1,
                force_connect=False
                )
            long = []
            season = []
            coherence = []
            for pair in pairs:
                early_time = isoparse(pair[0].split('_')[5])
                later_time = isoparse(pair[1].split('_')[5])
                if (later_time-early_time).days < 24:
                    coherence.append(pair)
                if 60<(later_time-early_time).days <120:
                    season.append(pair)
                if (later_time-early_time).days > 180:
                    long.append(pair)
            if len(coherence)>2:
                coherence = coherence[:2]
            elif len(coherence)==0:
                print(f"{Fore.YELLOW}No coherence pairs found for Path{key[0]} Frame{key[1]}, skip.")
                continue
            if len(season)>3:
                season = season[:3]
            elif len(season)==0:
                print(f"{Fore.YELLOW}No season pairs found for Path{key[0]} Frame{key[1]}, skip.")
                continue
            if len(long)>4:
                long = long[:4]
            elif len(long)==0:
                print(f"{Fore.YELLOW}No long pairs found for Path{key[0]} Frame{key[1]}, skip.")
                continue

            coherence_path = slc_path/f"coherence_p{key[0]}f{key[1]}"
            season_path = slc_path/f"season_p{key[0]}f{key[1]}"
            long_path = slc_path/f"long_p{key[0]}f{key[1]}"
            coherence_path.mkdir(parents=True, exist_ok=True)
            season_path.mkdir(parents=True, exist_ok=True)
            long_path.mkdir(parents=True, exist_ok=True)
            if processor == "hyp3":
                print("Will use Hyp3 to process online")

                coherence_job = Hyp3InSAR(
                    pairs=coherence,
                    out_dir=coherence_path.as_posix(),
                    earthdata_credentials_pool=credit_pool
                )
                coherence_job.submit()
                coherence_job.save(coherence_path.as_posix()+f"/hyp3_coherence_p{key[0]}f{key[1]}.json")
                print(f"Submitted coherence job for Path{key[0]} Frame{key[1]}, Job file saved under {coherence_path.as_posix()+f'/hyp3_coherence_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)
                season_job = Hyp3InSAR(
                    pairs=season,
                    out_dir=season_path.as_posix(),
                    earthdata_credentials_pool=credit_pool
                )
                season_job.submit()
                season_job.save(season_path.as_posix()+f"/hyp3_season_p{key[0]}f{key[1]}.json")
                print(f"Submitted season job for Path{key[0]} Frame{key[1]}, Job file saved under {season_path.as_posix()+f'/hyp3_season_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)
                long_job = Hyp3InSAR(
                    pairs=long,
                    out_dir=long_path.as_posix(),
                    earthdata_credentials_pool=credit_pool
                )
                long_job.submit()
                long_job.save(long_path.as_posix()+f"/hyp3_long_p{key[0]}f{key[1]}.json")
                print(f"Submitted long job for Path{key[0]} Frame{key[1]}, Job file saved under {long_path.as_posix()+f'/hyp3_long_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)

            elif processor == "ISCE":
                print("ISCE processor is not yet implemented, please use Hyp3.")

def hyp3_batch_check(
        batch_files_dir: str,
        download : bool = False,
        retry : bool = False,
        earthdata_credentials_pool: dict | None = None
):
    """
    Download a batch of hyp3 files from a directory.

    """
    batch_path = Path(batch_files_dir).expanduser().resolve()
    json_files = batch_path.rglob('*.json')

    for file in json_files:
        job = Hyp3InSAR.load(file, earthdata_credentials_pool=earthdata_credentials_pool)
        b = json.loads(file.read_text())
        print(f'Overview for job {Path(b['out_dir'])}')
        batchs = job.refresh()
        if download is True:
            job.download()
        if retry and len(job.failed_jobs)>0:
            job.retry()

def earth_credit_pool(earthdata_credentials_pool_path:str) -> dict:
    """
    Load Earthdata credit pool from a file.
    """
    earthdata_credentials_pool_path = Path(earthdata_credentials_pool_path).expanduser().resolve()
    earthdata_credentials_pool = {}
    with open(earthdata_credentials_pool_path, 'r') as f:
        for line in f:
            key, value = line.strip().split(':')
            earthdata_credentials_pool[key] = value
    return earthdata_credentials_pool