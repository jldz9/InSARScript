#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())


import asf_search as asf
from insarscript.utils import quick_look_dis, hyp3_batch_check, earth_credit_pool
#import openmeteo_requests
import pandas as pd
#import requests_cache
#from retry_requests import retry
import numpy as np
import time

path = '~/tmp'
hyp3_batch_check(path)