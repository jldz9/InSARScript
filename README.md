# InSARScript

InSAR Script is an open-source package designed to support the full InSAR processing pipeline.
The primary goal of this package is to provide a streamlined and user-friendly InSAR processing experience across multiple satellite products.


## Table of Contents
- Installation
- Requirements
- Usage
- Documentation

## Installation 

InSARScript can be installed using Conda
```bash
conda install jldz9::insarscript -c conda-forge

```
Pip: 

```bash
Pip install insarscript
```

Source: 

```bash
git clone https://github.com/jldz9/InSARScript.git
cd InSARScript
conda env create -f environment.yml -n insarscript_dev
```

## Requirements
- Python >=3.11
- proj >=9.4
- hyp3_sdk
- mintpy
- gdal >=3.8
- sqlite >=3.44
- mintpy
- asf_search 
- colorama 
- contextily 
- dem_stitcher 
- hyp3_sdk 
- python-box 
- rasterio >=1.4
- sentineleof 
- tomli-w

## Usage 

#### Search:

```python
from insarscript import S1_SLC

s1 = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=False,
    bbox = [124.67, 46.38, 125.35, 46.85],
    start='2020-01-01',
    end='2020-12-31',
    output_dir = '~/tmp',
)
results = s1.search()

```

#### Interferogram Process

```python
from insarscript import S1_SLC
from insarscript import select_pairs
sbas_pairs = select_pairs(search_results= filter_results[(3,435)])

from insarscript import Hyp3_InSAR_Processor
hyp3_sbas = Hyp3_InSAR_Processor(
    pairs = sbas_pairs,
    out_dir = '~/tmp'
)
batch = hyp3_sbas.submit()
hyp3_sbas.save()
hyp3_sbas.refresh()
hyp3_sbas.download()

```

#### SBAS

```python
from insarscript import Hyp3_SBAS
sbas_run = Hyp3_SBAS(
    hyp3_dir = '~/tmp'
)
sbas_run.prep_data()
sbas_run.run()
```

## Documentation 

[InSARScript documentation](https://jldz9.github.io/InSARScript/)

