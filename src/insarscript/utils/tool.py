#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import time

from dateutil.parser import isoparse
from pathlib import Path
from pprint import pformat
from types import SimpleNamespace

import tomllib, tomli_w
from tqdm import tqdm
from box import Box as Config
from colorama import Fore
from mintpy.utils import readfile

from insarscript.core import S1_SLC, select_pairs, Hyp3_InSAR_Processor

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent.joinpath('config.toml')        
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
    results: dict | None = None,
    bbox : list[float] = [126.451, 45.272, 127.747, 45.541],
    path: int | None = None,
    frame: int | None = None,
    start: str= '2020-01-01',
    end : str = '2020-12-31',
    AscendingflightDirection: bool = True,
    processor: str = "hyp3",
    output_dir = "out",
    credit_pool: dict | None = None
):
    """
    Quick look for slow ground displacement.
    This method will generate quick overlook through given area
    :param results: The search result from ASF search output from ASFDownloader, should be a dict with {(path, frame): [asf_search.Products..,asf_search.Products..]}, if the result was provided, this program will skip searching process
    
    """
    output_dir = Path(output_dir).joinpath('quick_look').expanduser().resolve()
    if results is not None and isinstance(results, dict):
        result_slc = results
    else:
        slc = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=start,
            end=end,
            output_dir=output_dir.as_posix(),
            path=path,
            frame=frame
        )
        result_slc = slc.search()
    for key, r in tqdm(result_slc.items(), desc=f'Submiting Jobs', position=0, leave=True):
        if len(r) <= 10:
            print(f"{Fore.YELLOW}Not enough SLCs found for Path{key[0]} Frame{key[1]}, skip.")
            continue
        slc_path = output_dir.joinpath(f"quicklook_p{key[0]}f{key[1]}")
        slc_path.mkdir(parents=True, exist_ok=True)
        pairs = select_pairs(
            r,
            dt_targets=(12,24,36,48,72,96),
            dt_tol=3,
            dt_max=120, 
            pb_max=200,
            min_degree=2,
            max_degree=5,
            force_connect=True
            )
        
        if processor == "hyp3":
            print("---------Using HyP3 online processor-----------")
            job = Hyp3_InSAR_Processor(
                pairs=pairs,
                out_dir=slc_path.as_posix(),
                earthdata_credentials_pool=credit_pool
            )
            job.submit()
            job.save(slc_path.joinpath(f"quicklook_hyp3_p{key[0]}f{key[1]}.json").as_posix())
            print(f"Submitted long job for Path{key[0]} Frame{key[1]}, Job file saved under {slc_path.as_posix()+f'/hyp3_long_p{key[0]}f{key[1]}.json'}")
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
        job = Hyp3_InSAR_Processor.load(file, earthdata_credentials_pool=earthdata_credentials_pool)
        b = json.loads(file.read_text())
        print(f"Overview for job {Path(b['out_dir'])}")
        if not download :
            batchs = job.refresh()
        if download :
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


def generate_slurm_script(
    job_name="my_job",
    output_file="job_%j.out",    # %j = jobID
    error_file="job_%j.err",
    time="04:00:00",
    partition="all",
    nodes=1,
    nodelist=None,            # e.g., "node[01-05]"
    ntasks=1,
    cpus_per_task=1,
    mem="4G",
    gpus=None,                   # e.g., "1" or "2" or "1g"
    array=None,                  # e.g., "0-9" or "1-100%10"
    dependency=None,             # e.g., "afterok:123456"
    mail_user=None,
    mail_type="ALL",             # BEGIN, END, FAIL, ALL
    account=None,
    qos=None,
    modules=None,                # list of modules to load
    conda_env=None,              # name of conda env to activate
    export_env=None,             # dict of env variables
    command="echo Hello SLURM!",
    filename="job.slurm"
):
    """
    Generate a full SLURM batch script with many options.
    """

    lines = ["#!/bin/bash"]

    # Basic job setup
    lines.append(f"#SBATCH --job-name={job_name}")
    lines.append(f"#SBATCH --output={output_file}")
    lines.append(f"#SBATCH --error={error_file}")
    lines.append(f"#SBATCH --time={time}")
    lines.append(f"#SBATCH --partition={partition}")
    lines.append(f"#SBATCH --nodes={nodes}")
    lines.append(f"#SBATCH --ntasks={ntasks}")
    lines.append(f"#SBATCH --cpus-per-task={cpus_per_task}")
    lines.append(f"#SBATCH --mem={mem}")

    # Optional extras
    if gpus:
        lines.append(f"#SBATCH --gres=gpu:{gpus}")
    if array:
        lines.append(f"#SBATCH --array={array}")
    if dependency:
        lines.append(f"#SBATCH --dependency={dependency}")
    if mail_user:
        lines.append(f"#SBATCH --mail-user={mail_user}")
        lines.append(f"#SBATCH --mail-type={mail_type}")
    if account:
        lines.append(f"#SBATCH --account={account}")
    if qos:
        lines.append(f"#SBATCH --qos={qos}")
    if nodelist:
        lines.append(f"#SBATCH --nodelist={nodelist}")

    lines.append("")  # blank line

    # Environment setup
    if modules:
        for mod in modules:
            lines.append(f"module load {mod}")
    if conda_env:
        lines.append(f"source activate {conda_env}")
    if export_env:
        for k, v in export_env.items():
            lines.append(f"export {k}={v}")

    lines.append("")  # blank line

    # Execution
    lines.append("echo \"Starting job on $(date)\"")
    lines.append(command)
    lines.append("echo \"Job finished on $(date)\"")

    script_content = "\n".join(lines)

    with open(filename, "w") as f:
        f.write(script_content)

    return filename 