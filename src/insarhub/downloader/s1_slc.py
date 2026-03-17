import getpass
import requests
from pathlib import Path

from colorama import Fore
from eof.download import download_eofs

from insarhub.config import S1_SLC_Config
from .asf_base import ASF_Base_Downloader

class S1_SLC(ASF_Base_Downloader):
    name = "S1_SLC"
    description = "Sentinel-1 SLC scene search and download via ASF."
    default_config = S1_SLC_Config

    """
    A class to search and download Sentinel-1 data using ASF Search API."""

    def download(self, save_path: str | None = None, max_workers: int = 3, force_asf: bool = False, download_orbit: bool = False):
        """Download SLC data and optionally associated orbit files.

        Args:
            save_path (str | None): Optional path to save the downloaded files. Defaults to None.
            max_workers (int): Parallel download workers. Defaults to 3.
            force_asf (bool): If True, forces downloading orbit files from ASF instead of CDSE. Defaults to False.
            download_orbit (bool): If True, also downloads orbit files after scenes. Defaults to False.
        """
        super().download(save_path=save_path, max_workers=max_workers)
        if download_orbit:
            self.download_orbit(force_asf=force_asf)

    def download_orbit(self, force_asf: bool = False):
        """Download orbit files for the current search results.

        Orbit files can be downloaded from ASF or Copernicus Data Space Ecosystem (CDSE).
        CDSE typically releases orbit files earlier. Users will be prompted for CDSE credentials
        if not already configured in a `.netrc` file.

        Args:
            force_asf (bool): If True, forces downloading from ASF instead of CDSE. Defaults to False.
        """
        print("""
Orbit files can be downloaded from both ASF and Copernicus Data Space Ecosystem (CDSE) servers. Generally CDSE release orbit files a few hours to days earlier.
To download orbit file from Copernicus Data Space Ecosystem(CDSE). Please ensure you to create an account at https://dataspace.copernicus.eu/ and setup in the .netrc file.
If a .netrc file is not provide under your home directory, you will be prompt to enter your CDSE username and password.
Check documentation for how to setup .netrc file.

IF you wish to download orbit files from ASF and skip CDSE, use .download_orbit(force_asf=True).""")

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

        base_dir = getattr(self, 'download_dir', None) or self.config.workdir
        print("Downloading orbit files for SLCs...")
        for key, results in self.results.items():  # type: ignore[union-attr]
            download_path = Path(base_dir).joinpath(f'p{key[0]}_f{key[1]}')
            download_path.mkdir(parents=True, exist_ok=True)
            for i, result in enumerate(results, start=1):
                print(f"Searching orbit files for {i}/{len(results)}: {result.properties['fileID']}")
                scene_name = result.properties['sceneName']
                print(f"Searching orbit for {scene_name}")
                orbit_kwargs = dict(
                    orbit_dts=[scene_name.replace("__", "_").split("_")[4]],
                    missions=[scene_name.split("_")[0]],
                    save_dir=download_path.as_posix(),
                )
                try:
                    info = download_eofs(**orbit_kwargs, force_asf=force_asf)
                except Exception as e:
                    if not force_asf:
                        print(f"{Fore.YELLOW}CDSE failed ({e}), retrying from ASF...")
                        try:
                            info = download_eofs(**orbit_kwargs, force_asf=True)
                        except Exception as e2:
                            print(f"{Fore.RED}ASF fallback also failed: {e2}")
                            info = []
                    else:
                        print(f"{Fore.RED}Orbit download failed: {e}")
                        info = []
                if len(info) > 0:
                    print(f"{Fore.GREEN}Orbit files for {result.properties['sceneName']} downloaded successfully.")
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

