import planetary_computer, pystac_client
from typing import Dict, Any, Optional, Callable

APIS: Dict[str, Dict[str, Any]] = {
    "planetary_computer": {
        "url": "https://planetarycomputer.microsoft.com/api/stac/v1",
        "signer": planetary_computer.sign,
        "description": "Microsoft Planetary Computer: Hosts Sentinel, Landsat, and more."},
    
    "element84": {
        "url": "https://earth-search.aws.element84.com/v1",
        "signer": None,
        "description": "Element 84 (Earth Search on AWS): Hosts Sentinel and Landsat."
    },
    "usgs": {
        "url": "https://stac.earthdata.nasa.gov/api/v1",
        "signer": None,
        "description": "Official USGS STAC API for Landsat, MODIS, etc."
    },
    "google": {
        "url": "https://earthengine-stac.storage.googleapis.com/catalog/catalog.json",
        "signer": None,
        "description": "Google Earth Engine STAC Catalog."
    }
}



