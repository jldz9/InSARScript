#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

#------------
# 1. Test select_pairs function
#------------

from insarscript.core import S1_SLC, select_pairs

from insarscript.core import S1_SLC
platform=['Sentinel-1A', 'Sentinel-1B']
bbox = [125.737, 41.179, 127.800, 44.106]
start = '2017-01-01'
end = '2018-12-30'
output_dir = '~/S1'
max_number = 20

s1 = S1_SLC(platform=platform, bbox=bbox, start=start, end=end, output_dir=output_dir, maxResults=max_number)
results = s1.search()
for key, result in results.items():
    print(f"{key}: {len(result)}")
    try:
        pairs = select_pairs(result)
    except ValueError as e:
        print(e)
# ------------
# 2. Test Hyp3_GAMMA_Processor class
# ------------
from insarscript.core import Hyp3_InSAR_Processor

test_json = Path('~/InSARScript/test/Path105_Frame441.json').expanduser().as_posix()
hyp3 = Hyp3_InSAR_Processor.load(path=test_json, save_path='~/S1/hyp3')