### Installaton
You can install the latest available version from Conda:

??? Note
    
    You may want to start with a fresh environment by: 

    ```conda create -n insarscript python=3.12 && conda activate insarscript```

```bash

conda install insarscript -c conda-forge

```
OR 

from pip:
??? Note
    Since GDAL depends on non-Python system libraries, we will add it via conda: 

```bash
pip install insarscript
conda install gdal
```

### Development Setup
InSAR Script is currently under active development, to set up a the latest dev version:

``` bash
git clone https://github.com/jldz9/InSARScript.git
cd InSARScript
conda env create -f environment.yml -n insar_dev
conda activate insar_dev
pip install -e .
```

??? Note

    Or `mamba env create -f environment.yml -n insar_dev` 
    
    if you have [mamba](https://mamba.readthedocs.io/en/latest/installation/mamba-installation.html) installed for faster environment solve




