import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR



a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B'],
    AscendingflightDirection=True,
    maxResults=5,
    bbox = [-113.18, 37.77, -112.44, 38.10],
    start='2017-01-01',
    end='2019-12-30',
    download_orbit=True,
    output_dir = '~/S1'
)
#results = a.search()
#pairs = select_pairs(results[(20,123)])

runner2 = Hyp3InSAR.load('/home/jldz9/S1/batch.json')

#batch = runner.submit(pairs)
#a.dem()

#a.download()


