import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import asf_search as asf
from insarscript.core import S1_SLC, select_pairs, Hyp3InSAR
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import numpy as np
import time
'''
a = S1_SLC(
    platform=['Sentinel-1A', 'Sentinel-1B', 'Sentinel-1C'],
    AscendingflightDirection=False,
    bbox = [126.451, 45.272, 127.747, 45.541],
    start='2017-01-01',
    output_dir = '~/S1'
)
results = a.search()

pairs = select_pairs(results[(105,441)])

runner2 = Hyp3InSAR.load('/home/jldz9/S1/batch.json')

batch = runner.submit(pairs)
a.dem()

a.download()
'''
latitude: float | None = None
longitude: float | None = None
bbox: list[float] | None = [45.36, 126.48, 45.54, 126.65]
start_date: str = "2023-01-19"
end_date: str = "2023-01-20"
timezone: str = "auto"

if latitude is not None and longitude is not None:
        lats = list(latitude)
        lons = list(longitude)
if bbox is not None: 
    lats = np.linspace(bbox[0], bbox[2], 3)
    lons = np.linspace(bbox[1], bbox[3], 3)
else:
    raise ValueError("Either latitude and longitude or bbox must be provided.")

responses = []

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
client = openmeteo_requests.Client(session=retry_session)

api_url = "https://archive-api.open-meteo.com/v1/archive"

for lat in lats:
    for lon in lons:

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
            "hourly": "snow_depth"
        }
        response = client.weather_api(api_url, params=params)
        time.sleep(0.5)
        response= response[0].Hourly()

        start = pd.to_datetime(response.Time(), unit="s", utc=True)
        end = pd.to_datetime(response.TimeEnd(), unit="s", utc=True)
        step = pd.Timedelta(seconds=response.Interval())
        snow_depth = response.Variables(0).ValuesAsNumpy()
        df = pd.DataFrame({
            "time_utc": pd.date_range(start=start, end=end, freq=step, inclusive="left"),
            "snow_depth_cm": snow_depth
            }).reset_index(drop=True)
        responses.append(df)
chart = pd.concat(responses, ignore_index=True)