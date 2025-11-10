import os
from pathlib import Path
from colorama import Fore, Style, Back
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


import pyproj
proj_data_path = Path(pyproj.datadir.get_data_dir())
if proj_data_path.is_dir():
    os.environ["PROJ_LIB"] = proj_data_path.as_posix()
else:
    raise RuntimeError('Proj data path does not exist, please check your PROJ installation')
            