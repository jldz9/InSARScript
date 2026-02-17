#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import time

from collections import defaultdict
from dateutil.parser import isoparse
from pathlib import Path
from pprint import pformat
from types import SimpleNamespace

import geopandas as gpd
from asf_search.exceptions import ASFSearchError
from asf_search import ASFProduct
from box import Box as Config
from colorama import Fore
from mintpy.utils import readfile
from shapely.geometry import box
from shapely import wkt
from tqdm import tqdm





def select_pairs(search_results: dict[tuple[int,int], list[ASFProduct]],
                dt_targets:tuple[int] =(6, 12, 24, 36, 48, 72, 96) ,
                dt_tol:int=3,
                dt_max:int=120,
                pb_max:int=150,
                min_degree:int=3,
                max_degree:int=999,
                force_connect: bool = True):
    
    """
    Select interfergrom pairs based on temporalBaseline and perpendicularBaseline'
    :param search_results: The list of ASFProduct from asf_search 
    :param dt_targets: The prefered temporal spacings to make interfergrams
    :param dt_tol: The tolerance in days adds to temporal spacings for flexibility
    :param dt_max: The maximum temporal baseline [days]
    :param pb_max: The maximum perpendicular baseline [m]
    :param min_degree: The minimum number of connections
    :param max_degree: The maximum number of connections
    :param force_connect: if connections are less than min_degree with given dt_targets, will force to use pb_max to search for additional pairs. Be aware this could leads to low quality pairs.
    """
    input_is_list = isinstance(search_results, list)
    if input_is_list:
        working_dict = {(0, 0): search_results}
    elif isinstance(search_results, dict):
        working_dict = search_results
    else:
        raise ValueError(f"search_results must be a list or dict, got {type(search_results)}")
    
    pairs_group = defaultdict(list)
    for key, search_result in working_dict.items():
        if not isinstance(working_dict, dict):
            raise ValueError(f'search_results need to be a dict of list of ASFProduct from asf_search, got {type(working_dict)} for key {key}')
        if not input_is_list:
            print(f'{Fore.GREEN}Searching pairs for path {key[0]} frame {key[1]}...')

        prods = sorted(search_result, key=lambda p: p.properties['startTime'])
        ids = {p.properties['sceneName'] for p in prods}
        id_time = {p.properties['sceneName']: p.properties['startTime'] for p in prods}
        # 1) Build pairwise baseline table with caching (N stacks; each pair filled once)
        B = {} # (earlier,later) -> (|dt_days|, |bperp_m|)
        for ref in tqdm(prods, desc="Finding pairs", position=0, leave=True):
            rid = ref.properties['sceneName']
            print(f'looking for paris for {rid}')
            for attempt in range(1, 11):
                try:
                    stacks = ref.stack()
                    break
                except ASFSearchError as e: 
                    if attempt == 10:
                        raise 
                    time.sleep(0.5 * 2**(attempt-1))
                    
            for sec in stacks:
                sid = sec.properties['sceneName']
                if sid not in ids or sid == rid:
                    continue
                a, b = sorted((rid, sid), key=lambda k: id_time[k])
                if (a,b) in B:
                    continue
                dt = abs(10000 if sec.properties['temporalBaseline'] is None else sec.properties['temporalBaseline'])
                bp = abs(10000 if sec.properties['perpendicularBaseline'] is None else sec.properties['perpendicularBaseline'])
                
                B[(a,b)] = (dt, bp)

        # 2) First-cut keep by Δt/Δ⊥
        def pass_rules(dt, bp):
            near = any(abs(dt -t)<= dt_tol for t in dt_targets)
            return near and dt <= dt_max and bp <= pb_max
        
        pairs = {e for e, (dt, bp) in B.items() if pass_rules(dt, bp)}

        # 3) Enforce connectivity: degree ≥ MIN_DEGREE (add nearest-time links under PB cap)
        if force_connect is True:
            neighbors = defaultdict(set)

            for a, b in pairs:
                neighbors[a].add(b)
                neighbors[b].add(a)

            names = [p.properties['sceneName'] for p in prods]
            for n in names:
                if len(neighbors[n]) >= min_degree:
                    continue
                cands = sorted((m for m in names if m != n), key=lambda m: abs((isoparse(id_time[m]) - isoparse(id_time[n])).days))
                for m in cands:
                    a, b = sorted((n, m), key=lambda k: id_time[k])
                    dtbp = B.get((a, b))
                    if not dtbp:
                        continue
                    _, bp = dtbp
                    if bp > pb_max:
                        continue
                    if (a, b) not in pairs:
                        pairs.add((a, b))
                        neighbors[a].add(b); neighbors[b].add(a)
                    if len(neighbors[n]) >= min_degree:
                        break

            for n in names:
                while len(neighbors[n]) > max_degree:
                    # Rank this node’s pairs by "badness" = (dt, pb), descending
                    ranked = sorted(
                        [(m, *B.get(tuple(sorted((n, m))), (99999, 99999))) for m in neighbors[n]],
                        key=lambda x: (x[1], x[2]),  # sort by dt, then pb
                        reverse=True
                    )
                    worst, _, _ = ranked[0]  # worst neighbor
                    a, b = sorted((n, worst), key=lambda k: id_time[k])
                    if (a, b) in pairs:
                        pairs.remove((a, b))
                    neighbors[a].discard(b)
                    neighbors[b].discard(a)
        pairs_group[key]=sorted(pairs)
    return pairs_group[(0, 0)] if input_is_list else pairs_group

def get_config(config_path=None):

    """A function to load config file in TOML format"""
    if config_path is None:
        config_path = Path(__file__).parent.joinpath('config.toml')        
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

def earth_credit_pool(earthdata_credentials_pool_path = Path.home().joinpath('.credit_pool')) -> dict:
    """
    Load Earthdata credit pool from a file.
    """
    earthdata_credentials_pool_path = Path(earthdata_credentials_pool_path).expanduser().resolve()
    earthdata_credentials_pool = {}
    with open(earthdata_credentials_pool_path, 'r') as f:
        for line in f:
            key, value = line.strip().split(':')
            earthdata_credentials_pool[key] = value
    return earthdata_credentials_pool

def generate_slurm_script(
    job_name="my_job",
    output_file="job_%j.out",    # %j = jobID
    error_file="job_%j.err",
    time="04:00:00",
    partition="all",
    nodes=1,
    nodelist=None,            # e.g., "node[01-05]"
    ntasks=1,
    cpus_per_task=1,
    mem="4G",
    gpus=None,                   # e.g., "1" or "2" or "1g"
    array=None,                  # e.g., "0-9" or "1-100%10"
    dependency=None,             # e.g., "afterok:123456"
    mail_user=None,
    mail_type="ALL",             # BEGIN, END, FAIL, ALL
    account=None,
    qos=None,
    modules=None,                # list of modules to load
    conda_env=None,              # name of conda env to activate
    export_env=None,             # dict of env variables
    command="echo Hello SLURM!",
    filename="job.slurm"
    ):
    """
    Generate a full SLURM batch script with many options.
    """

    lines = ["#!/bin/bash"]

    # Basic job setup
    lines.append(f"#SBATCH --job-name={job_name}")
    lines.append(f"#SBATCH --output={output_file}")
    lines.append(f"#SBATCH --error={error_file}")
    lines.append(f"#SBATCH --time={time}")
    lines.append(f"#SBATCH --partition={partition}")
    lines.append(f"#SBATCH --nodes={nodes}")
    lines.append(f"#SBATCH --ntasks={ntasks}")
    lines.append(f"#SBATCH --cpus-per-task={cpus_per_task}")
    lines.append(f"#SBATCH --mem={mem}")

    # Optional extras
    if gpus:
        lines.append(f"#SBATCH --gres=gpu:{gpus}")
    if array:
        lines.append(f"#SBATCH --array={array}")
    if dependency:
        lines.append(f"#SBATCH --dependency={dependency}")
    if mail_user:
        lines.append(f"#SBATCH --mail-user={mail_user}")
        lines.append(f"#SBATCH --mail-type={mail_type}")
    if account:
        lines.append(f"#SBATCH --account={account}")
    if qos:
        lines.append(f"#SBATCH --qos={qos}")
    if nodelist:
        lines.append(f"#SBATCH --nodelist={nodelist}")

    lines.append("")  # blank line

    # Environment setup
    if modules:
        for mod in modules:
            lines.append(f"module load {mod}")
    if conda_env:
        lines.append(f"source activate {conda_env}")
    if export_env:
        for k, v in export_env.items():
            lines.append(f"export {k}={v}")

    lines.append("")  # blank line

    # Execution
    lines.append("echo \"Starting job on $(date)\"")
    lines.append(command)
    lines.append("echo \"Job finished on $(date)\"")

    script_content = "\n".join(lines)

    with open(filename, "w") as f:
        f.write(script_content)

    return filename 

def batch_rename(
    dirs : list[str],
    pattern: str = "velocity.tif",
    ):

    for path in dirs:
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            print(f"{path} is not a valid directory, skip.")
            continue
        tif_files = list(path.rglob(f'*{pattern}'))
        for tif in tif_files:
            new_name = f"velocity_{tif.parent.name}.tif"
            new_path = tif.parent.joinpath(new_name)
            tif.rename(new_path)
            print(f"Renamed {tif.name} to {new_name}")


def _to_wkt(geom_input) -> str:
    """
    Converts various input types to a WKT string.
    Supported: 
    1. List/Tuple of 4 numbers [min_lon, min_lat, max_lon, max_lat]
    2. String path to a spatial file (GeoJSON, SHP, etc.)
    3. Valid WKT string
    """
    if isinstance(geom_input, (list, tuple)):
        if len(geom_input) != 4:
            raise ValueError(f"BBox list must have exactly 4 elements, got {len(geom_input)}")
        
        if not all(isinstance(n, (int, float)) for n in geom_input):
            raise TypeError("All elements in BBox list must be int or float.")
        
        return box(*geom_input).wkt
    
    if isinstance(geom_input, str):
        geom_input = geom_input.strip()

        if Path(geom_input).exists():
            try:
                # Use geopandas to read any spatial format (SHP, GeoJSON, KML)
                gdf = gpd.read_file(geom_input)
                # Combine all geometries in the file into one (unary_union)
                return gdf.geometry.union_all().wkt
            except Exception as e:
                raise ValueError(f"Could not read spatial file at {geom_input}: {e}")
            
        try:
            # Try to load it to see if it's valid WKT
            decoded = wkt.loads(geom_input)
            return decoded.wkt
        except Exception:
            raise ValueError(
                "Input string is neither a valid file path nor a valid WKT string."
            )
    raise TypeError(f"Unsupported input type: {type(geom_input)}. Expected list, tuple, or str.")