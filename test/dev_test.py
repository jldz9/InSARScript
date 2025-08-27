import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

from dateutil.parser import isoparse
import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR
from insarscript.utils import quick_look_dis
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
'''
quick_look_dis(
    bbox=[125.737, 41.179, 127.800, 44.106],
    year=[2020],
    flight_direction="asc",
    processor="hyp3",
    output_dir="~/JiLin/quick_look"
)
'''
import json
from pathlib import Path
from insarscript.utils import  hyp3_batch_check
batch_files_dir = '~/JiLin/quick_look'

hyp3_batch_check(batch_files_dir, download=True)