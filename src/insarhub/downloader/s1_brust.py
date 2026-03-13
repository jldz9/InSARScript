import getpass
import requests
from pathlib import Path

from colorama import Fore
from eof.download import download_eofs


from insarhub.config import S1_Burst_Config
from .asf_base import ASF_Base_Downloader

class S1_Burst(ASF_Base_Downloader):
    name = "S1_Burst"
    description = "Sentinel-1 Burst scene search and download via ASF."
    default_config = S1_Burst_Config

    """
    A class to search and download Sentinel-1 burst data using ASF Search API."""