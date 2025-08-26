#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
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
    year: int | list[int]= [2019,2020],
    flight_direction: str = "ascending",
    processor: str = "hyp3",
    output_dir = "out"  
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

    output_dir = Path(output_dir).expanduser().resolve()

    for y in year:
        print(f"{Fore.GREEN}Processing year: {y}")
        process_path = Path(output_dir+f"/{y}/{flight_direction.lower()}")
        process_path.mkdir(parents=True, exist_ok=True)
        slc_early = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=str(y)+ "-06-01",
            end=str(y)+ "-09-12",
            output_dir=process_path.as_posix()
        )
        slc_later = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=str(y+1)+ "-06-01",
            end=str(y+1)+ "-09-12",
            output_dir=process_path.as_posix()
        )
        result_slc_early = slc_early.search()
        
        result_slc_late = slc_later.search()
        slc = {k: result_slc_early.get(k, []) + result_slc_late.get(k, []) for k in set(result_slc_early) | set(result_slc_late)}

     
        for key, r in slc.items():
            slc_path = process_path/f"SLC_p{key[0]}f{key[1]}"
            slc_path.mkdir(parents=True, exist_ok=True)
            if len(r) <= 2:
                print(f"{Fore.YELLOW}Not enough ascending SLCs found for Path{key[0]} Frame{key[1]}, skip.")
                continue
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
                    out_dir=coherence_path.as_posix()
                )
                coherence_job.submit()
                coherence_job.save(coherence_path.as_posix()+f"/hyp3_coherence_p{key[0]}f{key[1]}.json")
                print(f"Submitted coherence job for Path{key[0]} Frame{key[1]}, Job file saved under {coherence_path.as_posix()+f'/hyp3_coherence_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)
                season_job = Hyp3InSAR(
                    pairs=season,
                    out_dir=season_path.as_posix()
                )
                season_job.submit()
                season_job.save(season_path.as_posix()+f"/hyp3_season_p{key[0]}f{key[1]}.json")
                print(f"Submitted season job for Path{key[0]} Frame{key[1]}, Job file saved under {season_path.as_posix()+f'/hyp3_season_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)
                long_job = Hyp3InSAR(
                    pairs=long,
                    out_dir=long_path.as_posix()
                )
                long_job.submit()
                long_job.save(long_path.as_posix()+f"/hyp3_long_p{key[0]}f{key[1]}.json")
                print(f"Submitted long job for Path{key[0]} Frame{key[1]}, Job file saved under {long_path.as_posix()+f'/hyp3_long_p{key[0]}f{key[1]}.json'}")
                time.sleep(1)

            elif processor == "ISCE":
                print("ISCE processor is not yet implemented, please use Hyp3.")

def batch_download(
        batch_files_dir: str
):
    """
    Download a batch of hyp3 files from a directory.
    """
    #TODO recursive search all .json files in the directory and batch load them to download and monitor, remove already downloaded and  mark download failed and unready jobs
    pass