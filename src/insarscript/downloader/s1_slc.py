import getpass
import requests
from pathlib import Path

from colorama import Fore
from eof.download import download_eofs

from insarscript.config import S1_SLC_Config
from .asf_base import ASF_Base_Downloader

class S1_SLC(ASF_Base_Downloader):
    name = "S1_SLC"
    default_config = S1_SLC_Config

    """
    A class to search and download Sentinel-1 data using ASF Search API."""

    def download(self, save_path: str | None = None, max_workers: int= 3, force_asf: bool = False, download_orbit: bool = False):
        """Download SLC data and optionally associated orbit files.

        This method downloads the primary SLC data using the base downloader functionality.
        If `download_orbit` is True, it will also attempt to download orbit files from either
        ASF or the Copernicus Data Space Ecosystem (CDSE). Users may be prompted to provide
        CDSE credentials if not already configured in a `.netrc` file.

        Args:
            save_path (str | None): Optional path to save the downloaded files. Defaults to None.
            force_asf (bool): If True, forces downloading orbit files from ASF instead of CDSE. Defaults to False.
            download_orbit (bool): If True, attempts to download orbit files. Defaults to False.

        Raises:
            ValueError: If CDSE authentication fails and the user cannot provide valid credentials.
        """
        super().download(save_path=save_path)
        if download_orbit:
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
                        netrc_path = Path.home().joinpath(".netrc")
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
                    scene_name = result.properties['sceneName']
                    print(f"Searching orbit for {scene_name}")
                    scene_info = result.properties['sceneName'].replace("__", "_").split("_")
                    info = download_eofs(
                        orbit_dts=[scene_name.replace("__", "_").split("_")[4]],
                        missions=[scene_name.split("_")[0]],
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

