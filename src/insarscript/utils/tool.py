#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import getpass
import requests
import time
from collections import defaultdict
from pathlib import Path
from pprint import pformat
from types import SimpleNamespace



import tomllib, tomli_w
import asf_search as asf
from asf_search.exceptions import ASFAuthenticationError
from colorama import Fore
from eof.download import download_eofs
from shapely.geometry import box





class Config(SimpleNamespace):
    """A SimpleNamespace extension that allows for nested dictionaries and attribute access.
        Use for config file to store hyperparameters and other settings for the entire GeoDLKit program
    """
    def __init__(self, **kwargs):
        try:
            converted_kwargs = {k: self._convert(v) for k, v in kwargs.items()}
        except RecursionError:
            raise RecursionError("Recursive reference detected in config data.")
        super().__init__(**converted_kwargs)


    @classmethod
    def from_file(cls, file_path: str) -> 'Config':
        """
        Load a configuration from toml and return a Config object.
        :param file_path: Path to the configuration file.
        :return: Config object with the loaded configuration.
        """
        file_path_lower = file_path.lower()
        if not file_path_lower.endswith('.toml'):
            raise ValueError(f"Configuration file {file_path} is not in TOML format.")
        
        fpth = Path(file_path) 
        if not fpth.is_file(): 
            raise FileNotFoundError(f"Configuration file {file_path} does not exist.")
        
        with open(file_path, 'rb') as f:
            data = tomllib.load(f)
            return cls(**data)

    def _convert(self, value):
        """Convert nested dictionaries to Config."""
        if isinstance(value, dict):
            return Config(**value)
        if isinstance(value, list):
            # Handle lists of dicts or other nested structures
            return [self._convert(item) for item in value]
        return value
    
    def __setattr__(self, name, value):
        """
        Override setattr to ensure nested Config objects are properly converted.
        """
        super().__setattr__(name, self._convert(value))

    def __getitem__(self, key: str):
        """Allows dictionary-style access (e.g., config['database']['host'])."""
        return getattr(self, key)
    
    def __setitem__(self, key: str, value):
        """Allows dictionary-style item setting (e.g., config['database']['host'] = 'new_host')."""
        self.__setattr__(key, value)

    def __delitem__(self, key: str):
        """Allows dictionary-style item deletion (e.g., del config['database']['host'])."""
        delattr(self, key)

    def __repr__(self) -> str:
        """Returns a pretty-printed representation of the Config object."""
        return f"Config({pformat(self.to_dict())})"

    def update(self, updates: dict):
        """Update the values of the namespace from a dictionary.
        Args:
            update: Update passed into the config, expect Config or dict 
        """
        if isinstance(updates, Config):
            update = updates.to_dict()
        for key, value in updates.items():
            if hasattr(self, key):
                current_attr = getattr(self, key)
                if isinstance(current_attr, Config) and isinstance(value, dict):
                    # Update nested SimpleNamespace
                    current_attr.update(value)
                else:
                    # Overwrite with the new value
                    setattr(self, key, self._convert(value))
            else:
                # Add new attribute if not already present
                setattr(self, key, self._convert(value))
    
    def delete(self, attr_path):
        """
        Delete an attribute from the Config, including nested attributes.

        :param attr_path: A string representing the path to the attribute (e.g., "IO.input").
        """
        keys = attr_path.split(".")
        current = self
        for key in keys[:-1]:  # Navigate to the parent of the attribute
            if hasattr(current, key):
                current = getattr(current, key)
                if not isinstance(current, Config):
                    raise AttributeError(f"'{key}' is not a nested Config object")
            else:
                raise AttributeError(f"Attribute '{key}' not found")

        # Delete the final attribute
        final_key = keys[-1]
        if hasattr(current, final_key):
            delattr(current, final_key)
        else:
            raise AttributeError(f"Attribute '{final_key}' not found in '{current}'")

    def to_dict(self) -> dict | list:
        """Convert the Config to a dictionary."""
        def recursive_convert(obj) -> dict | list:
            if isinstance(obj, Config):
                return {k: recursive_convert(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [recursive_convert(item) for item in obj]
            return obj

        return recursive_convert(self)
    
    def to_file(self, output_path):
        """
        Write the Simplenamespace_ext object to a file in TOML format.

        :param output_path: The path to the file where the TOML data will be written.
        """
        data: dict | list = self.to_dict()
        output_path_lower = output_path.lower()
        if output_path_lower.endswith(".toml"):
            with open(output_path, 'wb') as f:
                tomli_w.dump(data, f) # type: ignore 
        else: 
            raise ValueError(f"Output file {output_path} is not in TOML format. Please use a .toml extension.")

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent/'config.toml'        
    config_path = Path(config_path)
    if config_path.is_file():
        try:
            with open(config_path, 'rb') as f:
                toml = tomllib.load(f)
                cfg = Config(**toml)
                return cfg
        except Exception as e:
                raise ValueError(f"Error loading config file with error {e}, is this a valid config file in TOML format?")
    else:
        raise FileNotFoundError(f"Config file not found under {config_path}")

# pyright: reportAttributeAccessIssue=false
class ASFDownloader: 
    """Simplify searching and downloading satellite data using ASF Search API."""

    def __init__(self,
            dataset: str | list[str] |None = None,
            platform: str | list[str] |None = None,
            instrument: str | None = None, 
            absoluteBurstID: int | list[int] | None = None,
            absoluteOrbit: int | list[int]| None = None,
            asfFrame: int | list[int] | None = None,
            beamMode: str | None = None,
            beamSwath: str | list[str] | None = None,
            campaign: str | None = None,
            maxDoppler: float | None = None,
            minDoppler: float | None    = None,
            maxFaradayRotation: float | None = None,
            minFaradayRotation: float | None = None,
            flightDirection: str | None = None,
            flightLine: str | None = None,
            frame: int | list[int] | None = None,
            fullBurstID: str | list[str] | None = None,
            groupID: str| None = None,
            lookDirection: str | None = None,
            offNadirAngle: float | list[float] |None = None,
            operaBurstID: str | list[str] | None = None,
            polarization: str |list[str] | None = None,
            processingLevel: str | None = None,
            relativeBurstID: str | list[str] | None= None,
            relativeOrbit: int | list[int] | None = None,
            bbox: list[float] | None = None, 
            processingDate: str | None = None,
            start: str | None = None,
            end: str | None = None,
            season: list[int] | None  = None,
            stack_from_id: str | None = None,
            maxResults: int | None = None,
            output_dir: str | None = None,
    ):
        """
        Initialize the Downloader with search parameters. Options was adapted from asf_search searching api. 
        You may check https://docs.asf.alaska.edu/asf_search/searching/ for more info, below only list customized parameters.

        :param bbox: Bounding box coordinates in the format [min_lon, min_lat, max_lon, max_lat]. Will then convert to WKT format. to filled as intersectsWith parameter in asf_search.
        :param output_dir: Directory where downloaded files will be saved. Relative path will be resolved to current workdir.
        """
        kwargs = {k: v for k, v in locals().items() if k != "self" and k != "bbox" and k != "output_dir"}
        if all(v is None for v in kwargs.values()):
            raise ValueError("ASFDownloader was init without any parameters.")
        elif dataset is None and platform is None:
            raise ValueError("ASFDownloader requires at least dataset or plantform parameters to be set.")
        
        if bbox is not None and len(bbox) == 4:
            self.bbox = bbox
            kwargs['intersectsWith'] = box(*bbox, ccw=True).wkt
        else:
            kwargs['intersectsWith'] = None
        
        self.kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

        # Ensure output path is absolute path
        output_dir = Path(output_dir).expanduser().resolve() if output_dir else None # type: ignore
        if output_dir is None:
            self.output_dir = Path.cwd() / "tmp"
        elif not output_dir.is_absolute():
            self.output_dir = Path.cwd() / self.output_dir
        else: 
            self.output_dir = Path(output_dir).expanduser().resolve()
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        print(f"Download directory set to: {self.output_dir}")
        

        print(f"""
This downloader relies on the ASF API. Please ensure you to create an account at https://search.asf.alaska.edu/. 
If a .netrc file is not provide under your home directory, you will be prompt to enter your ASF username and password. 
Check documentation for how to setup .netrc file.\n""")
        self._has_asf_netrc = self._check_netrc(keyword='machine urs.earthdata.nasa.gov')
        if not self._has_asf_netrc:
            while True:
                self._username = input("Enter your ASF username: ")
                self._password = getpass.getpass("Enter your ASF password: ")
                try:
                    self._session = asf.ASFSession().auth_with_creds(self._username, self._password)
                except ASFAuthenticationError:
                    print(f"{Fore.RED}Authentication failed. Please check your credentials and try again.\n")
                    continue
                print(f"{Fore.GREEN}Authentication successful.\n")
                netrc_path = Path.home() / ".netrc"
                asf_entry = f"\nmachine urs.earthdata.nasa.gov\n    login {self._username}\n    password {self._password}\n"
                with open(netrc_path, 'a') as f:
                    f.write(asf_entry)
                print(f"{Fore.GREEN}Credentials saved to {netrc_path}. You can now use the downloader without entering credentials again.\n")
                break
        else:
            self._session = asf.ASFSession()
            print(f"{Fore.GREEN}Credential from .netrc was found for authentication.\n")
       
    def _check_netrc(self, keyword: str) -> bool:
        """Check if .netrc file exists in the home directory."""
        netrc_path = Path.home() / '.netrc'
        if not netrc_path.is_file():            
            print(f"{Fore.RED}No .netrc file found in your home directory. Will prompt login.\n")
            return False
        else: 
            with netrc_path.open() as f:
                content = f.read()
                if keyword in content:
                    return True
                else:
                    print(f"{Fore.RED}no machine name urs.earthdata.nasa.gov found .netrc file. Will prompt login.\n")
                    return False
                
    def search(self):
        """
        Search for data using the ASF Search API with the provided parameters.
        Returns a list of search results.
        """
        print(f"Searching for SLCs....")
        search_opts = {k: v for k, v in self.kwargs.items() if v is not None}
        self.results = asf.search(**search_opts)
        if not self.results:
            print(f"{Fore.YELLOW}No results found for the given search parameters.")
            return
        else:
            print(f"{Fore.GREEN}Search completed successfully. A total of {len(self.results)} results found. Use .download() to download the results.\n")
        grouped = defaultdict(list)
        for result in self.results:
            key = (result.properties['pathNumber'], result.properties['frameNumber'])
            grouped[key].append(result)
        self.results = grouped
        if len(grouped) > 1: 
            print(f"{Fore.YELLOW}The AOI crosses multiple stacks, will try to create subfolders under {self.output_dir} for each stack")
        self.download_dir = self.output_dir.joinpath('data')
        self.download_dir.mkdir(exist_ok=True, parents=True)
        for key in self.results.keys():
            self.download_dir.joinpath(f'p{key[0]}_f{key[1]}').mkdir(exist_ok=True, parents=True)


    def download(self):
        """
        Download the search results to the specified output directory.
        """
        success_count = 0
        failure_count = 0
        if not hasattr(self, 'results'):
            raise ValueError(f"{Fore.RED}No search results found. Please run search() first.")
        
     
        print(f"Downloading results to {self.output_dir}...")
        for key, results in self.results.items():
            download_path = self.download_dir.joinpath(f'p{key[0]}_f{key[1]}')
            print(f'Downloading stacks for path {key[0]} frame {key[1]} to {download_path}')
            for i, result in enumerate(results, start=1):
                print(f"Downloading {i}/{len(results)}: {result.properties['fileID']}")
                try: 
                    start_time = time.time()
                    result.download(path=download_path, session=self._session)
                    elapsed = time.time() - start_time

                    size_mb = result.properties['bytes'] / (1024 * 1024)  # Convert bytes to MB
                    speed = size_mb / elapsed if elapsed > 0 else 0

                    print(f"{Fore.GREEN}✔ Downloaded {size_mb:.2f} MB in {elapsed:.2f} sec ({speed:.2f} MB/s)\n")
                    success_count += 1
                except asf.ASFDownloadError as e:
                    print(f"{Fore.RED}✘ DOWNLOAD FAILED for {result.properties['fileID']}. Reason: {e}")
                    failure_count += 1
                except ConnectionError as e:
                    print(f"{Fore.RED}✘ CONNECTION FAILED for {result.properties['fileID']}. Check your network. Reason: {e}")
                    self.failure_count += 1
                except (IOError, OSError) as e:
                    print(f"{Fore.RED}✘ FILE SYSTEM ERROR for {result.properties['fileID']}. Check permissions for '{self.output_dir}'. Reason: {e}")
                    self.failure_count += 1
                except Exception as e:
                    print(f"{Fore.RED}✘ AN UNEXPECTED ERROR occurred for {result.properties['fileID']}. Reason: {e}")
                    self.failure_count += 1
                finally:
                    print("")
        
class S1_SLC(ASFDownloader):
    """A class to search and download Sentinel-1 data using ASF Search API."""
    platform_dft = [asf.PLATFORM.SENTINEL1A, asf.PLATFORM.SENTINEL1B, asf.PLATFORM.SENTINEL1C]
    instrument_dft = asf.INSTRUMENT.C_SAR
    beamMode_dft = asf.BEAMMODE.IW
    polarization_dft = [asf.POLARIZATION.VV, asf.POLARIZATION.VV_VH]
    processingLevel_dft = asf.PRODUCT_TYPE.SLC
    def __init__(self, 
                 platform: str | list[str] | None = None,
                 AscendingflightDirection: bool = True,
                 bbox: list[float] = [-113.18, 37.77, -112.44, 38.10], 
                 start: str = "2018-01-01", 
                 end: str = "2019-12-31", 
                 output_dir: str ="tmp",
                 download_orbit: bool = False,
                 maxResults: int | None = None
                 ):
        """
        Initialize the S1 Downloader with search parameters.
        :param platform: Select Sentinel-1 platform. Defaults to ['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'].
        :param AscendingflightDirection: If True, will search for ascending flight direction, else will be descending. Defaults to True.
        :param bbox: Bounding box coordinates in the format [min_lon, min_lat, max_lon, max_lat].
        :param start: Start time for the search e.g.,"2023-01-01", You may enter natural language dates, or a date and/or time stamp
        :param end: End time for the search e.g.,"2023-01-31", You may enter natural language dates, or a date and/or time stamp
        :param output_dir: Directory where downloaded files will be saved. Defaults to "tmp".
        :param download_orbit: If True, will download orbit files for SLCs you search. Defaults to False since ISCE2 will download orbit automatically for you during processing.
        :param maxResults: Maximum number of results to return. Defaults to None, which means no limit.
        """
        if platform is None:
           self.platform = self.platform_dft
        if isinstance(platform, str):
            if platform in ['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C']:
                self.platform = platform
        if isinstance(platform, list):
            if all( x in ['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'] for x in platform): 
                self.platform = platform
        else:
            raise ValueError(f"Invalid platform {platform}. Please select from {self.platform_dft}.")
        if AscendingflightDirection:
            self.flightDirection = asf.FLIGHT_DIRECTION.ASCENDING
        else:
            self.flightDirection = asf.FLIGHT_DIRECTION.DESCENDING
        self.bbox = bbox
        self.start = start
        self.end = end
        self.download_orbit = download_orbit
        self.maxResults = maxResults
        
        super().__init__(
                         platform= self.platform,
                         instrument=self.instrument_dft,
                         beamMode=self.beamMode_dft,
                         flightDirection=self.flightDirection,
                         polarization=self.polarization_dft,
                         processingLevel=self.processingLevel_dft,
                         bbox=bbox, 
                         start=self.start, 
                         end=self.end, 
                         output_dir=output_dir,
                         maxResults=self.maxResults)
    def search(self):
        super().search()

    def download(self, force_asf: bool = False):
        super().download()
        if self.download_orbit:
            print(f"""
Orbit files can be downloaded from both ASF and Copernicus Data Space Ecosystem (CDSE) servers. Generally CDSE release orbit files a few hours to days earlier.
To download orbit file from Copernicus Data Space Ecosystem(CDSE). Please ensure you to create an account at https://dataspace.copernicus.eu/ and setup in the .netrc file.
If a .netrc file is not provide under your home directory, you will be prompt to enter your CDSE username and password. 
Check documentation for how to setup .netrc file.\n
IF you wish to download oribit files from ASF and skip CDSE, use .download(forceasf=True).""")
            self._has_cdse_netrc = self._check_netrc(keyword='machine dataspace.copernicus.eu')
            if self._has_cdse_netrc:
                print(f"{Fore.GREEN}Credential from .netrc was found for authentication.\n")
            else: 
                while True:
                    self._cdse_username = input("Enter your CDSE username: ")
                    self._cdse_password = getpass.getpass("Enter your CDSE password: ")
                    if not self._check_cdse_credentials(self._cdse_username, self._cdse_password): 
                        print(f"{Fore.RED}Authentication failed. Please check your credentials and try again.\n")
                        continue
                    else:
                        print(f"{Fore.GREEN}Authentication successful.\n")
                        netrc_path = Path.home() / ".netrc"
                        cdse_entry = f"\nmachine dataspace.copernicus.eu\n    login {self._cdse_username}\n    password {self._cdse_password}\n"
                        with open(netrc_path, 'a') as f:
                            f.write(cdse_entry)
                        print(f"{Fore.GREEN}Credentials saved to {netrc_path}. You can now download orbit from CDSE without entering credentials again.\n")
                        break
            print(f"Downloading orbit files for SLCs...")
            for key, results in self.results.items():
                download_path = self.download_dir.joinpath(f'p{key[0]}_f{key[1]}')
                for i, result in enumerate(results, start=1):
                    print(f"Searching orbit files for {i}/{len(results)}: {result.properties['fileID']}")
                    scene_info = result.properties['sceneName'].replace("__", "_").split("_")
                    info = download_eofs(
                        orbit_dts = [scene_info[4]],
                        missions=[scene_info[0]],
                        save_dir=download_path.as_posix(),
                        force_asf=force_asf
                    )
                    if len(info) > 0:
                        print(f"{Fore.GREEN}Orbit files for {result.properties['sceneName']}downloaded successfully.")
                    else:
                        print(f"{Fore.YELLOW}No orbit files found for the given parameters.")
    
    def _check_cdse_credentials(self, username: str, password: str) -> bool:
        url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": "cdse-public",
            "username": username,
            "password": password
        }
        resp = requests.post(url, data=data)
        return resp.status_code == 200 and "access_token" in resp.json()
#TODO filter different frame and path