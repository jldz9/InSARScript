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



def hyp3_batch_check(
        batch_files_dir: str,
        download : bool = False,
        retry : bool = False,
        earthdata_credentials_pool: dict | None = None
):
    """
    Download a batch of hyp3 files from a directory.

    """
    batch_path = Path(batch_files_dir).expanduser().resolve()
    json_files = batch_path.rglob('*.json')

    for file in json_files:
        job = Hyp3_InSAR_Processor.load(file, earthdata_credentials_pool=earthdata_credentials_pool)
        b = json.loads(file.read_text())
        print(f"Overview for job {Path(b['out_dir'])}")
        if not download :
            batchs = job.refresh()
        if download :
            job.download()
        if retry and len(job.failed_jobs)>0:
            job.retry()

def quick_look_dis(
    results: dict | None = None,
    bbox : list[float] = [126.451, 45.272, 127.747, 45.541],
    scenes: list[tuple[int, int]] | None = None,
    start: str= '2020-01-01',
    end : str = '2020-12-31',
    AscendingflightDirection: bool = True,
    processor: str = "hyp3",
    output_dir = "out",
    credit_pool: dict | None = None
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
    output_dir = Path(output_dir).joinpath('quick_look').expanduser().resolve()
    if results is not None and isinstance(results, dict):
        result_slc = results
    elif scenes is not None and isinstance(scenes, list):
        for (path, frame) in scenes:
            print(f"Searching for Path {path} Frame {frame} ...")
            slc = S1_SLC(
                AscendingflightDirection=AscendingflightDirection,
                bbox=None,
                start=start,
                end=end,
                output_dir=output_dir.as_posix(),
                path = path,
                frame = frame
            )
            result_slc.update(slc.search())
    else:
        slc = S1_SLC(
            AscendingflightDirection=AscendingflightDirection,
            bbox=bbox,
            start=start,
            end=end,
            output_dir=output_dir.as_posix(),
        )
        result_slc = slc.search()

    pairs = select_pairs(
            result_slc,
            dt_targets=(12,24,36,48,72,96),
            dt_tol=3,
            dt_max=120, 
            pb_max=200,
            min_degree=3,
            max_degree=5,
            force_connect=True
            )
    for key, pair in tqdm(pairs.items(), desc=f'Submiting Jobs', position=0, leave=True):
        if len(pairs) <= 10:
            print(f"{Fore.YELLOW}Not enough pairs found for a decent displacement analysis for Path{key[0]} Frame{key[1]}, skip the sence.")
            continue
        slc_path = output_dir.joinpath(f"quicklook_p{key[0]}f{key[1]}")
        slc_path.mkdir(parents=True, exist_ok=True)
        
        if processor == "hyp3":
            print("---------Using HyP3 online processor-----------")
            job = Hyp3_InSAR_Processor(
                pairs=pair,
                out_dir=slc_path.as_posix(),
                earthdata_credentials_pool=credit_pool
            )
            job.submit()
            job.save(slc_path.joinpath(f"quicklook_hyp3_p{key[0]}f{key[1]}.json").as_posix())
            print(f"Submitted long job for Path{key[0]} Frame{key[1]}, Job file saved under {slc_path.as_posix()+f'/hyp3_long_p{key[0]}f{key[1]}.json'}")
            time.sleep(1)

        elif processor == "ISCE":
            print("ISCE processor is not yet implemented, please use Hyp3.")


PRESSURE_LEVELS = [
    '1', '2', '3', '5', '7', '10', '20', '30', '50', '70', '100', '125', '150', 
    '175', '200', '225', '250', '300', '350', '400', '450', '500', '550', '600', 
    '650', '700', '750', '775', '800', '825', '850', '875', '900', '925', '950', 
    '975', '1000'
]
client = None

def _set_global_client():
    global client
    if not client:
        client = cdsapi.Client(progress = False, quiet=True)
        logger = logging.getLogger('cdsapi')
        logger.setLevel(logging.WARNING)

def _cdsapi_worker(dataset, max_retrys=3):
    """
    Worker to retrieve and download ERA5 with automatic retry.
    Works safely inside multiprocessing.
    """

    for attempt in range(1, max_retrys + 1):
        try:
            result = client.retrieve('reanalysis-era5-pressure-levels', dataset)
            result.download(dataset['file_name'])
            return Path(dataset['file_name']).name
    
        except Exception as e:
            err_msg = str(e)
            if attempt == max_retrys:
                return f"ERROR (max retries reached): {err_msg}"
            wait = min(60, 5 * attempt)
            time.sleep(wait)
            
        
def _get_round_hour(time_str):
    
        """
        Input: "023505" (HHMMSS)
        Output: Integer Hour (e.g., 3)
        Logic: Rounds to nearest hour. > 30m rounds up.
        """
        h = int(time_str[0:2])
        m = int(time_str[2:4])
        s = int(time_str[4:6])

        if m > 30 or (m == 30 and s > 0):
            h += 1
            
        if h == 24:
            h = 0
            
        return f"{h:02d}"

def _get_snwe(snwe, min_buffer=2, step=10):
    # utils sub-functions
    def ceil2multiple(x, step=10):
        """Given a number x, find the smallest number in multiple of step >= x."""
        # assert isinstance(x, INT_DATA_TYPES), f'input number is not int: {type(x)}'
        if x % step == 0:
            return x
        else:
            return x + (step - x % step)

    def floor2multiple(x, step=10):
        """Given a number x, find the largest number in multiple of step <= x."""
        # assert isinstance(x, INT_DATA_TYPES), f'input number is not int: {type(x)}'
        return x - x % step

    s, n, w, e = snwe
    # lat/lon0/1 --> SNWE
    S = np.floor(min(s, n) - min_buffer)
    N = np.ceil( max(s, n) + min_buffer)
    W = np.floor(min(w, e) - min_buffer)
    E = np.ceil( max(w, e) + min_buffer)

    # SNWE in multiple of 10
    if step > 1:
        S = floor2multiple(S, step=step)
        W = floor2multiple(W, step=step)
        N = ceil2multiple(N, step=step)
        E = ceil2multiple(E, step=step)

    # return native int format, as cdsapi-0.7.3 does not support numpy.int64
    return (int(S), int(N), int(W), int(E))
    
def _single_dataset(day, hr, snwe):
    # snwe input must be [South, North, West, East]
    # But CDSAPI expects [North, West, South, East]
    S, N, W, E = snwe
    return {
            'product_type'   : ['reanalysis'],
            'variable'       : ['geopotential', 'temperature', 'specific_humidity'],
            'year'           : [f'{day[0:4]}'],
            'month'          : [f'{day[4:6]}'],
            'day'            : [f'{day[6:8]}'],
            'time'           : [f'{hr}:00'],
            'pressure_level' : PRESSURE_LEVELS,
            'data_format'    : 'grib',
            'area'           : [N, W, S, E],  # CDSAPI Order: North, West, South, East
        }

def _mintpy_filename(output_dir, day, hr, snwe):
    """
    Generates filename exactly matching MintPy's get_grib_filenames logic.
    snwe must be integers: (South, North, West, East)
    """
    s, n, w, e = snwe
    area = ''
    # MintPy Logic: Handle S/N and W/E prefixes based on sign
    area += f'_S{abs(s)}' if s < 0 else f'_N{abs(s)}'
    area += f'_S{abs(n)}' if n < 0 else f'_N{abs(n)}'
    area += f'_W{abs(w)}' if w < 0 else f'_E{abs(w)}'
    area += f'_W{abs(e)}' if e < 0 else f'_E{abs(e)}'
    
    filename = f"ERA5{area}_{day}_{hr}.grb"
    return output_dir / filename

def batch_era5_download(batch_dir, ERA5_dir):
    """
    Get ERA5 weather data for a batch of jobs. This should run after Hyp3_SBAS prep_data:
.
    This program will try to locate all json files and assume each work folder contains a Hyp3_InSAR_Processor job file.
    :param batch_dir: The directory containing the batch of jobs.
    :param output_dir: The output directory to save the ERA5 data. dataname format: ERA5_N{S}_N{N}_E{W}_E{E}_{YYYYMMDD}_{HH}.grb
    """
    
    batch_path = Path(batch_dir).expanduser().resolve()
    ERA5_path = Path(ERA5_dir).expanduser().resolve()
    ERA5_path.mkdir(parents=True, exist_ok=True)

    

    for subfolder in tqdm(batch_path.iterdir(), desc="Scanning Subfolders", position=0, leave=True):
        zip_files = list(subfolder.glob('*.zip'))
        W, E, N, S = 180, -180, -90, 90
        dates = set()
        valid_files_count = 0
        for zip_path in tqdm(zip_files, desc="Scanning Metadata", unit="file", position=1, leave=True):
            try:
                with zipfile.ZipFile(zip_path, 'r') as z:
                    namelist = z.namelist()

                    date_match = re.findall(r'(\d{8})T(\d{6})', zip_path.name)
                    if date_match:
                        for d in date_match:
                            dates.add(f'{d[0]}_{_get_round_hour(d[1])}')

                    dem_file = next((f for f in namelist if f.endswith('_dem.tif')), None)
                    if not dem_file:
                        dem_file = next((f for f in namelist if f.endswith('_unw_phase.tif')), None)

                    if dem_file:
                        vsi_path = f"/vsizip/{zip_path.as_posix()}/{dem_file}" #Use GDAL virtual filesystem path
                        with rasterio.open(vsi_path) as src:
                            left, bottom, right, top = src.bounds
                            wgs84_bounds = transform_bounds(src.crs, 'EPSG:4326', left, bottom, right, top)
                            W = min(W, wgs84_bounds[0])
                            S = min(S, wgs84_bounds[1])
                            E = max(E, wgs84_bounds[2])
                            N = max(N, wgs84_bounds[3])
                            valid_files_count += 1
            except Exception:
                # Skip corrupt files silently or log
                continue
        if valid_files_count == 0:
            print(f"{Fore.RED}Could not read geometry from any files under {subfolder.name}.")
            continue
            
        snwe_tuple = _get_snwe((S, N, W, E))
        sorted_dates = sorted(list(dates))
        datasets = []
        for date in sorted_dates:
            day, hr = date.split('_')
            
            # Prepare API request (snwe passed to calculate Area)
            dataset = _single_dataset(day, hr, snwe_tuple)
            
            # Generate Filename (Using NEW MintPy compliant function)
            output_path = _mintpy_filename(ERA5_path, day, hr, snwe_tuple)
            
            dataset['file_name'] = output_path.as_posix()
            
            if output_path.exists():
                print(f"{Fore.YELLOW}ERA5 file already exists: {output_path.name}, skipping download.")
            else:
                datasets.append(dataset)

        if not datasets:
            print(f"{Fore.GREEN}All ERA5 files already exist for {subfolder.name}.")
            continue
        
        
        with multiprocessing.Pool(processes=3, initializer=_set_global_client) as pool:
            with tqdm(total=len(datasets), desc="Downloading ERA5", unit="file") as pbar:
                for result in pool.imap_unordered(_cdsapi_worker, datasets):
                    if str(result).startswith("ERROR"):
                        pbar.write(f"{Fore.RED}{result}")
                    else:
                        pbar.set_postfix_str(f"Last: {result}", refresh=True)
                    pbar.update(1)
        print(f"{Fore.GREEN}\nERA5 for {subfolder.name} download complete.") 
        
if __name__== "__main__":
    batch_era5_download('~/InSAR/Iran/quick_look', '~/InSAR/ERA5/ERA5')
        
        

    