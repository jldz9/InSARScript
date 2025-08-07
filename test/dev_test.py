
import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import asf_search as asf

from insarscript.utils.tool import S1_SLC

a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B'],
    maxResults=5,
    AscendingflightDirection=True,
    bbox = [-113.18, 37.77, -112.44, 38.10],
    start='2017-01-01',
    end='2019-12-30',
    download_orbit=True,
    output_dir = '~/S1'
)
a.search()
a.download()


