#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import getpass
import requests
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

import mintpy.defaults
import numpy as np
import rasterio
import pyaps3

from colorama import Fore, Style
from mintpy.utils import readfile
from mintpy.smallbaselineApp import TimeSeriesAnalysis
from osgeo import gdal
from tqdm import tqdm

from insarscript import _env


class Mintpy:
    """SBAS process was mainly supported by MintPy"""

    def __init__(self, 
                 workdir: str,
                 reference_point : list[int] | None=  None,
                 reference_mask: str = "stack", 
                 debug = False):
        self.cfg = readfile.read_template(Path(mintpy.defaults.__file__).parent/'smallbaselineApp.cfg')
        self.workdir = Path(workdir).expanduser().resolve()
        self._cds_authorize()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = self.workdir/'tmp'
        
        self.cfg['mintpy.compute.numWorker'] = _env['cpu']
        self.cfg['mintpy.compute.cluster'] = 'local' #_env['manager']
        self.cfg['mintpy.compute.maxMemory'] = _env['memory']
        self.debug = debug

    def _cds_authorize(self):
        if self._check_cdsapirc:
           return True
        else: 
            while True:
                self._cds_token = getpass.getpass("Enter your CDS api token at https://cds.climate.copernicus.eu/profile: ")
                cdsrc_path = Path.home() / ".cdsapirc"
                if cdsrc_path.is_file():
                    cdsrc_path.unlink()
                cdsrc_entry = f"\nurl: https://cds.climate.copernicus.eu/api\nkey: {self._cds_token}"
                with open(cdsrc_path, 'a') as f:
                    f.write(cdsrc_entry)
                    print(f"{Fore.GREEN}Credentials saved to {cdsrc_path}.\n")
                try:
                    tmp = (Path.home()/".cdsrc_test").mkdir(exist_ok=True)
                    pyaps3.ECMWFdload(['20200601','20200901'], hr='14', filedir=tmp, model='ERA5', snwe=(30,40,120,140))
                    shutil.rmtree(tmp)
                    print(f"{Fore.GREEN}Authentication successful.\n")
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401:
                        print(f'{Fore.RED} Authentication Failed please check your token')
                break
            
    def _check_cdsapirc(self):
        """Check if .cdsapirc token exist under home directory."""
        cdsapirc_path = Path.home() / '.cdsapirc'
        if not cdsapirc_path.is_file():            
            print(f"{Fore.RED}No .cdsapirc file found in your home directory. Will prompt login.\n")
            return False
        else: 
            with cdsapirc_path.open() as f:
                content = f.read()
                if 'key:' in content:
                    return True
                else:
                    print(f"{Fore.RED}no api token found under .cdsapirc. Will prompt login.\n")
                    return False

class Hyp3GAMMA(Mintpy):
    
    def __init__(self, 
                 hyp3_dir: str, 
                 workdir: str | None = None,
                 debug = False):
        
        self.hyp3_dir = Path(hyp3_dir).expanduser().resolve()
        if workdir is None:
            workdir = self.hyp3_dir.as_posix()
        super().__init__(workdir=workdir, debug=debug)
        
        
        self.useful_keys = ['unw_phase.tif', 'corr.tif', 'lv_theta.tif', 'lv_phi.tif', 'water_mask.tif', 'dem.tif']

    def unzip_hyp3(self):
        print(f'{Style.BRIGHT}Step 1: Unzip all downloaded hyp3 gamma files')
        hyp3_results = list(self.hyp3_dir.rglob('*.zip'))
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        for zip_file in tqdm(hyp3_results, desc=f"Unzipping hyp3 gamma files"):
            if (self.tmp_dir/zip_file.stem).is_dir():
                print(f'{Fore.YELLOW}{zip_file.stem} exist, skip')
                continue
            else:
                print(f'{zip_file}')
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(self.tmp_dir)
        
    def collect_files(self):
        print(f'{Style.BRIGHT}Step 2: Collect all necessary files')
        useful_files = defaultdict(list)
        for key in self.useful_keys:
            files = list(self.tmp_dir.rglob(f'*_{key}'))
            if len(files) == 0 and key in ['lv_phi.tif', 'lv_theta.tif']:
                print(f'{Fore.YELLOW}Warning: No *_{key} found from hyp3 product, it is optional but recommended by Mintpy. Use include_look_vectors=True when submit hyp3 jobs to include *_{key} in final product.')
            if len(files) == 0 and key in ['unw_phase.tif', 'corr.tif', 'dem.tif']:
                raise FileNotFoundError(f'{Fore.RED}Error: No {key} found from hyp3 product, it is required for Mintpy processing')
            useful_files[key.split('.')[0]] = files 

        meta = self.tmp_dir.rglob('*.txt')
        meta = [m for m in meta if 'README' not in m.name]
        if len(meta) == 0:
            raise FileNotFoundError(f'{Fore.RED}Error: No metadata .txt file found from hyp3 product, it is required for Mintpy processing')
        useful_files['meta'] = meta
        self.useful_files = useful_files
        print('Complete!')

    def clip_to_overlap(self):
        print(f'{Style.BRIGHT}Step 3: Prepare common overlap using gdal')
        ulx_list, uly_list, lrx_list, lry_list = [], [], [], []
        for f in self.useful_files['dem']:
            ds = gdal.Open(f.as_posix())
            gt = ds.GetGeoTransform() # (ulx, xres, xrot, uly, yrot, yres)
            ulx, uly = gt[0], gt[3]
            lrx, lry = gt[0] + gt[1] * ds.RasterXSize, gt[3] + gt[5] * ds.RasterYSize
            ulx_list.append(ulx)
            uly_list.append(uly)
            lrx_list.append(lrx)
            lry_list.append(lry)
            ds = None
        common_overlap = (max(ulx_list), min(uly_list), min(lrx_list), max(lry_list)) # (ulx, uly, lrx, lry)
        self.common_overlap = common_overlap
        print(f'{Style.BRIGHT}Step 4: Clip all files to common overlap')
        self.clip_dir = self.workdir/'clip'
        self.clip_dir.mkdir(parents=True, exist_ok=True)
        clip_files = defaultdict(list)
        for key, files in tqdm(self.useful_files.items(), desc=f'Group', position=0, leave=True):
            if key in [u.split('.')[0] for u in self.useful_keys] and len(files) > 0:
                for file in tqdm(files, desc="Clipping jobs", position=1, leave=False):
                    dst_file = self.clip_dir/f'{file.stem}_clip.tif'
                    if dst_file.is_file():
                        print(f'{Fore.YELLOW}{dst_file.name} exist, skip')
                        clip_files[key].append(dst_file)
                        continue
                    gdal.Translate(
                        destName= dst_file.as_posix(),
                        srcDS = file.as_posix(),
                        projWin = common_overlap
                    )
                    clip_files[key].append(dst_file)
            elif key == 'meta':
                for file in tqdm(files, desc='Copying metadata'):
                    if (self.clip_dir/file.name).is_file():
                        continue
                    shutil.copy(file, self.clip_dir/file.name)
        self.clip_files = clip_files

    def get_high_coh_mask(self, min_corr = 0.85):
        print(f'{Style.BRIGHT}Step 5: Generate stack-wide high-coherence mask')
        self.mask_file = self.workdir/"stack_corr_mask.tif"
        if self.mask_file.is_file(): 
            print(f'{self.mask_file} exist, skip')

        else:
            clip_corr = sorted(self.clip_files['corr'])
            if len(clip_corr) < 1: 
                raise FileNotFoundError(f"No corr file found under {self.clip_dir}")
            
            with rasterio.open(clip_corr[0]) as src:
                profile = src.profile
                profile.update(dtype=rasterio.uint8, count=1)
                stack = np.zeros((len(clip_corr), src.height, src.width), dtype=np.float32)

            for i, f in tqdm(enumerate(clip_corr), desc="Reading corr masks"):
                with rasterio.open(f) as src: 
                    stack[i] = src.read(1)

            minimal = np.min(stack, axis=0)
            mask = (minimal >= min_corr).astype(np.uint8) 
            with rasterio.open(self.mask_file, "w", **profile) as dst:
                    dst.write(mask,1)
            
    def run(self):
        print(f'{Style.BRIGHT}Step 6: Run Timeseries analysis')
        self.cfg['mintpy.load.processor'] = 'hyp3'
        self.cfg['mintpy.load.unwFile'] = (self.clip_dir/'*_unw_phase_clip.tif').as_posix()
        self.cfg['mintpy.load.corFile'] = (self.clip_dir/'*_corr_clip.tif').as_posix()
        self.cfg['mintpy.load.demFile'] = (self.clip_dir/'*_dem_clip.tif').as_posix()
        if not hasattr(self, 'mask_file'):
            self.cfg['mintpy.reference.maskFile'] = 'auto'
        else:
            self.cfg['mintpy.reference.maskFile'] = self.mask_file.as_posix()
        self.cfg['mintpy.deramp'] = 'linear'
        self.cfg['mintpy.topographicResidual'] = 'yes'
        self.cfg['mintpy.troposphericDelay.method'] = 'pyaps'

        for key, minpy_key  in zip(['lv_theta.tif', 'lv_phi.tif', 'water_mask.tif'],['mintpy.load.incAngleFile', 'mintpy.load.azAngleFile','mintpy.load.waterMaskFile']) :
            if key.split('.')[0] in self.clip_files.keys():
                self.cfg[minpy_key] = self.clip_dir.joinpath(f'*_{key.split('.')[0]}_clip.tif').as_posix()
            else:
                print(f'*_{key} does not exist, will skip in config')
        cfg_file = self.workdir/'mintpy.cfg'
        with cfg_file.open('w') as f:
            for key, value in self.cfg.items():
                if isinstance(value, str):
                    val_str = value
                elif isinstance(value, list):
                    val_str = ','.join(map(str, value))
                else:
                    val_str = str(value)
                f.write(f'{key} = {val_str}\n')
        app = TimeSeriesAnalysis(cfg_file.as_posix(), self.workdir)
        app.open()
        app.run(steps=['load_data', 'modify_network', 'reference_point', 'invert_network','correct_troposphere','deramp','correct_topography','residual_RMS','reference_date','velocity','geocode', 'google_earth'])
    
    def clear(self):
        if not self.debug:
            shutil.rmtree(self.tmp_dir)
            shutil.rmtree(self.clip_dir)
            print('tmp files cleaned')

        