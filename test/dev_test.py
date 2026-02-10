'''
import dash
from dash import html, dcc
import xarray as xr
import holoviews as hv

from holoviews.operation.datashader import datashade

import hvplot.xarray
from holoviews.plotting.plotly.dash import to_dash
from rasterio.transform import from_origin
import numpy as np
import panel as pn
import pandas as pd
import cartopy.crs as ccrs
pn.extension()
hv.extension('bokeh')

from insarscript.utils.postprocess import _crs_from_attrs

# --- 1. Load Data with Xarray ---
# We write a robust loader to handle MintPy's HDF5 structure
def load_mintpy(filepath):
    # Open dataset. MintPy usually puts data in root or 'timeseries' group.
    # We use 'h5netcdf' engine which is very fast.
    ds = xr.open_dataset(filepath, engine="h5netcdf", chunks="auto", backend_kwargs={'phony_dims': 'sort'})
    length = ds.attrs.get('LENGTH', None)
    if length is None:
        try :
            length = ds.dims['dim_1']
        except KeyError:
            try: 
                length = ds.dims['phony_dim_1']
            except KeyError:
                raise ValueError("Cannot determine LENGTH from dataset dimensions.")
    else: 
        length = int(length)
    width = ds.attrs.get('WIDTH', None)
    if width is None:
        try :
            width = ds.dims['dim_2']
        except KeyError:
            try: 
                width = ds.dims['phony_dim_2']
            except KeyError:
                raise ValueError("Cannot determine WIDTH from dataset dimensions.")
    else:
        width = int(width)
    
    # Standardize dimensions to x, y, time
    # MintPy H5 files often imply lat/lon from metadata attributes.
    # If your xarray load doesn't show lat/lon coords, we construct them:
    if 'lat' not in ds.coords:
        attrs = ds.attrs
        # Generate coordinates from metadata (Equation: start + index * step)
        y_coords = float(attrs['Y_FIRST']) + np.arange(length) * float(attrs['Y_STEP'])
        x_coords = float(attrs['X_FIRST']) + np.arange(width) * float(attrs['X_STEP'])
        
        # Assign to dataset
        try:
            ds = ds.rename({'dim_1': 'y', 'dim_2': 'x', 'dim_0': 'time'})
        except ValueError:
            try:
                ds = ds.rename({'phony_dim_1': 'y', 'phony_dim_2': 'x', 'phony_dim_0': 'time'})
            except ValueError:
                raise ValueError("Cannot rename dimensions to lat, lon, time.")
        ds = ds.assign_coords(y=y_coords, x=x_coords)
        transform = from_origin(float(attrs['X_FIRST']), float(attrs['Y_FIRST']), float(attrs['X_STEP']), abs(float(attrs['Y_STEP'])))
        crs = _crs_from_attrs(attrs)
        if crs is None:
            raise ValueError("Cannot determine CRS from dataset attributes.")
        ds.rio.write_crs(crs.to_string(), inplace=True)
        ds.rio.write_transform(transform, inplace=True)
        data_crs = ccrs.epsg(crs._epsg)
        raw_dates = ds['date'].values.astype(str)
        ds['time'] = pd.to_datetime(raw_dates)
    return ds, data_crs

def plot_timeseries(x, y):
        # ... (Keep your plot_timeseries logic exactly the same as before) ...
        # (I will reprint it below just in case)
        
        if x is None or y is None:
            return hv.Div("<div style='color:grey; text-align:center; margin-top:50px'>Click map to view data</div>")

        print(f"🖱️ Click detected: {y:.4f}, {x:.4f}") 
        
        # 1. Get Data (Meters -> Centimeters)
        ts = ds['timeseries'].sel(x=x, y=y, method='nearest').load()
        y_vals_cm = ts.values * 100
        x_vals = ds['time'].values

        # 2. Linear Regression (Velocity)
        df = pd.DataFrame({'date': x_vals, 'disp': y_vals_cm})
        df['days'] = (df['date'] - df['date'].iloc[0]).dt.days
        
        try:
            slope, intercept = np.polyfit(df['days']/365.25, df['disp'], 1)
            vel_label = f"Vel: {slope:.2f} cm/yr"
            y_model = slope * (df['days']/365.25) + intercept
        except:
            vel_label = "Vel: N/A"
            y_model = y_vals_cm

        # 3. Plots
        scatter = hv.Scatter((x_vals, y_vals_cm)).opts(color='#1f77b4', size=6)
        line = hv.Curve((x_vals, y_model)).opts(color='orange', line_width=3)
        
        return (scatter * line).opts(
            title=f"{vel_label} | Lat: {y:.4f} Lon: {x:.4f}",
            ylabel="Displacement (cm)",
            xlabel="Date",
            framewise=True,
            responsive=True,
            height=400,
            show_grid=True
        )

if __name__ == "__main__":
    filepath = '/mnt/c/Users/jldz9/OneDrive/CSU/091725ERDCmeeting/data/Iran/timeseries.h5'
    ds,data_crs = load_mintpy(filepath)
    map_slice = ds['timeseries'].isel(time=-1).hvplot.image(
        x='x', y='y',
        rasterize=True,
        cmap='RdBu_r', 
        symmetric=True,
        geo=True,
        crs=data_crs,
        title="Spatial View"
    )
    import geoviews as gv
    map_view = (gv.tile_sources.OSM * map_slice).opts(
        responsive=True, 
        height=600,
        active_tools=['wheel_zoom', 'tap'],
        tools=['tap', 'wheel_zoom']
    )
    stream = hv.streams.Tap(source=map_slice, x=None, y=None)
    ts_view = hv.DynamicMap(plot_timeseries, streams=[stream])
    layout = pn.Column(
        pn.pane.Markdown("# 🛰️ InSAR Explorer"),
        pn.Row(
            pn.Card(map_view, title="1. Select Pixel", width_policy='max'),
            pn.Card(ts_view, title="2. Time Series", width_policy='max')
        )
    )
   
    pn.serve(layout, port=5006, show=True)
'''
import h5py
import numpy as np
import pandas as pd
import xarray as xr
import holoviews as hv
import panel as pn
import hvplot.xarray
from holoviews.streams import Tap
pn.extension(loading_spinner='dots', loading_color='#00aa41')
filename = '/mnt/c/Users/jldz9/OneDrive/CSU/091725ERDCmeeting/data/Iran/timeseries.h5'
def create_app():
    def load_mintpy(filepath):
        # Open dataset. MintPy usually puts data in root or 'timeseries' group.
        # We use 'h5netcdf' engine which is very fast.
        ds = xr.open_dataset(filepath, engine="h5netcdf", chunks="auto", backend_kwargs={'phony_dims': 'sort'})
        length = ds.attrs.get('LENGTH', None)
        if length is None:
            try :
                length = ds.dims['dim_1']
            except KeyError:
                try: 
                    length = ds.dims['phony_dim_1']
                except KeyError:
                    raise ValueError("Cannot determine LENGTH from dataset dimensions.")
        else: 
            length = int(length)
        width = ds.attrs.get('WIDTH', None)
        if width is None:
            try :
                width = ds.dims['dim_2']
            except KeyError:
                try: 
                    width = ds.dims['phony_dim_2']
                except KeyError:
                    raise ValueError("Cannot determine WIDTH from dataset dimensions.")
        else:
            width = int(width)
        
        # Standardize dimensions to x, y, time
        # MintPy H5 files often imply lat/lon from metadata attributes.
        # If your xarray load doesn't show lat/lon coords, we construct them:
        if 'lat' not in ds.coords:
            attrs = ds.attrs
            # Generate coordinates from metadata (Equation: start + index * step)
            y_coords = float(attrs['Y_FIRST']) + np.arange(length) * float(attrs['Y_STEP'])
            x_coords = float(attrs['X_FIRST']) + np.arange(width) * float(attrs['X_STEP'])
            
            # Assign to dataset
            try:
                ds = ds.rename({'dim_1': 'y', 'dim_2': 'x', 'dim_0': 'time'})
            except ValueError:
                try:
                    ds = ds.rename({'phony_dim_1': 'y', 'phony_dim_2': 'x', 'phony_dim_0': 'time'})
                except ValueError:
                    raise ValueError("Cannot rename dimensions to lat, lon, time.")
            ds = ds.assign_coords(y=y_coords, x=x_coords)
            raw_dates = ds['date'].values.astype(str)
            ds['time'] = pd.to_datetime(raw_dates)
        return ds

    ds = load_mintpy(filename)
    map_plot = ds.timeseries.isel(time=-1).hvplot.image(
        x='x', y='y',
        rasterize=True,  # Handles large data by downsampling view only
        cmap='turbo',
        data_aspect=1,
        frame_height=500,
        title="Projected Deformation Map (Click a Point)"
    )

    tap = Tap(source=map_plot, x=ds.x.mean().item(), y=ds.y.mean().item())

    @pn.depends(tap.param.x, tap.param.y)
    def get_timeseries(x, y):
        # Select data for the clicked pixel
        selection = ds.timeseries.sel(x=x, y=y, method='nearest')
        
        # Plot the full time series for that pixel
        return selection.hvplot.line(
            x='time', 
            grid=True,
            title=f"Full Timeseries at X={x:.1f}, Y={y:.1f}",
            ylabel="Deformation (m)",
            color='red',
            frame_height=300,
            frame_width=600
        )

    return pn.Column(
        pn.pane.Markdown("# MintPy Time Series Explorer"),
        pn.Row(
            pn.Card(map_plot, title="Spatial View"),
            pn.Card(get_timeseries, title="Temporal View")
        )
    )
if __name__ == "__main__":
    pn.serve(create_app, show=True, title="MintPy Dashboard")