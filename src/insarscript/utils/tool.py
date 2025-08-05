#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import getpass
from pathlib import Path
from pprint import pformat
from types import SimpleNamespace

import tomllib, tomli_w
import asf_search as asf
from asf_search.exceptions import ASFAuthenticationError

from colorama import Fore, Style




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
  
class ASFDownloader:
    """Simplify searching and downloading satellite data using ASF Search API."""

    def __init__(self,
            bbox: list[float] ,
            start_time: str,
            end_time: str,
            output_dir: str = "tmp",
    ):
        """
        Initialize the Downloader with search parameters.
        """
        self.bbox = bbox
        self.start_time = start_time
        self.end_time = end_time
        self.output_dir = Path(output_dir)
        print(f"""
This downloader relies on the ASF API. Please ensure you to create an account at https://search.asf.alaska.edu/. 
If a .netrc file is not found under your home directory, you will be prompted to enter your ASF username and password. 
Check documentation for how to setup .netrc file.\n""")
        self._check_netrc = self._check_netrc()
        if not self._check_netrc:
            while True:
                self._username = input("Enter your ASF username: ")
                self._password = getpass.getpass("Enter your ASF password: ")
                try:
                    self._session = asf.ASFSession().auth_with_creds(self._username, self._password)
                except ASFAuthenticationError:
                    print(f"{Fore.RED}Authentication failed. Please check your credentials and try again.\n")
                    continue
                print(f"{Fore.GREEN}Authentication successful.\n")
                break
        else:
            self._session = asf.ASFSession()
            print(f"{Fore.GREEN}Credential from .netrc was found for authentication.\n")
        # Ensure output directory exists
        if not self.output_dir.is_absolute():
            self.output_dir = Path.cwd() / self.output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        print(f"Download directory set to: {self.output_dir}")

    def _check_netrc(self):
        """Check if .netrc file exists in the home directory."""
        netrc_path = Path.home() / '.netrc'
        if not netrc_path.is_file():            
            print(f"{Fore.RED}No .netrc file found in your home directory. Will prompt login.\n")
            return False
        else: 
            with netrc_path.open() as f:
                content = f.read()
                if 'machine urs.earthdata.nasa.gov' in content:
                    return True
                else:
                    print(f"{Fore.RED}no machine name urs.earthdata.nasa.gov found .netrc file. Will prompt login.\n")
                    return False

    


