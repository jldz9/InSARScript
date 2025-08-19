import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR



a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=False,
    bbox = [126.451, 45.272, 127.747, 45.541],
    start='2017-01-01',
    output_dir = '~/S1'
)
results = a.search()

pairs = select_pairs(results[(105,441)])

runner2 = Hyp3InSAR.load('/home/jldz9/S1/batch.json')

#batch = runner.submit(pairs)
#a.dem()

#a.download()


