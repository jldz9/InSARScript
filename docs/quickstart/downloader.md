The InSARScript Downloader module provides a streamlined interface for searching and downloading satellite data.

- **Import downloader**

    Import the Downloader class to access all downloader functionality
```python
from insarscript import Downloader
```

- **View available downloaders**

    List all registered downloader
```python
Downloader.available()
```

## Available Downloaders

### ASF Base Downloader

InSARScript wrapped [asf_search](https://github.com/asfadmin/Discovery-asf_search) as one of its download backends. The `ASF_Base_Downloader` is implemented on top of a reusable base configuration class, which provides the full searching, filtering, and downloading logic of asf_search.

::: insarscript.downloader.asf_base.ASF_Base_Downloader
    options:
        heading_level: 0
        members: false

#### Usage

- **Create downloader with parameters**

    Initialize a downloader instance with search criteria
```python
s1 = Downloader.create('ASF_base_Downloader', 
                        intersectsWith=[-113.05, 37.74, -112.68, 38.00],
                        dataset='SENTINEL-1',
                        instrument='C-SAR',
                        beamMode='IW',
                        polarization=['VV', 'VV+VH'],
                        processingLevel='SLC'
                        start='2020-01-01', 
                        end='2020-12-31',  
                        relativeOrbit=100, 
                        frame=466, 
                        workdir='path/to/dir')
```
OR:
```python
params = {
    "intersectsWith": [-113.05, 37.74, -112.68, 38.00],
    "dataset": "SENTINEL-1",
    "instrument": "C-SAR",
    "beamMode": "IW",
    "polarization": ["VV", "VV+VH"],
    "processingLevel": "SLC",
    "start": "2020-01-01",
    "end": "2020-12-31",
    "relativeOrbit": 100,
    "frame": 466,
    "workdir": "path/to/dir"
}
dl = Downloader.create('ASF_base_Downloader', **params)
```
OR
```python
from insarscript.config import ASF_Base_Config
cfg = ASF_Base_Config(intersectsWith=[-113.05, 37.74, -112.68, 38.00],
                        dataset='SENTINEL-1',
                        instrument='C-SAR',
                        beamMode='IW',
                        polarization=['VV', 'VV+VH'],
                        processingLevel='SLC'
                        start='2020-01-01', 
                        end='2020-12-31',  
                        relativeOrbit=100, 
                        frame=466, 
                        workdir='path/to/dir')
dl = Downloader.create('ASF_base_Downloader', config=cfg)
```

    The base configure `ASF_Base_Config` contains all parameters from asf_search keywords. For detailed descriptions and usage of each parameter, please refer to the [official ASF Search documentation](https://docs.asf.alaska.edu/asf_search/searching/#searching).

    ::: insarscript.config.ASF_Base_Config
        options:
            heading_level: 0
            members: false


- **Search**

    Query the satellite archive and retrieve available scenes matching your criteria
```python
results = dl.search()
```

    ::: insarscript.downloader.ASF_Base_Downloader.search
        options:
            show_source: false
            heading_level: 5

- **Filter**

    Refine existing search results by applying additional constraints
```python
filter_result = dl.filter(start='2020-02-01')
```

    ::: insarscript.downloader.ASF_Base_Downloader.filter
        options:
            show_source: false
            heading_level: 5

- **Reset filter**

    Restore search results to the original unfiltered state
```python
dl.reset()
```
    ::: insarscript.downloader.ASF_Base_Downloader.reset
        options:
            show_source: false
            heading_level: 5

- **Summary**

    Display statistics and overview of current search results
```python
dl.summary()
```
    ::: insarscript.downloader.ASF_Base_Downloader.summary
        options:
            show_source: false
            heading_level: 5

- **View Footprint**

    Visualize geographic coverage of search results on an interactive map
```python
dl.footprint()
```

    ::: insarscript.downloader.ASF_Base_Downloader.footprint
            options:
                show_source: false
                heading_level: 5

- **Download**

    Download all scenes from current search results to local storage
```python
dl.download()
```

    ::: insarscript.downloader.ASF_Base_Downloader.download
        options:
            show_source: false
            heading_level: 5
        

- **DEM Download**

    Download DEM that covers all scenes from current search results to local storatge
```python
dl.dem()
```
    ::: insarscript.downloader.ASF_Base_Downloader.dem
        options:
            show_source: false
            heading_level: 5

### S1_SLC

S1_SLC is a specialized downloader that extends ASF_Base_Downloader, preconfigured specifically for downloading Sentinel-1 SLC data.

::: insarscript.downloader.s1_slc.S1_SLC
    options:
        show_source: true
        heading_level: 0
        members: false

#### Usage

- **Create downloader with parameters**

    Initialize a downloader instance with search criteria
```python
s1 = Downloader.create('S1_SLC', 
                        intersectsWith=[-113.05, 37.74, -112.68, 38.00],
                        start='2020-01-01', 
                        end='2020-12-31',  
                        relativeOrbit=100, 
                        frame=466, 
                        workdir='path/to/dir')
```
OR
```python
params = {
    "intersectsWith": [-113.05, 37.74, -112.68, 38.00],
    "start": "2020-01-01",
    "end": "2020-12-31",
    "relativeOrbit": 100,
    "frame": 466,
    "workdir": "path/to/dir"
}
dl = Downloader.create('S1_SLC', **params)
```
OR
```python
from insarscript.config import S1_SLC_Config
cfg = S1_SLC_Config(intersectsWith= [-113.05, 37.74, -112.68, 38.00],
                    start= "2020-01-01",
                    end= "2020-12-31",
                    relativeOrbit= 100,
                    frame= 466,
                    workdir= "path/to/dir")
dl = Downloader.create('S1_SLC', config=cfg)

```


    The configure `S1_SLC_config` contains pre-defined parameters specifically for Sentinel-1 data. For detailed descriptions and usage of each parameter, please refer to the [official ASF Search documentation](https://docs.asf.alaska.edu/asf_search/searching/#searching).

    ::: insarscript.downloader.s1_slc.S1_SLC_Config
        options:
            heading_level: 0
            members: false


- **Search**

    Query the satellite archive and retrieve available scenes matching your criteria
```python
results = dl.search()
```

    ::: insarscript.downloader.s1_slc.S1_SLC.search
        options:
            show_source: false
            heading_level: 5

- **Filter**

    Refine existing search results by applying additional constraints
```python
filter_result = dl.filter(start='2020-02-01')
```

    ::: insarscript.downloader.s1_slc.S1_SLC.filter
        options:
            show_source: false
            heading_level: 5

- **Reset filter**

    Restore search results to the original unfiltered state
```python
dl.reset()
```
    ::: insarscript.downloader.s1_slc.S1_SLC.reset
        options:
            show_source: false
            heading_level: 5

- **Summary**

    Display statistics and overview of current search results
```python
dl.summary()
```
    ::: insarscript.downloader.s1_slc.S1_SLC.summary
        options:
            show_source: false
            heading_level: 5

- **View Footprint**

    Visualize geographic coverage of search results on an interactive map
```python
dl.footprint()
```

    ::: insarscript.downloader.s1_slc.S1_SLC.footprint
            options:
                show_source: false
                heading_level: 5

- **Download**

    Download all scenes from current search results to local storage
```python
dl.download()
```

    ::: insarscript.downloader.s1_slc.S1_SLC.download
        options:
            show_source: false
            heading_level: 5
        

- **DEM Download**

    Download DEM that covers all scenes from current search results to local storatge
```python
dl.dem()
```
    ::: insarscript.downloader.s1_slc.S1_SLC.dem
        options:
            show_source: false
            heading_level: 5




