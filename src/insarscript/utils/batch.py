import cdsapi
import numpy as np
import multiprocessing
import json
import time
import re
import zipfile
import rasterio
from rasterio.warp import transform_bounds
import logging

from colorama import Fore
from osgeo import gdal
from pathlib import Path
from tqdm import tqdm

from insarscript import Downloader, Processor
from insarscript.utils import select_pairs
def hyp3_insar_batch_check(
        root_dir: str,
        download : bool = False,
        retry : bool = False,
        earthdata_credentials_pool: dict | None = None
):
    """
    Download a batch of hyp3 files from a directory.

    """
    batch_path = Path(root_dir).expanduser().resolve()
    json_files = batch_path.rglob('*.json')

    for file in json_files:
        job = Processor.create('Hyp3_InSAR', saved_job_path=file, earthdata_credentials_pool=earthdata_credentials_pool)
        b = json.loads(file.read_text())
        print(f"Overview for job {Path(b['out_dir'])}")
        if not download :
            batchs = job.refresh()
        if download :
            job.download()
        if retry and len(job.failed_jobs)>0:
            job.retry()

def dis_scan(
    results: dict | None = None,
    bbox : list[float] = [126.451, 45.272, 127.747, 45.541],
    start: str= '2020-01-01',
    end : str = '2020-12-31',
    flightDirection: str = 'ASCENDING', # or DESCENDING
    downloader: str = "S1_SLC",
    processor: str = "Hyp3_InSAR",
    output_dir = "out",
    earthdata_credentials_pool: dict | None = None
):
    """
    Quick look for slow ground displacement.
    This method will generate quick overlook through given area
    :param results: The search result from ASF search output from ASFDownloader, should be a dict with {(path, frame): [asf_search.Products..,asf_search.Products..]}, if the result was provided, this program will skip searching process
    :param bbox: The bounding box to search for SLCs, in [minLon, minLat, maxLon, maxLat] format
    :param scenes: A list of (path, frame) tuples to limit the search
    :param start: The start date for searching SLCs, in 'YYYY-MM-DD' format
    :param end: The end date for searching SLCs, in 'YYYY-MM-DD
    :param AscendingflightDirection: True for ascending, False for descending
    :param processor: The processor to use, "hyp3" or "ISCE"
    :param output_dir: The output directory to save results
    :param credit_pool: The Earthdata credit pool for Hyp3 processor, a dict with {username: password}
    """
    result_slc = {}
    output_dir = Path(output_dir).joinpath('dis_scan').expanduser().resolve()
    if results is not None and isinstance(results, dict):
        result_slc = results
    else:
        slc = Downloader.create(downloader, 
                                bbox=bbox, 
                                start=start, 
                                end=end, 
                                flightDirection=flightDirection)
        
        result_slc = slc.search()

    pairs = select_pairs(
            result_slc,
            dt_targets=(12,24,36,48,72),
            dt_tol=3,
            dt_max=120, 
            pb_max=200,
            min_degree=3,
            max_degree=5,
            force_connect=True
            )
    for key, pair in tqdm(pairs.items(), desc=f'Working on batch', position=0, leave=True):
        if len(pair) <= 10:
            print(f"{Fore.YELLOW}Not enough pairs found for a decent displacement analysis for Path{key[0]} Frame{key[1]}, skip the sence.")
            continue
        slc_path = output_dir.joinpath(f"quicklook_p{key[0]}f{key[1]}")
        slc_path.mkdir(parents=True, exist_ok=True)
        
        job =Processor.create(processor,
            pairs=pair,
            out_dir=slc_path.as_posix(),
            earthdata_credentials_pool=earthdata_credentials_pool)
        job.submit()
        job.save(slc_path.joinpath(f"quicklook_hyp3_p{key[0]}f{key[1]}.json").as_posix())
        print(f"Submitted long job for Path{key[0]} Frame{key[1]}, Job file saved under {slc_path.as_posix()+f'/hyp3_long_p{key[0]}f{key[1]}.json'}")
        time.sleep(1)

class ERA5Downloader:
    """
    A class to handle batch downloading of ERA5 weather data for InSAR processing,
    formatted specifically for MintPy compatibility.
    """
    
    PRESSURE_LEVELS = [
        '1', '2', '3', '5', '7', '10', '20', '30', '50', '70', '100', '125', '150', 
        '175', '200', '225', '250', '300', '350', '400', '450', '500', '550', '600', 
        '650', '700', '750', '775', '800', '825', '850', '875', '900', '925', '950', 
        '975', '1000'
    ]

    def __init__(self, output_dir, num_processes=3, max_retries=3):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.num_processes = num_processes
        self.max_retries = max_retries
        
        # Internal client holder for workers
        self._worker_client = None

    @staticmethod
    def _get_round_hour(time_str):
        """Rounds HHMMSS to the nearest whole hour."""
        h = int(time_str[0:2])
        m = int(time_str[2:4])
        s = int(time_str[4:6])

        if m > 30 or (m == 30 and s > 0):
            h += 1
        if h == 24:
            h = 0
        return f"{h:02d}"

    @staticmethod
    def _calculate_snwe(snwe, min_buffer=2, step=10):
        """Calculates buffered bounding box in multiples of 'step'."""
        def ceil2multiple(x, s):
            return x if x % s == 0 else x + (s - x % s)

        def floor2multiple(x, s):
            return x - x % s

        s_orig, n_orig, w_orig, e_orig = snwe
        S = np.floor(min(s_orig, n_orig) - min_buffer)
        N = np.ceil(max(s_orig, n_orig) + min_buffer)
        W = np.floor(min(w_orig, e_orig) - min_buffer)
        E = np.ceil(max(w_orig, e_orig) + min_buffer)

        if step > 1:
            S, W = floor2multiple(S, step), floor2multiple(W, step)
            N, E = ceil2multiple(N, step), ceil2multiple(E, step)

        return (int(S), int(N), int(W), int(E))

    @staticmethod
    def _get_mintpy_filename(output_dir, day, hr, snwe):
        """Generates MintPy-compliant filename: ERA5_S10_N20_W120_E110_YYYYMMDD_HH.grb"""
        s, n, w, e = snwe
        def fmt(val):
            return f"{'S' if val < 0 else 'N'}{abs(val)}" if val == s or val == n \
                   else f"{'W' if val < 0 else 'E'}{abs(val)}"
        
        # Note: MintPy logic often uses N/S for lat and W/E for lon
        area_str = f"_{fmt(s)}_{fmt(n)}_{fmt(w)}_{fmt(e)}"
        return Path(output_dir) / f"ERA5{area_str}_{day}_{hr}.grb"

    def _prepare_cds_payload(self, day, hr, snwe_tuple):
        """Formats the dictionary for the CDS API request."""
        S, N, W, E = snwe_tuple
        return {
            'product_type': ['reanalysis'],
            'variable': ['geopotential', 'temperature', 'specific_humidity'],
            'year': [day[0:4]],
            'month': [day[4:6]],
            'day': [day[6:8]],
            'time': [f'{hr}:00'],
            'pressure_level': self.PRESSURE_LEVELS,
            'data_format': 'grib',
            'area': [N, W, S, E],  # CDS format: North, West, South, East
        }

    @classmethod
    def _worker_init(cls):
        """Initializer for multiprocessing pool to create a per-process CDS client."""
        global _client
        _client = cdsapi.Client(progress=False, quiet=True)
        logger = logging.getLogger('cdsapi')
        logger.setLevel(logging.WARNING)

    @staticmethod
    def _download_worker(task_info):
        """The actual download function executed by the worker process."""
        global _client
        dataset = task_info['dataset']
        dest_path = task_info['dest_path']
        max_retries = task_info['max_retries']

        for attempt in range(1, max_retries + 1):
            try:
                result = _client.retrieve('reanalysis-era5-pressure-levels', dataset)
                result.download(dest_path)
                return Path(dest_path).name
            except Exception as e:
                if attempt == max_retries:
                    return f"ERROR: {dest_path} failed after {max_retries} attempts: {str(e)}"
                time.sleep(min(60, 5 * attempt))

    def download_batch(self, batch_dir):
        """
        Scans a directory for Hyp3 jobs (zip files), determines required ERA5 
        extents/dates, and downloads missing data.
        """
        batch_path = Path(batch_dir).expanduser().resolve()
        
        for subfolder in tqdm(list(batch_path.iterdir()), desc="Folders", position=0):
            if not subfolder.is_dir():
                continue
                
            zip_files = list(subfolder.glob('*.zip'))
            if not zip_files:
                continue

            W, E, N, S = 180, -180, -90, 90
            dates = set()
            valid_files_count = 0

            # 1. Scan Metadata from Zips
            for zip_path in tqdm(zip_files, desc=f"Scanning {subfolder.name[:10]}...", leave=False, position=1):
                try:
                    with zipfile.ZipFile(zip_path, 'r') as z:
                        namelist = z.namelist()
                        
                        # Extract Dates
                        date_match = re.findall(r'(\d{8})T(\d{6})', zip_path.name)
                        for d, t in date_match:
                            dates.add(f'{d}_{self._get_round_hour(t)}')

                        # Extract Spatial Bounds using GDAL Virtual File System
                        dem_file = next((f for f in namelist if '_dem.tif' in f or '_unw_phase.tif' in f), None)
                        if dem_file:
                            vsi_path = f"/vsizip/{zip_path.as_posix()}/{dem_file}"
                            with rasterio.open(vsi_path) as src:
                                l, b, r, t = src.bounds
                                wgs = transform_bounds(src.crs, 'EPSG:4326', l, b, r, t)
                                W, S, E, N = min(W, wgs[0]), min(S, wgs[1]), max(E, wgs[2]), max(N, wgs[3])
                                valid_files_count += 1
                except Exception:
                    continue

            if valid_files_count == 0:
                print(f"{Fore.RED}No geometry found in {subfolder.name}")
                continue

            # 2. Prepare Download Tasks
            snwe_tuple = self._calculate_snwe((S, N, W, E))
            tasks = []
            for date_str in sorted(dates):
                day, hr = date_str.split('_')
                output_path = self._get_mintpy_filename(self.output_dir, day, hr, snwe_tuple)
                
                if output_path.exists():
                    continue

                tasks.append({
                    'dataset': self._prepare_cds_payload(day, hr, snwe_tuple),
                    'dest_path': output_path.as_posix(),
                    'max_retries': self.max_retries
                })

            # 3. Execute Parallel Downloads
            if not tasks:
                print(f"{Fore.GREEN}All files exist for {subfolder.name}")
                continue

            print(f"{Fore.CYAN}Downloading {len(tasks)} files for {subfolder.name}...")
            with multiprocessing.Pool(processes=self.num_processes, initializer=self._worker_init) as pool:
                with tqdm(total=len(tasks), desc="Progress", unit="file", leave=False) as pbar:
                    for result in pool.imap_unordered(self._download_worker, tasks):
                        if result.startswith("ERROR"):
                            pbar.write(f"{Fore.RED}{result}")
                        else:
                            pbar.set_postfix_str(f"Finished: {result}")
                        pbar.update(1)

        print(f"{Fore.MAGENTA}Batch Processing Complete.")



if __name__== "__main__":
    batch_era5_download('~/InSAR/Iran/quick_look', '~/InSAR/ERA5/ERA5')
        
        

    