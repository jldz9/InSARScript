import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import asf_search as asf

from insarscript.utils.tool import ASFDownloader

a = ASFDownloader(
    bbox=[-109.0, 36.0, -102.0, 41.0],
    start_time="2022-01-01",
    end_time="2022-01-31",
    output_dir="downloads"
)