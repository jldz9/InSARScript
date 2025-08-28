#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())



# -------------
# Test S1_SLC.py
# -------------
from insarscript.core import S1_SLC
platform=['Sentinel-1A', 'Sentinel-1B']
bbox = [125.737, 41.179, 127.800, 44.106]
start = '2017-01-01'
end = '2018-12-30'
output_dir = '~/S1'
max_number = 5
s1 = S1_SLC(platform=platform, bbox=bbox, start=start, end=end, output_dir=output_dir, maxResults=max_number)
results = s1.search()
s1.footprint(save_path='~/S1/footprint.png')
s1.count
s1.dem(save_path='~/S1/DEM')
s1.download(save_path='~/S1/data')

#-------------
