
import getpass
import time
from dataclasses import asdict
from dateutil.parser import isoparse
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
from shapely import wkt, plotting
from shapely.ops import transform
from shapely.geometry import shape

from insarscript.core.base import BaseDownloader
from insarscript.core.config import ASF_Base_Config

class ASF_Base_Downloader(BaseDownloader): 
    """
    Simplify searching and downloading satellite data using ASF Search API.
    """
    name = "ASF_base_Downloader"
    default_config = ASF_Base_Config

    def __init__(self, config: ASF_Base_Config | None = None): 
            
        """
        Initialize the Downloader with search parameters. Options was adapted from asf_search searching api. 
        You may check https://docs.asf.alaska.edu/asf_search/searching/ for more info, below only list customized parameters.

        :param bbox: Bounding box coordinates in the format [west_lon, south_lat, east_lon, north_lat]. Will then convert to WKT format. to filled as intersectsWith parameter in asf_search.
        :param output_dir: Directory where downloaded files will be saved. Relative path will be resolved to current workdir.
        """
        super().__init__(config)

        if self.config.dataset is None and self.config.platform is None:
            raise ValueError(f"{Fore.RED}Dataset or platform must be specified for ASF search.")
        
        if self.config.bbox and not self.config.intersectsWith:
            w, s, e, n = self.config.bbox
            self.config.intersectsWith = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))" 
        
        self._asf_authorize()
        
    def _asf_authorize(self):
        print(f"""
This downloader relies on the ASF API. Please ensure you to create an account at https://search.asf.alaska.edu/. 
If a .netrc file is not provide under your home directory, you will be prompt to enter your ASF username and password. 
Check documentation for how to setup .netrc file.\n""")
        self._has_asf_netrc = self._check_netrc(keyword='machine urs.earthdata.nasa.gov')
        if not self._has_asf_netrc:
            while True:
                _username = input("Enter your ASF username: ")
                _password = getpass.getpass("Enter your ASF password: ")
                try:
                    self._session = asf.ASFSession().auth_with_creds(_username, _password)
                except ASFAuthenticationError:
                    print(f"{Fore.RED}Authentication failed. Please check your credentials and try again.\n")
                    continue
                print(f"{Fore.GREEN}Authentication successful.\n")
                netrc_path = Path.home().joinpath(".netrc")
                asf_entry = f"\nmachine urs.earthdata.nasa.gov\n    login {_username}\n    password {_password}\n"
                with open(netrc_path, 'a') as f:
                    f.write(asf_entry)
                print(f"{Fore.GREEN}Credentials saved to {netrc_path}. You can now use the downloader without entering credentials again.\n")
                break
        else:
            self._session = asf.ASFSession()
       
    def _check_netrc(self, keyword: str) -> bool:
        """Check if .netrc file exists in the home directory."""
        netrc_path = Path.home().joinpath('.netrc')
        if not netrc_path.is_file():            
            print(f"{Fore.RED}No .netrc file found in your home directory. Will prompt login.\n")
            return False
        else: 
            with netrc_path.open() as f:
                content = f.read()
                if keyword in content:
                    return True
                else:
                    print(f"{Fore.RED}no machine name {keyword} found .netrc file. Will prompt login.\n")
                    return False
                
    def search(self) -> dict:
        """
        Search for data using the ASF Search API with the provided parameters.
        Returns a list of search results.
        """
        print(f"Searching for SLCs....")
        search_opts = {k: v for k, v in asdict(self.config).items() 
                       if v is not None and k not in ['output_dir', 'name', 'bbox']}
        
        for attempt in range(1, 11):
            try:
                self.results = asf.search(**search_opts)
                break
            except Exception as e:
                print(f"{Fore.RED}Search failed: {e}")
                if attempt == 10:
                    raise
                time.sleep(2 ** attempt)  

        if not self.results:
            raise ValueError(f'{Fore.RED}Search does not return any result, please check input parameters or Internet connection')
        else:
            print(f"{Fore.GREEN} -- A total of {len(self.results)} results found. \n")

        grouped = defaultdict(list)
        for result in self.results:
            key = (result.properties['pathNumber'], result.properties['frameNumber'])
            grouped[key].append(result)
        self.results = grouped
        if len(grouped) > 1: 
            print(f"{Fore.YELLOW}The AOI crosses {len(grouped)} stacks, you can use .summary() or .footprint() to check footprints and .pick((path_frame)) to specific the stack of scence you would like to download. If use .download() directly will create subfolders under {self.config.output_dir} for each stack")
        return grouped
 
    def summary(self, ls=False):
        if not hasattr(self, 'results'):
            self.search()
        count = {key:len(item) for key, item in self.results.items()}
        time_range = {key: (min(isoparse(i.properties['startTime']) for i in item), max(isoparse(i.properties['startTime']) for i in item)) for key, item in self.results.items()}
        for key, item in count.items():
            print(f"Sence: Path {key[0]} Frame {key[1]}, Amount: {item}, time: {time_range[key][0].date()} --> {time_range[key][1].date()}")
            if ls:
                for scene in self.results[key]:
                    print(f"    {scene.properties['sceneName']}  {isoparse(scene.properties['startTime']).date()}")

    def footprint(self, save_path: str | None = None):
        """
        Print the search result footprint and AOI use matplotlib
        
        """
        if not hasattr(self, 'results'):
            self.search()
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        N = len(self.results)
        cmap = plt.cm.get_cmap('hsv', N+1)
        fig, ax = plt.subplots(1, 1, figsize=(10,10))
        geom_aoi = transform(transformer.transform, wkt.loads(self.config.intersectsWith))
        minx, miny, maxx, maxy =  geom_aoi.bounds
        label_x_aoi = maxx - 0.01 * (maxx - minx)
        label_y_aoi = maxy - 0.01 * (maxy - miny)
        plotting.plot_polygon(geom_aoi, ax=ax, edgecolor='red', facecolor='none', linewidth=2, linestyle='--')
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
             f"Path: {key[0]}\nFrame: {key[1]}\nStack: {len(results)}",
             horizontalalignment='right', verticalalignment='top',
             fontsize=12, color=cmap(i), fontweight='bold',
             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.3'))
            for result in results:
                geom = transform(transformer.transform, shape(result.geometry))
                x, y = geom.exterior.xy
                ax.plot(x, y, color=cmap(i))
        
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        ax.set_axis_off()
        if save_path is not None:
            save_path = Path(save_path).expanduser().resolve()
            plt.savefig(save_path.as_posix(), dpi=300, bbox_inches='tight')
            print(f"Footprint figure saved to {save_path}")
        else:
            plt.show()
        
    def pick(self, path_frame = tuple | list[tuple]) -> dict:
        """
        Give a path and frame to choose specific stack of scenes or a list of path and frame, e.g path_frame = [(25,351), (25,352), (25,353)]
        """
        if not hasattr(self, 'results'):
            raise ValueError(f"{Fore.RED}No search results found. Please run search() first.")
        if isinstance(path_frame, tuple):
            new_dict = defaultdict(list)
            value = self.results.get(path_frame)
            new_dict[path_frame].extend(value) #type: ignore
            self.results = new_dict
            return new_dict
        elif isinstance(path_frame, list):
            new_dict = defaultdict(list)
            for p_f in path_frame: 
                value = self.results.get(p_f)
                if value is None: 
                    continue
                new_dict[p_f].extend(value)
            self.results = new_dict
            return new_dict
        else: 
            raise ValueError(f"path and frame needs to be under same type, either both int or both list of int")
    
    def dem(self, save_path: str | None = None):
        """Download DEM for co-registration uses"""
        output_dir = Path(save_path).expanduser().resolve() if save_path else self.config.output_dir

        for key, results in self.results.items():
            download_path = output_dir.joinpath(f'dem',f'p{key[0]}_f{key[1]}')
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
            
            with rio.open(download_path.joinpath(f'dem_p{key[0]}_f{key[1]}.tif'), 'w', **p) as ds:
                    ds.write(X,1)
                    ds.update_tags(AREA_OR_POINT='Point')
        return X, p
    
    def download(self, save_path: str | None = None):
        """
        Download the search results to the specified output directory.
        """
        output_dir = Path(save_path).expanduser().resolve() if save_path else self.config.output_dir

        self.download_dir = output_dir.joinpath('data')
        self.download_dir.mkdir(exist_ok=True, parents=True)
        success_count = 0
        failure_count = 0
        if not hasattr(self, 'results'):
            raise ValueError(f"{Fore.RED}No search results found. Please run search() first.")
        print(f"Downloading results to {output_dir}...")
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
                    print(f"{Fore.RED}✘ FILE SYSTEM ERROR for {result.properties['fileID']}. Check permissions for '{output_dir}'. Reason: {e}")
                    failure_count += 1
                except Exception as e:
                    print(f"{Fore.RED}✘ AN UNEXPECTED ERROR occurred for {result.properties['fileID']}. Reason: {e}")
                    failure_count += 1
                finally:
                    print("")