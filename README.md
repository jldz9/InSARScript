# InSARScript

InSAR Script is an open-source package designed to support the full InSAR processing pipeline.
The primary goal of this package is to provide a streamlined and user-friendly InSAR processing experience across multiple satellite products.

## Table of Contents
- Installation
- Requirements
- Usage
- Documentation

## Installation 

InSARScript can be installed using Conda:
```bash
conda install insarscript -c conda-forge
```
Pip: 

```bash
Pip install insarscript
conda install gdal
```

From source: 

```bash
git clone https://github.com/jldz9/InSARScript.git
cd InSARScript
conda env create -f environment.yml -n insarscript_dev
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
from insarscript import Downloader
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
from insarscript import Processor
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
from insarscript import Analyzer
```
- View available analyzers
    ```python
    Analyzer.available()
    ```

- Create Analyzer

```python
    analyzer = Analyzer.create('Hyp3_SBAS_Analyzer', workdir="/your/work/dir")
```
- Prepare data

 ```python
    analyzer.prep_data()
```

- Run time-series analysis
 ```python
    analyzer.run()
```

## Documentation 

[InSARScript documentation](https://jldz9.github.io/InSARScript/)

