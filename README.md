# InSARHub

InSARHub is a modular Python framework for automated InSAR and time-series processing.

The primary goal of this package is to provide a streamlined and user-friendly InSAR processing experience across multiple satellite products.

## Table of Contents
- Installation
- Requirements
- Usage
- CLI
- Documentation

## Installation 

InSARHub can be installed using Conda:
```bash
conda install insarhub -c conda-forge
```
Pip:

```bash
pip install insarhub
conda install gdal
```

From source: 

```bash
git clone https://github.com/jldz9/InSARHub.git
cd InSARHub
conda env create -f environment.yml -n insarhub_dev
```

## Requirements
- Python >=3.11
- numpy <2.0"
- proj >=9.4
- gdal >=3.8
- sqlite >=3.44
- mintpy
- asf_search 
- colorama 
- contextily 
- dem_stitcher 
- hyp3_sdk 
- rasterio >=1.4
- sentineleof 

## Usage 

### Downloader:

```python
from insarhub import Downloader
```

- View available downloaders

    ```python
    Downloader.available()
    ```
- Create downloader

    ```python
    s1 = Downloader.create('S1_SLC', 
                            intersectsWith=[-113.05, 37.74, -112.68, 38.00],
                            start='2020-01-01', 
                            end='2020-12-31',  
                            relativeOrbit=100, 
                            frame=466, 
                            workdir='path/to/dir')
    ```

- Search
    ```python
    results = dl.search()
    ```

- Filter
    ```python
    filter_result = dl.filter(start='2020-02-01')
    ```

- Download

    ```python
    dl.download()
    ```

### Processor:

```python
from insarhub import Processor
```
- View available processors
    ```python
    Processor.available()
    ```

- Create Processor

    ```python
    processor = Processor.create('Hyp3_InSAR', workdir='/your/work/path', pairs=pairs)
    ```

- Submit Jobs
    ```python
    jobs = processor.submit()
    ```

- Refresh Jobs

    ```python
    jobs = processor.refresh()
    ```
- Download Sucessed Jobs

    ```python
    processor.download()
    ```


### Analyzer

```python
from insarhub import Analyzer
```
- View available analyzers
    ```python
    Analyzer.available()
    ```

- Create Analyzer

    ```python
    analyzer = Analyzer.create('Hyp3_SBAS', workdir="/your/work/dir")
    ```
- Prepare data

    ```python
    analyzer.prep_data()
    ```

- Run time-series analysis
    ```python
    analyzer.run()
    ```

## CLI

InSARHub includes a command-line interface for running the full pipeline without writing Python code, suitable for HPC batch jobs and scripted workflows.

```bash
insarhub <command> [options]
```

### End-to-end example

```bash
# Search scenes and select interferogram pairs
insarhub downloader -N S1_SLC \
    --AOI -113.05 37.74 -112.68 38.00 \
    --start 2020-01-01 --end 2020-12-31 \
    --stacks 100:466 \
    -w /data/bryce \
    --select-pairs

# Submit pairs to HyP3 (auto-reads pairs_p*_f*.json from workdir subfolders)
insarhub processor submit -w /data/bryce

# Wait for jobs and download results automatically
insarhub processor watch -w /data/bryce

# Run MintPy time-series analysis
insarhub analyzer -N Hyp3_SBAS -w /data/bryce run
```

### Commands

| Command | Description |
|---------|-------------|
| `insarhub downloader` | Search scenes, select pairs, and download data |
| `insarhub processor submit` | Submit interferogram pairs to HyP3 |
| `insarhub processor watch` | Poll HyP3 and download results when complete |
| `insarhub analyzer run` | Prepare data and run MintPy SBAS analysis |
| `insarhub utils clip` | Clip HyP3 zip contents to an AOI |
| `insarhub utils select-pairs` | Select pairs from a saved search GeoJSON |
| `insarhub utils plot-network` | Plot interferogram network |
| `insarhub utils slurm` | Generate a SLURM batch script |
| `insarhub utils era5-download` | Download ERA5 weather data for tropospheric correction |

Use `insarhub <command> --help` for full option details, or see the [CLI Reference](https://jldz9.github.io/InSARHub/quickstart/cli/).

## Documentation

[InSARHub documentation](https://jldz9.github.io/InSARHub/)

