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

scenes = [(40,112),(69,112),(69,109),(69,104),(69,98),(171,106),(142,106),(142,101),(142,96),
          (40,107),(40,102),(40,97),(113,111),(113,106),(113,101),(113,96),(84,65),(84,70),
          (11,71),(11,65),(113,71),(40,71),(40,77),(142,75),(142,81),(69,84),(69,74),(157,56),
          (157,61),(157,66),(69,89),(171,93)]


quick_look_dis(scenes=scenes, start='2020-01-01', end='2020-12-31', 
                        AscendingflightDirection=True, 
                        processor='hyp3', 
                        output_dir='/local/insar',
                        credit_pool=earth_credit_pool())

