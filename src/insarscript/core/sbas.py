#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import zipfile

from pathlib import Path
from tqdm import tqdm


class Mintpy:
    """SBAS process was mainly supported by MintPy"""

    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
    

    def prep_hyp3_gamma(self):
        # Step 1: Unzip all downloaded hyp3 gamma files
        hyp3_results = self.workdir.glob('*.zip')
        self.tmp_dir = self.workdir/'tmp'
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        for zip_file in tqdm(hyp3_results, desc="Unzipping hyp3 gamma files"):
            print(f'Unzipping {zip_file}')
            # Unzip the file
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(self.tmp_dir)
        
        # Step 2: Collect all necessary files
        useful_files = ['*_unw_phase.tif', '*_corr.tif', '*_lv_theta.tif', '*_lv_phi.tif', '*_water_mask.tif', '*_dem.tif', '*.txt']
        unwrap_files = list(self.tmp_dir.glob('*_unw_phase.tif'))
        corr_files = list(self.tmp_dir.glob('*_corr.tif'))
        lv_theta_files = list(self.tmp_dir.glob('*_lv_theta.tif'))
        lv_phi_files = list(self.tmp_dir.glob('*_lv_phi.tif'))
        water_mask_files = list(self.tmp_dir.glob('*_water_mask.tif'))
        dem_files = list(self.tmp_dir.glob('*_dem.tif'))
        txt_files = [p for p in list(self.tmp_dir.glob('*.txt')) if ".README" not in p.name]
        # Step 2: 

        pass
        