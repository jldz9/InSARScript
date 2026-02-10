
import getpass
import requests
import shutil
from pathlib import Path

import pyaps3
from colorama import Fore, Style
from mintpy.utils import readfile
from mintpy.smallbaselineApp import TimeSeriesAnalysis

from ..core.config import Mintpy_SBAS_Base_Config
from ..core.base import BaseAnalyzer


class Mintpy_Base_Analyzer(BaseAnalyzer):

    name = 'Mintpy_Base_Analyzer'
    default_config = Mintpy_SBAS_Base_Config
    '''
    Base class for Mintpy SBAS analysis. This class provides a template for implementing 
    specific analysis methods using the Mintpy software package.
    '''
    def __init__(self, config: Mintpy_SBAS_Base_Config | None = None):
        super().__init__(config)

        self.workdir = self.config.workdir
        self.tmp_dir = self.workdir.joinpath('tmp')
        self.clip_dir = self.workdir.joinpath('clip')
        self.cfg_path = self.workdir.joinpath('mintpy.cfg')

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
    
    def run(self, steps=None):
        if self.config.troposphericDelay_method == 'pyaps':
            self._cds_authorize()
        self.config.write_mintpy_config(self.cfg_path)

        run_steps = steps or [
            'load_data', 'modify_network', 'reference_point', 'invert_network',
            'correct_LOD', 'correct_SET', 'correct_ionosphere', 'correct_troposphere',
            'deramp', 'correct_topography', 'residual_RMS', 'reference_date',
            'velocity', 'geocode', 'google_earth', 'hdfeos5'
        ]
        print(f'{Style.BRIGHT}{Fore.MAGENTA}Running MintPy Analysis...{Fore.RESET}')
        app = TimeSeriesAnalysis(self.cfg_path.as_posix(), self.workdir.as_posix())
        app.open()
        app.run(steps=run_steps)

    def cleanup(self):
        if self.config.debug:
            print(f"{Fore.YELLOW}Debug mode is enabled. Keeping temporary files at: {self.workdir}{Fore.RESET}")
            return
        print(f"{Fore.CYAN}Step: Cleaning up temporary directories...{Fore.RESET}")

        for folder in [self.tmp_dir, self.clip_dir]:
            if folder.exists() and folder.is_dir():
                try:
                    shutil.rmtree(folder)
                    print(f"  Removed: {folder.relative_to(self.workdir)}")
                except Exception as e:
                    print(f"{Fore.RED}  Failed to remove {folder}: {e}{Fore.RESET}")
                    
        zips = list(self.workdir.glob('*.zip'))
        if zips:
            print(f"{Fore.CYAN}Step: Removing zip archives...{Fore.RESET}")
            for zf in zips:
                try:
                    zf.unlink()
                    print(f"  Removed: {zf.name}")
                except Exception as e:
                    print(f"{Fore.RED}  Failed to remove {zf.name}: {e}{Fore.RESET}")

        print(f"{Fore.GREEN}Cleanup complete.{Fore.RESET}")