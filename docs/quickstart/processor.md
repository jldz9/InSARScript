The InSARScript Processor module provides functionality specifically for interferogram processing.


- **Import processor**

    Import the Processor class to access all dprocessor functionality
```python
from insarscript import Processor
```

- **View available processors**

    List all registered processor
```python
Processor.available()
```

## Available Processors

### Hyp3_InSAR
The HyP3 InSAR processor is a cloud-based processing service provided by the ASF HyP3 system for generating interferograms from Sentinel-1 SAR data.
InSARScript wrapped [hyp3_sdk](https://github.com/ASFHyP3/hyp3-sdk) as one of its process backends. 

The `Hyp3_InSAR` is specificially wrap `insar_job` in hype_sdk to provide InSAR SLC processing workflows. 

::: insarscript.processor.hyp3_insar.Hyp3_InSAR
    options:
        heading_level: 0
        members: false

#### Usage

- **Create Processor with Parameters**

    Initialize a processor instance with search criteria
```python
processor = Processor.create('Hyp3_InSAR', workdir='/your/work/path', pairs=pairs)
```
OR
```python
params = {
    "workdir":'/your/work/path',
    "pairs":pairs,
}
processor = Processor.create('Hyp3_InSAR', **params)
```
OR
```python
from insarscript.config import Hyp3_InSAR_Config
cfg = Hyp3_InSAR_Config(workdir='/your/work/path', pairs=pairs)
processor = Processor.create('Hyp3_InSAR', config=cfg)
```



    ::: insarscript.config.Hyp3_Base_Config
        options:
            members: false
            show_source: false
            heading_level: 0

    ::: insarscript.config.Hyp3_InSAR_Config
        options:
            members: false
            heading_level: 0

- **Submit Jobs**

    Submit InSAR jobs to HyP3 based on the current configuration.

    ```python
    jobs = processor.submit()
    ```


    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.submit
        options:
                members: false
                show_source: false
                heading_level: 5

- **Refresh Jobs**

    Refresh the status of all jobs.

    ```python
    jobs = processor.refresh()
    ```

    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.refresh
        options:
                members: false
                show_source: false
                heading_level: 5

- **Retry Failed Jobs**

    Retry all failed jobs by re-submitting them.

    ```python
    jobs = processor.retry()
    ```

    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.retry
        options:
                members: false
                show_source: false
                heading_level: 5


- **Download Sucessed Jobs**

    Download all succeeded jobs for all users.

    ```python
    processor.download()
    ```

    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.download
        options:
                members: false
                show_source: false
                heading_level: 5

- **Save Current Jobs**

    Save the current job batch information to a JSON file.

    ```python
    processor.save()
    ```

    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.save
        options:
                members: false
                show_source: false
                heading_level: 5
    

- **Watch Jobs**

    Continuously monitor jobs and download completed outputs.

    ```python
    processor.watch()
    ```

    ::: insarscript.processor.hyp3_insar.Hyp3_InSAR.watch
        options:
            members: false
            show_source: false
            heading_level: 5


*[HyP3]: Hybrid Pluggable Processing Pipeline