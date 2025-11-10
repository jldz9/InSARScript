#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import platform
import sys
import logging

from pathlib import Path

from colorama import init
init(autoreset=True)
from colorama import Fore, Style, Back

logging.disable(logging.CRITICAL)
from insarscript._version import __version__
_system_info = platform.system()

# ---------------------MintPy Configuration---------------------------
# Configuration followed the MintPy post-installation setip 
# https://github.com/insarlab/MintPy/blob/main/docs/installation.md#3-post-installation-setup
try: 
    import mintpy
except ImportError:
    print(f"{Fore.RED}MintPy is not installed.")
    sys.exit(1)
# a. ERA5 for tropospheric correction
#TODO - Add instruction for ERA5 setup at https://github.com/insarlab/pyaps#2-account-setup-for-era5

# b. Dask for parallel processing
from dask import config as dask_config
tmp_dir = Path.home().joinpath('.dask','tmp') 
tmp_dir.mkdir(parents=True, exist_ok=True)
dask_config.set({'temporary_directory':str(tmp_dir)})

# c. Extra environment variables setup
os.environ["VRT_SHARED_SOURCE"] = "0"
os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

# ---------------------Check runing environment -----------
if 'SLURM_MEM_PER_NODE' in os.environ:
    _memory_gb = int(int(os.environ['SLURM_MEM_PER_NODE'])/1024)
    _cpu_core = int(os.environ['SLURM_CPUS_PER_TASK'])
    _manager = 'slurm'
elif 'PBS_NUM_PPN' in os.environ:
    _memory_gb = int(int(os.environ['PBS_MEM']))
    _cpu_core = int(os.environ['PBS_NUM_PPN'])
    _manager = 'pbs'
elif 'LSB_JOB_NUMPROC' in os.environ:
    _memory_gb = int(int(os.environ['LSB_JOB_MEMLIMIT'])/1024)
    _cpu_core = int(os.environ['LSB_JOB_NUMPROC '])
    _manager = 'lsf'
else:
    import psutil
    _memory_gb = round(psutil.virtual_memory().total/1024**3)
    _cpu_core = os.cpu_count()
    _manager = 'local'

_env = {
        "memory": _memory_gb,
        "cpu": _cpu_core,
        "manager": _manager,
        "system": _system_info,

    }
# ---------------------package imports---------------------

from insarscript.utils import postprocess, tool, apis
from insarscript.core.downloader import S1_SLC
from insarscript.core.processor import select_pairs, Hyp3_InSAR_Processor
from insarscript.core.sbas import  Hyp3_SBAS


