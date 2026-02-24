Utilities are sets of tools designed to support and streamline InSAR processing workflows.


### Select Pairs 
Select interferogram pairs from ASF search results based on temporal and
    perpendicular baseline criteria.

```python
from insarscript import Downloader
from insarscript.utils import select_pairs 
s1 = Downloader.create('S1_SLC', 
                    intersectsWith=[-113.05, 37.74, -112.68, 38.00],
                    start='2020-01-01', 
                    end='2020-12-31',  
                    relativeOrbit=100, 
                    frame=466, 
                    workdir='path/to/dir')
results = dl.search()

pairs, baselines = select_pairs(search_results=results)

```

::: insarscript.utils.select_pairs
    options:
        members: flase
        heading_level: 0


### Plot Pair Network

Plot selected interferogram pairs SBAS network from select_pairs based on temporal and
    perpendicular baseline criteria. 

```python

from insarscript.utils import plot_pair_network

fig = plot_pair_network(pairs=pairs, B=baselines)
```

Example: 

![networks](fig/ifgs_network.png){:  margin: auto;" }


::: insarscript.utils.plot_pair_network
    options:
        members: flase
        heading_level: 0

### Earth Credit Pool

If user have multiple Earthdata credentials, user may storage it under ~/.credit_pool with format 
```bash
username1:password1
username2:password2
```
then read use:
```python
from isnarscript.utils import earth_credit_pool
ec_pool = earth_credit_pool()
```
You may then pass this into processor for seameless switch across multiple Earthdata credentials

```python
from insarscript import Processor
processor= Processor.create('Hyp3_InSAR', earthdata_credentials_pool=ec_pool, ....)
```

::: insarscript.utils.earth_credit_pool
    options:
        members: flase
        heading_level: 0

### Slurm Job Config

This class encapsulates all parameters needed to generate a SLURM batch script,
    including resource allocation, job settings, environment configuration, and
    execution commands.

```python
from insarscript.utils import Slurmjob_Config
config = SlurmJobConfig(
            job_name="my_analysis",
            time="02:00:00",
            command="python analyze.py"
        )
config.to_script("analysis.slurm")
```

::: insarscript.utils.Slurmjob_Config
    options:
        members: flase
        heading_level: 0

