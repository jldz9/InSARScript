#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

from dateutil.parser import isoparse
import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR
from insarscript.utils import quick_look_dis, hyp3_batch_check, earth_credit_pool
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


quick_look_dis(
    bbox=[116.52, 38.75, 117.125, 39.455],
    year=[2020],
    flight_direction="asc",
    processor="hyp3",
    output_dir="~/glb_dis/insar/tianjin",
    path=69,
    frame=124
)



print(pool)
'''
'''
tianjin = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=True,
    bbox = [120.721, 40.878, 123.484, 41.511],#,
    start='2020-01-01',
    end='2020-12-31',
    output_dir = '~/glb_dis/insar/tianjin',
)

tianjin.footprint(save_path='~/test2.png')
tianjin.summary(ls = True)
pool = earth_credit_pool('~/.credit_pool')
quick_look_dis(
    bbox = [114.75, 36.21, 118.29, 39.95],
    flight_direction = "asc",
    year=2020,
    output_dir="~/glb_dis/insar/tianjin",
    credit_pool=pool,
)
'''

'''

results = tianjin.search()
pairs = select_pairs(results[(69,124)])
print(f"Total {len(pairs)} pairs selected for interferogram generation")


import pickle
with open('/home/jldz9/data.pkl', 'rb') as f:
    pairs = pickle.load(f)
tianjin_hyp3 = Hyp3InSAR(pairs=pairs,
                         out_dir="~/glb_dis/insar/tianjin/hyp3",
                         earthdata_credentials_pool=pool)
tianjin_hyp3.submit()
tianjin_hyp3.save(path="~/glb_dis/insar/tianjin/hyp3/full_p69f124_2.json")
'''
'''
import json
from pathlib import Path
from insarscript.utils import  hyp3_batch_check
from insarscript.utils import earth_credit_pool
from insarscript.core import Hyp3InSAR

pool = earth_credit_pool('~/.credit_pool')
batch_files_dir = '~/glb_dis/insar/tianjin/hyp3'

#jobs = Hyp3InSAR.load(path=batch_files_dir, earthdata_credentials_pool=pool)
#jobs.refresh()

#hyp3_batch_check(batch_files_dir, earthdata_credentials_pool=pool, download=False, retry=True)





# prep_gamma_test

gamma_path = Path('~/glb_dis/insar/tianjin/quick_look/2020/quicklook_p105f456').expanduser().resolve()

from insarscript.core import Hyp3GAMMA
mintpy = Hyp3GAMMA(workdir='/scratch/quicklook_p105f456', hyp3_dir = gamma_path)
mintpy.unzip_hyp3()
mintpy.collect_files()
mintpy.clip_to_overlap()
mintpy.get_high_coh_mask()
mintpy.run()
'''
'''


---------------------------Quick look interferogram footprint 
from collections import defaultdict
import pandas as pd
p = Path('~/glb_dis/insar/tianjin/mintpy/tmp').expanduser().resolve()
sar = list(p.rglob('*unw_phase.tif'))
results = []
import rasterio 
import matplotlib.pyplot as plt
from pyproj import Transformer
import contextily as ctx
from shapely import box
from shapely.ops import transform
transformer = Transformer.from_crs("EPSG:32650", "EPSG:3857", always_xy=True)
N = len(list(sar))
cmap = plt.cm.get_cmap('hsv', N+1)
fig, ax = plt.subplots(1, 1, figsize=(10,10))


for i,s in enumerate(sar): 
    print(s)
    with rasterio.open(str(s)) as ds:
       bounds = ds.bounds 
       center_lon = (bounds.left+bounds.right)/2
       center_lat = (bounds.bottom + bounds.top)/2
       geom = transform(transformer.transform, box(bounds.left, bounds.bottom, bounds.right, bounds.top))
       x,y = geom.exterior.xy
       ax.plot(x,y, linewidth=2,color=cmap(i))
       tmp = {
           'name': s.name,
           'width': ds.width,
           'height': ds.height,
           'longitude':center_lon,
           'latitude': center_lat,
       }
       results.append(tmp)
ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
ax.set_axis_off()
plt.savefig('test.png')

df = pd.DataFrame(results)
'''   


#hyp3_batch_check('~/glb_dis/insar/tianjin/quick_look', download=True)
def main():
    from insarscript.utils import generate_slurm_script
    workdir = Path('~/glb_dis/insar/tianjin/quick_look/2020').expanduser().resolve()
    #paths = [p for p in workdir.glob('*') if p.is_dir()]
    paths = [#Path('/home/C838053462/glb_dis/insar/tianjin/quick_look/2020/quicklook_p142f111')]
             #Path('/home/C838053462/glb_dis/insar/tianjin/quick_look/2020/quicklook_p142f116')]
             #Path('/home/C838053462/glb_dis/insar/tianjin/quick_look/2020/quicklook_p142f121')]
             Path('/home/C838053462/glb_dis/insar/tianjin/quick_look/2020/quicklook_p142f126'),
             Path('/home/C838053462/glb_dis/insar/tianjin/quick_look/2020/quicklook_p3f455')]

    for path in paths:
        generate_slurm_script(job_name=f'sbas_{path.name}',
                              output_file=f'{path.name}_%j.out',
                              error_file=f'{path.name}_%j.err',
                              cpus_per_task=8, 
                              mem="16G",
                              conda_env='dev',
                              filename=f'{path.name}.slurm',
                              command="export PYTHONPATH=~/InSARScript/src\n"
                              "python << 'EOF'\n" \
                              "from pathlib import Path\n" \
                              "from insarscript.core import Hyp3InSAR\n" \
                              "from insarscript.core import Hyp3GAMMA\n" \
                              f"mintpy = Hyp3GAMMA(hyp3_dir ='{path}')\n"\
                              "mintpy.run()\n"\
                              "EOF"
        )

if __name__ == "__main__":
    main()