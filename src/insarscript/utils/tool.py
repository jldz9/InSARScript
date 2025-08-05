#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
from pprint import pformat
from types import SimpleNamespace

import pystac_client, planetary_computer
import tomllib, tomli_w

from insarscript.utils.stac_api import APIS


class Config(SimpleNamespace):
    """A SimpleNamespace extension that allows for nested dictionaries and attribute access.
        Use for config file to store hyperparameters and other settings for the entire GeoDLKit program
    """
    def __init__(self, **kwargs):
        try:
            converted_kwargs = {k: self._convert(v) for k, v in kwargs.items()}
        except RecursionError:
            raise RecursionError("Recursive reference detected in config data.")
        super().__init__(**converted_kwargs)


    @classmethod
    def from_file(cls, file_path: str) -> 'Config':
        """
        Load a configuration from toml and return a Config object.
        :param file_path: Path to the configuration file.
        :return: Config object with the loaded configuration.
        """
        file_path_lower = file_path.lower()
        if not file_path_lower.endswith('.toml'):
            raise ValueError(f"Configuration file {file_path} is not in TOML format.")
        
        fpth = Path(file_path) 
        if not fpth.is_file(): 
            raise FileNotFoundError(f"Configuration file {file_path} does not exist.")
        
        with open(file_path, 'rb') as f:
            data = tomllib.load(f)
            return cls(**data)

    def _convert(self, value):
        """Convert nested dictionaries to Config."""
        if isinstance(value, dict):
            return Config(**value)
        if isinstance(value, list):
            # Handle lists of dicts or other nested structures
            return [self._convert(item) for item in value]
        return value
    
    def __setattr__(self, name, value):
        """
        Override setattr to ensure nested Config objects are properly converted.
        """
        super().__setattr__(name, self._convert(value))

    def __getitem__(self, key: str):
        """Allows dictionary-style access (e.g., config['database']['host'])."""
        return getattr(self, key)
    
    def __setitem__(self, key: str, value):
        """Allows dictionary-style item setting (e.g., config['database']['host'] = 'new_host')."""
        self.__setattr__(key, value)

    def __delitem__(self, key: str):
        """Allows dictionary-style item deletion (e.g., del config['database']['host'])."""
        delattr(self, key)

    def __repr__(self) -> str:
        """Returns a pretty-printed representation of the Config object."""
        return f"Config({pformat(self.to_dict())})"

    def update(self, updates: dict):
        """Update the values of the namespace from a dictionary.
        Args:
            update: Update passed into the config, expect Config or dict 
        """
        if isinstance(updates, Config):
            update = updates.to_dict()
        for key, value in updates.items():
            if hasattr(self, key):
                current_attr = getattr(self, key)
                if isinstance(current_attr, Config) and isinstance(value, dict):
                    # Update nested SimpleNamespace
                    current_attr.update(value)
                else:
                    # Overwrite with the new value
                    setattr(self, key, self._convert(value))
            else:
                # Add new attribute if not already present
                setattr(self, key, self._convert(value))
    
    def delete(self, attr_path):
        """
        Delete an attribute from the Config, including nested attributes.

        :param attr_path: A string representing the path to the attribute (e.g., "IO.input").
        """
        keys = attr_path.split(".")
        current = self
        for key in keys[:-1]:  # Navigate to the parent of the attribute
            if hasattr(current, key):
                current = getattr(current, key)
                if not isinstance(current, Config):
                    raise AttributeError(f"'{key}' is not a nested Config object")
            else:
                raise AttributeError(f"Attribute '{key}' not found")

        # Delete the final attribute
        final_key = keys[-1]
        if hasattr(current, final_key):
            delattr(current, final_key)
        else:
            raise AttributeError(f"Attribute '{final_key}' not found in '{current}'")

    def to_dict(self) -> dict | list:
        """Convert the Config to a dictionary."""
        def recursive_convert(obj) -> dict | list:
            if isinstance(obj, Config):
                return {k: recursive_convert(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [recursive_convert(item) for item in obj]
            return obj

        return recursive_convert(self)
    
    def to_file(self, output_path):
        """
        Write the Simplenamespace_ext object to a file in TOML format.

        :param output_path: The path to the file where the TOML data will be written.
        """
        data: dict | list = self.to_dict()
        output_path_lower = output_path.lower()
        if output_path_lower.endswith(".toml"):
            with open(output_path, 'wb') as f:
                tomli_w.dump(data, f) # type: ignore 
        else: 
            raise ValueError(f"Output file {output_path} is not in TOML format. Please use a .toml extension.")

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent/'config.toml'        
    config_path = Path(config_path)
    if config_path.is_file():
        try:
            with open(config_path, 'rb') as f:
                toml = tomllib.load(f)
                cfg = Config(**toml)
                return cfg
        except Exception as e:
                raise ValueError(f"Error loading config file with error {e}, is this a valid config file in TOML format?")
    else:
        raise FileNotFoundError(f"Config file not found under {config_path}")
  
class STAC:
    """Simplify searching and downloading satellite data from various STAC APIs."""
    apis = Config(**APIS)
    def __init__(self,
            api_url: str ,
            collection_id: str,
            bbox: list[float] ,
            datetime_range: str,
            output_dir: str = "downloaded_data",
            cloud_cover_mas: int = 10,
            sign_item_func=None,
    ):
        """
        Connects to a STAC API, searches for data, and downloads the first available visual asset.

        Args:
            api_url (str): The URL of the STAC API.
            collection (str): The ID of the data collection to search (e.g., 'sentinel-2-l2a').
            bbox (list): The bounding box [lon_min, lat_min, lon_max, lat_max].
            datetime_range (str): The date range in 'YYYY-MM-DD/YYYY-MM-DD' format.
            output_dir (str, optional): Directory to save downloaded files. Defaults to "downloaded_data".
            cloud_cover_max (int, optional): Maximum allowed cloud cover. Defaults to 10.
            sign_item_func (callable, optional): A function to sign the item for download (e.g., for Planetary Computer).
        """
        self.api_url = api_url
        self.collection_id = collection_id
        self.bbox = bbox
        self.datetime_range = datetime_range
        self.output_dir = output_dir
        self.cloud_cover_max = cloud_cover_mas
        self.sign_item_func = sign_item_func

        # Initialize the STAC client
        self.client = pystac_client.Client.open(self.api_url)
        
        # Ensure output directory exists
        if self.output_dir == 'downloaded_data':
            self.output_dir = Path.cwd() / self.output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def list_apis(cls):
        """List available STAC APIs."""
        return {name: api.url for name, api in cls.apis.__dict__.items() if not name.startswith('_')}
    
    @classmethod
    def planetary_computer(cls,
                           collection_id):
        """Get the Microsoft Planetary Computer STAC API."""
        return cls.apis.planetary_computer


