#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

from dateutil.parser import isoparse
import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR
from insarscript.utils import quick_look_dis, hyp3_batch_check
#import openmeteo_requests
import pandas as pd
#import requests_cache
#from retry_requests import retry
import numpy as np
import time
from dateutil.parser import isoparse
'''
a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B'],
    AscendingflightDirection=False,
    bbox = [125.737, 41.179, 127.800, 44.106],
    start='2017-01-01',
    output_dir = '~/S1',
)
results = a.search()

a.dem()

a.download()

'''
quick_look_dis(
    bbox=[116.52, 38.75, 117.125, 39.455],
    year=[2020],
    flight_direction="asc",
    processor="hyp3",
    output_dir="~/glb_dis/insar/tianjin",
    path=69,
    frame=124
)
'''

import json
from pathlib import Path
from insarscript.utils import  hyp3_batch_check
batch_files_dir = '~/JiLin/quick_look'

hyp3_batch_check(batch_files_dir, download=True)

from insarscript.utils import earth_credit_pool

pool = earth_credit_pool('~/.credit_pool')
print(pool)

tianjin = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=True,
    bbox = [116.52, 38.75, 117.125, 39.455],
    start='2014-01-01',
    end='2025-12-31',
    output_dir = '~/CHN_Tianjin',
    path=69,
    frame=124
)

tianjin.footprint()
tianjin.summary
result_tianjing_d = tianjin.pick(47,461)

tianjin_a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=True,
    bbox = [116.52, 38.75, 117.125, 39.455],
    start='2017-01-01',
    output_dir = '~/CHN_Tianjin',
)

tianjin_a.search()
tianjin_a.footprint()


hyp3_batch_check(
    batch_files_dir='~/glb_dis',
    download=True
)
'''