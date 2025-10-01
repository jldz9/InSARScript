
### **Install**
InSAR Script is currently under active development. You can install the latest available version directly from Conda:

!!! Note
    
    You may want to start with a fresh environment by: 

    ```conda create -n insarscript python=3.12 && conda activate insarscript```

```bash

conda install jldz9::insarscript -c conda-forge

```

### **Development Setup**
To set up a development environment for the latest dev version, clone the repository and create the Conda environment: : 


``` bash
git clone https://github.com/jldz9/InSARScript.git
cd InSARScript
conda env create -f environment.yml -n insar_dev

```

!!! Note

    Or `mamba env create -f environment.yml -n insar_dev` 
    
    if you have [mamba](https://mamba.readthedocs.io/en/latest/installation/mamba-installation.html) installed for faster environment solve

This will create a Conda environment named insar_dev, which includes all dependencies required for development.


### **Account Setup**

This program requires multiple online accounts for full functionality. Registration for these accounts is completely free.

#### [NASA Earthdata](https://urs.earthdata.nasa.gov/)

This account is required for searching satellite scenes, downloading DEMs and orbit files, and submitting online interferogram processing jobs.

Once the registration is complete create a file named `.netrc` under your home directory if not exist and add 
```bash
machine urs.earthdata.nasa.gov
    login Your_Earthdata_username
    password Your_Earthdata_password
```
`OR`

The program will prompts for login on first use.<br><br>



#### [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)

This account is required for downloading orbit files, the release of orbit files on this website is faster than NASA earthdata for couple hours to days. 

Once the registration is complete create a file named `.netrc` under your home directory if not exist and add 

```bash 
machine dataspace.copernicus.eu
    login Your_CDSE_username
    password Your_CDSE_password 

```

`OR` 

The program will prompts for login on first use.<br><br>

#### [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)

This account is required to perform tropospheric correction using PyAPS.

Once the registration is complete create a file named `.cdsapirc` under your home directory if not exist and add
you [API Token](https://cds.climate.copernicus.eu/how-to-api):

```bash
url: https://cds.climate.copernicus.eu/api
key: your-personal-access-token
```
