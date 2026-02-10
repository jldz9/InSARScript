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

from insarscript.downloader import S1_SLC, ASF_Base_Downloader

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

def earth_credit_pool(earthdata_credentials_pool_path = Path.home().joinpath('.credit_pool')) -> dict:
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

def batch_rename(
    dirs : list[str],
    pattern: str = "velocity.tif",
    ):

    for path in dirs:
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            print(f"{path} is not a valid directory, skip.")
            continue
        tif_files = list(path.rglob(f'*{pattern}'))
        for tif in tif_files:
            new_name = f"velocity_{tif.parent.name}.tif"
            new_path = tif.parent.joinpath(new_name)
            tif.rename(new_path)
            print(f"Renamed {tif.name} to {new_name}")