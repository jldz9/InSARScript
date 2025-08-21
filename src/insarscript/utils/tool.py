#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from pprint import pformat
from types import SimpleNamespace

import tomllib, tomli_w
from box import Box as Config

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent/'config.toml'        
    config_path = Path(config_path)
    if config_path.is_file():
        try:
            with open(config_path, 'rb') as f:
                toml = tomllib.load(f)
                cfg = Config(toml)
                return cfg
        except Exception as e:
                raise ValueError(f"Error loading config file with error {e}, is this a valid config file in TOML format?")
    else:
        raise FileNotFoundError(f"Config file not found under {config_path}")

def gw_dis_quick_look(
    bbox : list[float] = [45.36, 126.48, 45.54, 126.65],
    processor: str = "hyp3",
    year: int | list[int]= [2019,2020]
):
     """
     Quick look for ground displacement due to ground water extration.
     This method will generate a few quick look interferograms:
     4 pairs of year-wide interferograms that cover temporal baseline of ~360 days 
        e.g.: June 2024 - June 2025
     1 pair of season interferogram 
     """
     print("Todo")