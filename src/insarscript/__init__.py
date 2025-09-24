#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
from pathlib import Path

from colorama import init
init(autoreset=True)
from colorama import Fore, Style, Back

logging.disable(logging.CRITICAL)
from insarscript._version import __version__


# For Sentinal-1 InSAR processing, Hyp3 and MintPy are used by default.
# ---------------------Check GDAL and SQLite3 version---------------------
# GDAL and SQLite3 are required by MintPy
# Use gdal > 3.8 and sqlite > 3.44 to avoid compatibility issues. (e.g.undefined symbol: sqlite3_total_changes64)
from packaging.version import parse as v
from osgeo import gdal
gdal_version = gdal.__version__
if v(gdal_version) < v('3.8'):
    print(f"{Fore.RED}GDAL version {gdal_version} is not supported. Please install GDAL version >= 3.8.")

import sqlite3
sqlite_version = sqlite3.sqlite_version
if v(sqlite_version) < v('3.44'):
    print(f"{Fore.RED}SQLite version {sqlite_version} is not supported. Please install SQLite version >= 3.44.")

# ---------------------Make Sure PROJ_LIB exist----------------------------
# proj.db is required when gdal tried to read the CRS, PROJ_LIB offen missing during installation. 

if os.environ.get('PROJ_LIB') is None:
    if os.environ.get('CONDA_PREFIX') is None:
        raise RuntimeError('Conda is not correctly installed, $CONDA_PREFIX does not exist')
    else: 
        os.environ["PROJ_LIB"] = os.environ['CONDA_PREFIX']+'/share/proj'
        if not Path(os.environ["PROJ_LIB"]).is_dir():
            raise RuntimeError('Proj does not installed correctly.')

# ---------------------ISCE2 Configuration---------------------
# If choose local processing, ISCE2 is required for Sentinel-1 SLC processing
# If ISCE is proper installed, ISCE_HOME should exist in the environment
# if ISCE_HOME exist, appending ISCE_HOME/applications and ISCE_HOME/bin to sys.path as recommended by MintPy 
# https://github.com/yunjunz/conda-envs/blob/main/README.md#2-install-isce-2-and-mintpy
try: 
    import isce
except ImportError:
    print(f"{Fore.RED}ISCE2 is not installed.")
    sys.exit(1)

if 'ISCE_HOME' not in os.environ:
    print(f"{Fore.RED}Can not find environment variable ISCE_HOME. isce2 is either not installed or installed in customized path.")
    sys.exit(1)
else: 
    isce_home = os.environ['ISCE_HOME']
    application_path = isce_home + '/applications'
    bin_path = isce_home + '/bin'
    os.environ['PATH'] = f"{os.environ.get('PATH','')}{os.pathsep}{application_path}{os.pathsep}{bin_path}"

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
tmp_dir = Path.home() / '.dask' / 'tmp'
tmp_dir.mkdir(parents=True, exist_ok=True)
dask_config.set({'temporary_directory':str(tmp_dir)})

# c. Extra environment variables setup
os.environ["VRT_SHARED_SOURCE"] = "0"
os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

# ---------------------Check runing environment -----------
if 'SLURM_MEM_PER_NODE' in os.environ:
    print('--------------------SLURM environment-----------------------')
    _memory_gb = int(int(os.environ['SLURM_MEM_PER_NODE'])/1024)
    _cpu_core = int(os.environ['SLURM_CPUS_PER_TASK'])
    _manager = 'slurm'
    
elif 'PBS_NUM_PPN' in os.environ:
    print('--------------------PBS environment-----------------------')
    _memory_gb = int(int(os.environ['PBS_MEM']))
    _cpu_core = int(os.environ['PBS_NUM_PPN'])
    _manager = 'pbs'
elif 'LSB_JOB_NUMPROC' in os.environ:
    print('--------------------LSF environment-----------------------')
    _memory_gb = int(int(os.environ['LSB_JOB_MEMLIMIT'])/1024)
    _cpu_core = int(os.environ['LSB_JOB_NUMPROC '])
    _manager = 'lsf'
else:
    print('--------------------Local environment---------------------')
        
    # Check if the necessary keys are available
    if 'SC_PAGE_SIZE' in os.sysconf_names and 'SC_PHYS_PAGES' in os.sysconf_names:
        page_size = os.sysconf('SC_PAGE_SIZE')
        phys_pages = os.sysconf('SC_PHYS_PAGES')
        _memory_gb = round((page_size * phys_pages) / (1024**3))
    else: _memory_gb = 8  # set default memory to 8GB if the system does not support os.sysconf
    _cpu_core = os.cpu_count()
    _manager = 'local'

_env = {
        "memory": _memory_gb,
        "cpu": _cpu_core,
        "manager": _manager

    }
# ---------------------package imports---------------------

from insarscript.utils import tool, apis
from insarscript.core import downloader, processor