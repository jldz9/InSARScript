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


quick_look_dis(
    bbox=[116.52, 38.75, 117.125, 39.455],
    year=[2020],
    flight_direction="asc",
    processor="hyp3",
    output_dir="~/glb_dis/insar/tianjin",
    path=69,
    frame=124
)



print(pool)
'''
'''
tianjin = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=True,
    bbox = [116.52, 38.75, 117.125, 39.455],
    start='2014-01-01',
    end='2025-12-31',
    output_dir = '~/glb_dis/insar/tianjin',
    path=69,
    frame=124
)

tianjin.footprint()
tianjin.summary(ls = True)
results = tianjin.search()
pairs = select_pairs(results[(69,124)])
print(f"Total {len(pairs)} pairs selected for interferogram generation")


import pickle
with open('/home/jldz9/data.pkl', 'rb') as f:
    pairs = pickle.load(f)
tianjin_hyp3 = Hyp3InSAR(pairs=pairs,
                         out_dir="~/glb_dis/insar/tianjin/hyp3",
                         earthdata_credentials_pool=pool)
tianjin_hyp3.submit()
tianjin_hyp3.save(path="~/glb_dis/insar/tianjin/hyp3/full_p69f124_2.json")
'''

import json
from pathlib import Path
from insarscript.utils import  hyp3_batch_check
from insarscript.utils import earth_credit_pool
from insarscript.core import Hyp3InSAR

pool = earth_credit_pool('~/.credit_pool')
batch_files_dir = '~/glb_dis/insar/tianjin/hyp3'

#jobs = Hyp3InSAR.load(path=batch_files_dir, earthdata_credentials_pool=pool)
#jobs.refresh()

hyp3_batch_check(batch_files_dir, earthdata_credentials_pool=pool, download=False, retry=True)

