#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import getpass
import requests
import subprocess
import time
from collections import defaultdict
from pathlib import Path


import asf_search as asf
import contextily as ctx
import dem_stitcher
import matplotlib.pyplot as plt
import rasterio as rio
from asf_search.exceptions import ASFAuthenticationError
from colorama import Fore
from eof.download import download_eofs
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform
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

        :param bbox: Bounding box coordinates in the format [west_lon, south_lat, east_lon, north_lat]. Will then convert to WKT format. to filled as intersectsWith parameter in asf_search.
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

        if len(grouped) == 0:
            raise ValueError(f'{Fore.RED}The search does not return any result, check input parameters or Internet connection')
        
        if len(grouped) > 1: 
            print(f"{Fore.YELLOW}The AOI crosses multiple stacks, you can use .footprint() to see footprints and .pick(path, frame) to specific the stack of scence you would like to download. If .download() will try to create subfolders under {self.output_dir} for each stack")
            self.download_dir = self.output_dir.joinpath('data')
            self.download_dir.mkdir(exist_ok=True, parents=True)
        return self.results
    
    def footprint(self):
        """
        Print the search result footprint and AOI use matplotlib
        """
        if not hasattr(self, 'results'):
            raise ValueError(f"{Fore.RED}No search results found. Please run search() first.")
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        N = len(self.results)
        cmap = plt.cm.get_cmap('hsv', N+1)
        fig, ax = plt.subplots(1, 1, figsize=(10,10))
        geom_aoi = transform(transformer.transform, box(*self.bbox, ccw=True))
        x, y = geom_aoi.exterior.xy
        ax.fill(x, y, color='red')
        minx, miny, maxx, maxy =  geom_aoi.bounds
        label_x_aoi = maxx - 0.01 * (maxx - minx)
        label_y_aoi = maxy - 0.01 * (maxy - miny)
        plt.text(label_x_aoi, label_y_aoi,
             f"AOI",
             horizontalalignment='right', verticalalignment='top',
             fontsize=12, color='red', fontweight='bold',
             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.3'))
        for i, (key, results) in enumerate(self.results.items()):
            geom = transform(transformer.transform, shape(results[0].geometry))
            minx, miny, maxx, maxy = geom.bounds
            label_x = maxx - 0.01 * (maxx - minx)
            label_y = maxy - 0.01 * (maxy - miny)
            plt.text(label_x, label_y,
             f"Path: {key[0]}\nFrame: {key[1]}",
             horizontalalignment='right', verticalalignment='top',
             fontsize=12, color=cmap(i), fontweight='bold',
             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.3'))
            for result in results:
                geom = transform(transformer.transform, shape(result.geometry))
                x, y = geom.exterior.xy
                ax.plot(x, y, color=cmap(i))
        
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        ax.set_axis_off()
        plt.show()
        
    def pick(self, path: int | list[int], frame: int | list[int]):
        """
        Give a path and frame to choose specific stack of scenes
        """
        if isinstance(path, int) and isinstance(frame, int):
            value = self.results.get((path, frame))
            new_dict = defaultdict(list)
            new_dict[(path, frame)].extend(value) #type: ignore
            self.results = new_dict
            return self.results
        elif isinstance(path, list) and isinstance(frame, list):
            new_dict = defaultdict(list)
            for i in path: 
                for j in frame:
                    value = self.results.get((i, j))
                    if value is None: 
                        continue
                    new_dict[(i, j)].extend(value)
            self.results = new_dict
            return self.results
        else: 
            raise ValueError(f"path and frame needs to be under same type, either both int or both list of int")
    def dem(self):
        """Download DEM for co-registration uses"""
        for key, results in self.results.items():
            download_path = self.download_dir.joinpath(f'p{key[0]}_f{key[1]}')
            download_path.mkdir(exist_ok=True, parents=True)
            geom = shape(results[0].geometry)
            west_lon, south_lat, east_lon, north_lat =  geom.bounds
            bbox = [ west_lon, south_lat, east_lon, north_lat]
            X, p = dem_stitcher.stitch_dem(
                bbox, 
                dem_name='glo_30',
                dst_area_or_point='Point',
                dst_ellipsoidal_height=True
            )
            
            with rio.open(download_path/f'dem_p{key[0]}_f{key[1]}.tif', 'w', **p) as ds:
                    ds.write(X,1)
                    ds.update_tags(AREA_OR_POINT='Point')
        return
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
            download_path.mkdir(parents=True, exist_ok=True)
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
                    failure_count += 1
                except (IOError, OSError) as e:
                    print(f"{Fore.RED}✘ FILE SYSTEM ERROR for {result.properties['fileID']}. Check permissions for '{self.output_dir}'. Reason: {e}")
                    failure_count += 1
                except Exception as e:
                    print(f"{Fore.RED}✘ AN UNEXPECTED ERROR occurred for {result.properties['fileID']}. Reason: {e}")
                    failure_count += 1
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
                 bbox: list[float] | None = [-113.18, 37.77, -112.44, 38.10],
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
