
This program requires several API accounts for full functionality. Registration for all of these services is completely free.

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
