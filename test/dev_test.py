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

a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B'],
    AscendingflightDirection=False,
    bbox = [125.481, 44.312, 125.531, 44.361],
    start='2017-01-01',
    output_dir = '~/S1',
    maxResults=5
)
results = a.search()

a.dem()

a.download()
'''
quick_look_dis(
    bbox=[125.481, 44.312, 125.531, 44.416],
    year=[2020, 2021],
    flight_direction="des",
    processor="hyp3",
    output_dir="~/S1/quick_look"
)
'''