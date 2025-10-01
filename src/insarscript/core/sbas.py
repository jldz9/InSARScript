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

#from asf_search import A
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
                 compression: str | None = None,
                 debug = False):
        """ Initialize Mintpy class
        :param workdir: The working directory for mintpy processing
        :param compression: The compression method for output files, default None, options include 'gzip / lzf '
        :param debug: If True, keep intermediate files, default False
        """
       
        self.cfg = readfile.read_template(Path(mintpy.defaults.__file__).parent.joinpath('smallbaselineApp.cfg'))
        self.workdir = Path(workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = self.workdir.joinpath('tmp')
        self.clip_dir = self.workdir.joinpath('clip')
        self.cfgfile = self.workdir.joinpath('mintpy.cfg')
        
        self.cfg['mintpy.compute.numWorker'] = _env['cpu']
        self.cfg['mintpy.compute.cluster'] = 'local'
        self.cfg['mintpy.compute.maxMemory'] = _env['memory']
        if compression is not None:
            self.cfg['mintpy.load.compression'] = compression
        self.debug = debug

    def _cds_authorize(self):
        if self._check_cdsapirc:
           return True
        else: 
            while True:
                self._cds_token = getpass.getpass("Enter your CDS api token at https://cds.climate.copernicus.eu/profile: ")
                cdsrc_path = Path.home().joinpath(".cdsapirc")
                if cdsrc_path.is_file():
                    cdsrc_path.unlink()
                cdsrc_entry = f"\nurl: https://cds.climate.copernicus.eu/api\nkey: {self._cds_token}"
                with open(cdsrc_path, 'a') as f:
                    f.write(cdsrc_entry)
                    print(f"{Fore.GREEN}Credentials saved to {cdsrc_path}.\n")
                try:
                    tmp = (Path.home().joinpath(".cdsrc_test")).mkdir(exist_ok=True)
                    pyaps3.ECMWFdload(['20200601','20200901'], hr='14', filedir=tmp, model='ERA5', snwe=(30,40,120,140))
                    shutil.rmtree(tmp)
                    print(f"{Fore.GREEN}Authentication successful.\n")
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401:
                        print(f'{Fore.RED} Authentication Failed please check your token')
                break
            
    def _check_cdsapirc(self):
        """Check if .cdsapirc token exist under home directory."""
        cdsapirc_path = Path.home().joinpath('.cdsapirc')
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
    def modify_network(self, 
                    tempBaseMax : int | None = None,
                    perpBaseMax : int | None = None,
                    connNumMax : int | None = None,
                    startDate : int | None = None,
                    endDate : int | None = None,
                    excludeDates : list[int] | None = None,
                    excludeDate120 : list[int] | None = None,
                    excludeIfgIndex : list[int] | None = None,
                    referenceFile : str | None = None,
                    coherenceBased: str | None = None,
                    minCoherence: float | None = None,
                    areaRatioBased : str | None = None,
                    minAreaRatio: float | None = None,
                    keepMinSpanTree: str | None = None,
                    maskFile: str | None = None,
                    aoiYX: list[str] | None = None,
                    aoiLALO: list[str] | None = None):
    
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.network.{key}'] = value

    def reference_point(self,
                        yx: list[int] | None = None,
                        lalo: list[float] | None = None,
                        maskFile : str | None = None,
                        coherenceFile : str | None = None,
                        minCoherence : float | None = None):
        
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.reference.{key}'] = value
    
    def correct_unwrap_error(self, 
                             method : str | None = None,
                             waterMaskFile : str | None = None,
                             connCompMinArea : float | None = None,
                             numSample: int | None = None,
                             ramp: str | None = None,
                             bridgePtsRadius: int | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.unwrapError.{key}'] = value



    def invert_network(self,
                       weightFunc : str | None = None,
                       waterMaskFile : str | None = None,
                       minNormVelocity : str | None = None,
                       maskDataset : str | None = None,
                       maskThreshold : float | None = None,
                       minRedundancy : float | None = None,
                       minTempCoh: float | None = None,
                       minNumPixel: int | None = None,
                       shadowMask: str | None = None,):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.networkInversion.{key}'] = value

    def correct_SET(self,
                    solidEarthTides: str | None = None):
        if solidEarthTides is not None and solidEarthTides in ['yes', 'no']:
            self.cfg['mintpy.solidEarthTides'] = solidEarthTides

    def correct_ionosphere(self,
                          method: str | None = None,
                          excludeDate: list[int] | None = None,
                          excludeDate12: list[int] | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.ionosphericDelay.{key}'] = value

    def correct_troposphere(self,
                            method: str | None = None,
                            weatherModel: str | None = None,
                            weatherDir: str | None = None,
                            polyOrder: int | None = None,
                            looks : int | None = None,
                            minCorrelation: float | None = None,
                            gacosDir: str | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.troposphericDelay.{key}'] = value
            if key == 'method' and value == 'pyaps' or key == 'method' and value is None:
                self._cds_authorize()
                
    def deramp(self,
                method: str | None = None,
                maskFile: str | None = None):
        
        if method is not None: 
            self.cfg['mintpy.deramp'] = method
        if maskFile is not None:
            self.cfg['mintpy.deramp.maskFile'] = maskFile

    def correct_topography(self,
                          method: str | None = None,
                          phaseVelocity  : str | None = None,
                          stepDate: str | None = None,
                          excludeDate: list[int] | None = None,
                          pixelwiseGeometry: str | None = None):
        

        kwargs = {k: v for k, v in locals().items() if k != "self" and k != "method" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.topographicResidual.{key}'] = value
        if method is not None and method in ['yes', 'no']:
            self.cfg['mintpy.topographicResidual'] = method

    def residual_RMS(self,
                     maskFile: str | None = None,
                     deramp: str | None = None,
                     cutoff: float | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.residualRMS.{key}'] = value

    def reference_date(self,
                       date : str | int | None = None):
        if date is not None:
            self.cfg['mintpy.referenceDate'] = date

    def velocity(self, 
                 startDate: int | None = None,
                 endDate: int | None = None,
                 excludeDate: str|list[int] | None = None,
                 polynomial: int | None = None,
                 periodic: float| list[float] | None = None,
                 stepDate: int | list[int] | None = None,
                 exp: list[int] | None = None,
                 log: list[int] | None = None,
                 uncertaintyQuantification: str | None = None,
                 timeSeriesCovFile: str | None = None,
                 bootstrapCount: int | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.timeFunc.{key}'] = value

    def geocode(self,
                method: str | None = None,
                SNWE: list[float] | None = None,
                laloStep: list[float] | None = None,
                interpMethod: str | None = None,
                fillValue: float | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" and k != "method" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.geocode.{key}'] = value
        if method is not None and method in ['yes', 'no']:
            self.cfg['mintpy.geocode'] = method

    def config_save(self,
                     kmz: str | None = None,
                     hdfEos5: str | None = None,
                     hdfEos5_update: str | None = None,
                     hdfEos5_subset: str | None = None):
        if kmz is not None and kmz in ['yes', 'no']:
            self.cfg['mintpy.save.kmz'] = kmz
        if hdfEos5 is not None and hdfEos5 in ['yes', 'no']:
            self.cfg['mintpy.save.hdfEos5'] = hdfEos5
        if hdfEos5_update is not None and hdfEos5_update in ['yes', 'no']:
            self.cfg['mintpy.save.hdfEos5.update'] = hdfEos5_update
        if hdfEos5_subset is not None and hdfEos5_subset in ['yes', 'no']:
            self.cfg['mintpy.save.hdfEos5.subset'] = hdfEos5_subset
    
    def config_plot(self,
             method: str | None = None,
             dpi: int | None = None,
             maxMemory: int | None = None):
        kwargs = {k: v for k, v in locals().items() if k != "self" and k != "method" }
        for key, value in kwargs.items():
            if value is not None:
                self.cfg[f'mintpy.plot.{key}'] = value
        if method is not None and method in ['yes', 'no']:
            self.cfg['mintpy.plot'] = method


    def run(self):
        print(f'{Style.BRIGHT}Step 5: Run Timeseries analysis')
        if (self.workdir.joinpath('smallbaselineApp.cfg')).is_file():
            cfg_file = self.workdir.joinpath('smallbaselineApp.cfg')
        else:
            cfg_file = self.workdir.joinpath('mintpy.cfg')
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
        app.run(steps=['load_data', 
                       'modify_network', 
                       'reference_point',
                       'invert_network',
                       'correct_LOD',
                       'correct_SET',
                       'correct_ionosphere',
                       'correct_troposphere',
                       'deramp',
                       'correct_topography',
                       'residual_RMS',
                       'reference_date',
                       'velocity',
                       'geocode', 
                       'google_earth',
                       'hdfeos5'])
        
    def clear(self):
        if not self.debug:
            if self.tmp_dir.is_dir():
                shutil.rmtree(self.tmp_dir)
            if self.clip_dir.is_dir():
                shutil.rmtree(self.clip_dir)
            print('tmp files cleaned')

    def save_gdal(self):
        from mintpy.cli.save_gdal import main as save_gdal_main
        
        inps = [
            (self.workdir.joinpath('velocity.h5')).as_posix()
        ]
        save_gdal_main(inps)


class Hyp3_SBAS(Mintpy):
    def __init__(self, 
                 hyp3_dir: str, 
                 workdir: str | None = None,
                 compression: str | None = None,
                 debug = False):
        
        self.hyp3_dir = Path(hyp3_dir).expanduser().resolve()
        if workdir is None:
            workdir = self.hyp3_dir.as_posix()
       
        super().__init__(workdir=workdir, compression=compression, debug=debug)
        print(f'workdir: {self.workdir}')
        self.useful_keys = ['unw_phase.tif', 'corr.tif', 'lv_theta.tif', 'lv_phi.tif', 'water_mask.tif', 'dem.tif']
        self.deramp(method='linear')
        self.config_plot(method='no')
        self.correct_troposphere()
       
    def unzip_hyp3(self):
        print(f'{Style.BRIGHT}Step 1: Unzip all downloaded hyp3 gamma files')
        hyp3_results = list(self.hyp3_dir.rglob('*.zip'))
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        for zip_file in tqdm(hyp3_results, desc=f"Unzipping hyp3 gamma files"):
            if (self.tmp_dir.joinpath(zip_file.stem)).is_dir():
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
        self.clip_dir.mkdir(parents=True, exist_ok=True)
        clip_files = defaultdict(list)
        for key, files in tqdm(self.useful_files.items(), desc=f'Group', position=0, leave=True):
            if key in [u.split('.')[0] for u in self.useful_keys] and len(files) > 0:
                for file in tqdm(files, desc="Clipping jobs", position=1, leave=False):
                    dst_file = self.clip_dir.joinpath(f'{file.stem}_clip.tif')
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
                    if (self.clip_dir.joinpath(file.name)).is_file():
                        continue
                    shutil.copy(file, self.clip_dir.joinpath(file.name))
        self.clip_files = clip_files
        if not self.debug:
            shutil.rmtree(self.tmp_dir)
    
    def prep_data(self):
        self.unzip_hyp3()
        self.collect_files()
        self.clip_to_overlap()
        self.load_data()

    def load_data(self):
        print(f'{Style.BRIGHT}Step 5: load_data')
        self.cfg['mintpy.load.processor'] = 'hyp3'
        self.cfg['mintpy.load.unwFile'] = (self.clip_dir.joinpath('*_unw_phase_clip.tif')).as_posix()
        self.cfg['mintpy.load.corFile'] = (self.clip_dir.joinpath('*_corr_clip.tif')).as_posix()
        self.cfg['mintpy.load.demFile'] = (self.clip_dir.joinpath('*_dem_clip.tif')).as_posix()
        for key, minpy_key  in zip(['lv_theta.tif', 'lv_phi.tif', 'water_mask.tif'],['mintpy.load.incAngleFile', 'mintpy.load.azAngleFile','mintpy.load.waterMaskFile']) :
            if len(list(self.clip_dir.rglob(f"*_{key.split('.')[0]}_clip.tif"))) >0:
                self.cfg[minpy_key] = self.clip_dir.joinpath(f"*_{key.split('.')[0]}_clip.tif").as_posix()
            else:
                print(f'*_{key} does not exist, will skip in config')
                continue
        
    
    

 