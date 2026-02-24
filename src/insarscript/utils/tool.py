#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import time
import logging

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from dateutil.parser import isoparse
from pathlib import Path
from typing import Optional, Union, List, Dict
from threading import Lock

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import numpy as np
from asf_search import ASFProduct, ASFSearchError
from asf_search.baseline.calc import calculate_perpendicular_baselines
from box import Box as Config
from colorama import Fore
from shapely.geometry import box
from shapely import wkt
from tqdm import tqdm


logger = logging.getLogger(__name__)

# Sentinel value used when a baseline cannot be determined.
# Large enough to fail every filter condition.
_MISSING: float = 10_000.0


# ═══════════════════════════════════════════════════════════════════════════
#  TYPE ALIASES
# ═══════════════════════════════════════════════════════════════════════════

SceneID   = str
DateFloat = float   # Unix timestamp (seconds)
Pair      = tuple[SceneID, SceneID]
BaselineEntry = tuple[float, float]   # (dt_days, bperp_m)
BaselineTable = dict[Pair, BaselineEntry]
PairGroup = dict[tuple[int, int], list[Pair]]


# ═══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _has_local_baseline(p: ASFProduct) -> bool:
    """
    Return True if *p* carries enough on-product data to compute bperp
    locally without calling the ASF API.

    Sentinel-1 (CALCULATED type):
        p.baseline['stateVectors']['positions'] and ['velocities'] must exist.

    ALOS / ERS / RADARSAT (PRE_CALCULATED type):
        p.baseline['insarBaseline'] (a scalar float) must exist.
    """
    b = getattr(p, "baseline", None)
    if not b:
        return False
    if "stateVectors" in b:
        sv = b["stateVectors"]
        return bool(sv.get("positions") and sv.get("velocities"))
    if "insarBaseline" in b:
        return True
    return False


def _fetch_stack_with_retry(
    ref: ASFProduct,
    max_attempts: int = 10,
) -> tuple[SceneID, list[ASFProduct]]:
    """
    Fetch the ASF stack for *ref* with exponential-backoff retry.

    Returns (scene_name, stack_products).
    Raises ASFSearchError after *max_attempts* consecutive failures.
    """
    rid = ref.properties["sceneName"]
    for attempt in range(1, max_attempts + 1):
        try:
            return rid, ref.stack()
        except ASFSearchError:
            if attempt == max_attempts:
                logger.error(
                    "Stack fetch failed for %s after %d attempts.", rid, max_attempts
                )
                raise
            wait = 0.5 * 2 ** (attempt - 1)
            logger.debug(
                "Attempt %d failed for %s; retrying in %.1f s.", attempt, rid, wait
            )
            time.sleep(wait)
    raise ASFSearchError(f"Unreachable: failed to fetch stack for {rid}")


def _build_baseline_table_local(
    prods: list[ASFProduct],
    ids: set[SceneID],
    id_time_dt: dict[SceneID, DateFloat],
) -> BaselineTable:
    """
    Compute the full pairwise (dt_days, bperp_m) table from data already
    stored on each ASFProduct — **zero network calls**.

    Algorithm
    ---------
    1. Call ``calculate_perpendicular_baselines(reference=prods[0], secondaries=prods)``
       once.  This is the same function asf_search uses internally inside
       ``ref.stack()``, but we call it directly so no HTTP request is made.
       It returns bperp for every scene relative to ``prods[0]`` as the anchor.

    2. Pairwise bperp between scenes A and B equals
       ``|bp_vector[A] - bp_vector[B]|``
       because perpendicular baseline is a linear function of orbital
       separation and the common anchor cancels out.

    3. Temporal baseline is computed directly from pre-parsed Unix timestamps.
    """
    B: BaselineTable = {}
    if not prods:
        return B

    try:
        anchored = calculate_perpendicular_baselines(
            reference=prods[0].properties['sceneName'],
            stack=prods,
        )
        bp_vector: dict[SceneID, float | None] = {
            p.properties["sceneName"]: p.properties.get("perpendicularBaseline")
            for p in anchored
        }
    except Exception as exc:
        logger.warning(
            "Local baseline calculation failed (%s); table will be empty.", exc
        )
        return B

    for i, a in enumerate(prods):
        for b in prods[i + 1:]:
            aid = a.properties["sceneName"]
            bid = b.properties["sceneName"]
            if aid not in ids or bid not in ids:
                continue
            # Temporal baseline in days
            dt = abs(id_time_dt[bid] - id_time_dt[aid]) / 86_400.0
            # Pairwise bperp = |bp_relative_to_anchor[B] - bp_relative_to_anchor[A]|
            bp_a, bp_b = bp_vector.get(aid), bp_vector.get(bid)
            bp = (
                abs(bp_b - bp_a)
                if (bp_a is not None and bp_b is not None)
                else _MISSING
            )

            early, late = (
                (aid, bid) if id_time_dt[aid] <= id_time_dt[bid] else (bid, aid)
            )
            B[(early, late)] = (dt, bp)

    logger.info(
        "Local baseline table: %d pairs from %d scenes.", len(B), len(prods)
    )
    return B


def _build_baseline_table_api(
    prods: list[ASFProduct],
    ids: set[SceneID],
    id_time_dt: dict[SceneID, DateFloat],
    max_workers: int,
) -> BaselineTable:
    """
    Fallback: fetch baselines via ``ref.stack()`` in a thread pool.

    Only called for products that are missing local baseline data.
    Threads are used because ``ref.stack()`` is network-bound (the GIL is
    released during I/O, so threads genuinely run concurrently).

    Lock strategy: each thread builds a local dict without any locking, then
    acquires the shared lock once to batch-write — minimising contention.
    ``setdefault`` ensures the first writer wins on any race.
    """
    B: BaselineTable = {}
    B_lock = Lock()

    def _process_ref(ref: ASFProduct) -> int:
        rid, stacks = _fetch_stack_with_retry(ref)
        local: BaselineTable = {}

        for sec in stacks:
            sid = sec.properties["sceneName"]
            if sid not in ids or sid == rid:
                continue
            a, b = (
                (rid, sid) if id_time_dt[rid] <= id_time_dt[sid] else (sid, rid)
            )
            if (a, b) in B:
                continue
            dt = sec.properties.get("temporalBaseline")
            bp = sec.properties.get("perpendicularBaseline")
            local[(a, b)] = (
                abs(dt) if dt is not None else _MISSING,
                abs(bp) if bp is not None else _MISSING,
            )

        if local:
            with B_lock:
                for k, v in local.items():
                    B.setdefault(k, v)   # first writer wins; values are identical

        return len(local)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_ref, ref): ref for ref in prods}
        with tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Fetching stacks (API fallback)",
            unit="scene",
        ) as bar:
            for fut in bar:
                ref = futures[fut]
                try:
                    n = fut.result()
                    bar.set_postfix(
                        pairs=len(B),
                        new=n,
                        scene=ref.properties["sceneName"][-10:],
                    )
                except Exception as exc:
                    logger.error(
                        "Error processing %s: %s",
                        ref.properties["sceneName"], exc,
                    )
                    raise

    logger.info(
        "API baseline table: %d pairs from %d scenes.", len(B), len(prods)
    )
    return B


def _build_baseline_table(
    prods: list[ASFProduct],
    ids: set[SceneID],
    id_time_dt: dict[SceneID, DateFloat],
    max_workers: int,
) -> BaselineTable:
    """
    Route each product to the fastest available baseline source.

    - Products with stateVectors or insarBaseline  →  local (no network)
    - Products missing that data                   →  API fallback (threaded)

    The two result dicts are merged; API results take precedence for any
    overlap (unlikely, but safe).
    """
    local_prods = [p for p in prods if _has_local_baseline(p)]
    api_prods   = [p for p in prods if not _has_local_baseline(p)]

    if not api_prods:
        logger.info(
            "All %d products have local baseline data — no API calls needed.",
            len(prods),
        )
    else:
        logger.warning(
            "%d / %d products missing local baseline data — API fallback for those.",
            len(api_prods), len(prods),
        )

    B: BaselineTable = {}

    if local_prods:
        B.update(_build_baseline_table_local(local_prods, ids, id_time_dt))

    if api_prods:
        B.update(_build_baseline_table_api(api_prods, ids, id_time_dt, max_workers))

    return B


def _enforce_connectivity(
    pairs: set[Pair],
    B: BaselineTable,
    names: list[SceneID],
    id_time_dt: dict[SceneID, DateFloat],
    min_degree: int,
    max_degree: int,
    pb_max: float,
    dt_max: float,
    force_connect: bool
) -> set[Pair]:
    """
    Enforce min_degree / max_degree connectivity on the interferogram graph.

    Step A — boost under-connected scenes
        For each scene with fewer than *min_degree* connections, add the
        nearest-time neighbours that satisfy *pb_max* and *dt_max* until
        the scene reaches *min_degree* or candidates are exhausted.

    Step B — trim over-connected scenes
        For each scene exceeding *max_degree*, remove the worst pair
        (highest dt, then highest bperp) as long as doing so does not drop
        the other endpoint below *min_degree*.  Stops early and logs a
        warning if trimming is impossible without violating min_degree.

    This function is intentionally single-threaded: each modification to
    *neighbors* affects subsequent decisions, so the operations are
    order-dependent and cannot be safely parallelised.

    Pre-sorting candidate lists once per scene (O(N log N) total) avoids
    re-sorting on every degree-enforcement iteration.
    """
    neighbors: dict[SceneID, set[SceneID]] = defaultdict(set)
    for a, b in pairs:
        neighbors[a].add(b)
        neighbors[b].add(a)

    # Pre-sort candidates by |Δt| for every scene — paid once, reused many times
    sorted_cands: dict[SceneID, list[tuple[SceneID, float]]] = {
        n: sorted(
            ((m, abs(id_time_dt[m] - id_time_dt[n])) for m in names if m != n),
            key=lambda x: x[1],
        )
        for n in names
    }

    # ── Step A: boost under-connected scenes ─────────────────────────────
    if force_connect:
        for n in names:
            if len(neighbors[n]) >= min_degree:
                continue

            logger.debug(
                "Scene %s: degree %d < min_degree %d; searching for more pairs.",
                n, len(neighbors[n]), min_degree,
            )

            for m, _ in sorted_cands[n]:
                if len(neighbors[n]) >= min_degree:
                    break
                if m in neighbors[n]:
                    continue

                a, b = (n, m) if id_time_dt[n] <= id_time_dt[m] else (m, n)
                entry = B.get((a, b))
                if entry is None:
                    continue

                dt_val, bp_val = entry
                if bp_val > pb_max or dt_val > dt_max:
                    continue

                pairs.add((a, b))
                neighbors[a].add(b)
                neighbors[b].add(a)
                logger.debug(
                    "  force-added %s – %s  (dt=%.0f d, bp=%.1f m)",
                    a, b, dt_val, bp_val,
                )

            if len(neighbors[n]) < min_degree:
                logger.warning(
                    "Scene %s: only %d / %d connections available in baseline table.",
                    n, len(neighbors[n]), min_degree,
                )

    # ── Step B: trim over-connected scenes ───────────────────────────────
    for n in names:
        while len(neighbors[n]) > max_degree:
            # Rank neighbours: worst = highest dt, then highest bperp
            ranked = sorted(
                neighbors[n],
                key=lambda m: B.get(
                    (n, m) if id_time_dt[n] <= id_time_dt[m] else (m, n),
                    (0.0, 0.0),
                ),
                reverse=True,
            )

            removed = False
            
            for min_other in (min_degree + 1, min_degree):
                for worst in ranked:
                    if len(neighbors[worst]) < min_other:
                        continue
                    a, b = (
                        (n, worst) if id_time_dt[n] <= id_time_dt[worst]
                        else (worst, n)
                    )
                    pairs.discard((a, b))
                    neighbors[n].discard(worst)
                    neighbors[worst].discard(n)
                    removed = True
                    break
                if removed:
                    break

            if not removed:
                # Every neighbour is at min_degree — impossible to trim further.
                # This happens when min_degree and max_degree conflict,
                # e.g. min_degree=5, max_degree=3.
                logger.warning(
                    "Scene %s: cannot trim to max_degree=%d — all %d neighbours "
                    "are at min_degree=%d. Consider increasing max_degree or "
                    "decreasing min_degree.",
                    n, max_degree, len(neighbors[n]), min_degree,
                )
                break

    return pairs

def _to_wkt(geom_input) -> str | None:
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
    if not geom_input:
        return None
    raise TypeError(f"Unsupported input type: {type(geom_input)}. Expected list, tuple, or str.")


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def select_pairs(
    search_results: Union[dict[tuple[int, int], list[ASFProduct]], list[ASFProduct]],
    dt_targets: tuple[int, ...] = (6, 12, 24, 36, 48, 72, 96),
    dt_tol: int = 3,
    dt_max: int = 120,
    pb_max: float = 150.0,
    min_degree: int = 3,
    max_degree: int = 999,
    force_connect: bool = True,
    max_workers: int = 8
) -> Union[PairGroup, list[Pair]]:
    
    """
    Select interferogram pairs based on temporal and perpendicular baseline.

    This function selects interferogram pairs according to temporal spacing 
    and perpendicular baseline constraints, optionally enforcing connectivity 
    rules per scene.

    Supported sensors:
    - Sentinel-1 (CALCULATED)  : stateVectors + ascendingNodeTime → local
    - ALOS / ERS / RADARSAT (PRE_CALCULATED) : insarBaseline scalar → local
    - Any product missing data : ref.stack() API call → fallback

    Args:
        search_results (list[ASFProduct] | dict[tuple[int,int], list[ASFProduct]]):
            Either a flat list (single stack) or a dictionary keyed by (path, frame).
        dt_targets (list[float], optional):
            Preferred temporal spacings in days. A candidate pair passes if 
            |dt - target| <= dt_tol for at least one target.
        dt_tol (float, optional):
            Tolerance in days added to each entry in dt_targets.
        dt_max (float, optional):
            Maximum temporal baseline in days.
        pb_max (float, optional):
            Maximum perpendicular baseline in meters.
        min_degree (int, optional):
            Minimum interferogram connections per scene. Enforced when force_connect is True.
        max_degree (int, optional):
            Maximum interferogram connections per scene.
        force_connect (bool, optional):
            If a scene falls below min_degree after primary selection, add its nearest-time 
            neighbors that satisfy pb_max and dt_max. May introduce lower-quality pairs; a warning is logged.
        max_workers (int, optional):
            Number of threads for API fallback. Has no effect if all products have local baseline 
            data (common for Sentinel-1 and ALOS). Set to 1 to disable threading (useful for debugging).

    Returns:
        list[Pair] | dict[tuple[int,int], list[Pair]]:
            A flat list of Pair tuples (earlier_scene_name, later_scene_name) sorted by acquisition time, 
            if search_results was a list. Otherwise, a dictionary keyed by (path, frame) with lists of Pair tuples.
    """

    # ── normalise input ───────────────────────────────────────────────────
    input_is_list = isinstance(search_results, list)
    if input_is_list:
        working_dict: dict[tuple[int, int], list[ASFProduct]] = {
            (0, 0): search_results   # type: ignore[arg-type]
        }
    elif isinstance(search_results, dict):
        working_dict = search_results
    else:
        raise TypeError(
            f"search_results must be a list or dict of ASFProducts, "
            f"got {type(search_results)}"
        )

    # ── primary filter helpers (defined once, closed over threshold args) ─
    def _near_target(dt: float) -> bool:
        return any(abs(dt - t) <= dt_tol for t in dt_targets)

    def _passes_primary(dt: float, bp: float) -> bool:
        return _near_target(dt) and dt <= dt_max and bp <= pb_max

    pairs_group: PairGroup = defaultdict(list)

    # ── process each (path, frame) key ───────────────────────────────────
    for key, search_result in working_dict.items():
        if not input_is_list:
            logger.info(
                "%sSearching pairs for path %d frame %d …",
                Fore.GREEN, key[0], key[1],
            )

        # Sort by acquisition time so `names` is chronologically ordered
        prods = sorted(search_result, key=lambda p: p.properties["startTime"])

        if not prods:
            logger.warning("No products for key %s — skipping.", key)
            continue

        # Pre-parse acquisition datetimes to Unix timestamps (done once;
        # reused in sort keys, dt calculations, and pair ordering)
        id_time_raw: dict[SceneID, str] = {
            p.properties["sceneName"]: p.properties["startTime"] for p in prods
        }
        id_time_dt: dict[SceneID, DateFloat] = {
            sid: isoparse(t).timestamp() for sid, t in id_time_raw.items()
        }
        ids: set[SceneID] = set(id_time_raw)
        names: list[SceneID] = [p.properties["sceneName"] for p in prods]

        # ── 1. Build pairwise baseline table ─────────────────────────────
        B = _build_baseline_table(prods, ids, id_time_dt, max_workers=max_workers)

        # ── 2. Primary pair selection ─────────────────────────────────────
        pairs: set[Pair] = {
            e for e, (dt, bp) in B.items() if _passes_primary(dt, bp)
        }
        logger.info(
            "Key %s — primary selection: %d / %d candidate pairs.",
            key, len(pairs), len(B),
        )

        # ── 3. Connectivity enforcement ───────────────────────────────────
        pairs = _enforce_connectivity(
            pairs,
            B,
            names,
            id_time_dt,
            min_degree=min_degree,
            max_degree=max_degree,
            pb_max=pb_max,
            dt_max=float(dt_max),
            force_connect=force_connect
        )

        pairs_group[key] = sorted(pairs)
        logger.info(
            "Key %s — final pair count: %d.", key, len(pairs_group[key])
        )
    pairs = pairs_group[(0, 0)] if input_is_list else pairs_group

    return pairs, B

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
    

def plot_pair_network(
    pairs: list[Pair] | PairGroup,
    baselines: BaselineTable,                           
    title: str = "Interferogram Network",
    figsize: tuple[int, int] = (18, 7),
    save_path: str |Path| None = None,
) -> plt.Figure:

    """
    Plot an interferogram network along with per-scene connection statistics.

    This function visualizes the relationships between SAR acquisitions in
    terms of temporal and perpendicular baselines. The network graph is
    shown on the left, while a horizontal bar chart summarizes the number
    of connections per scene on the right.

    The layout is as follows:
        - Left  : Network graph (x-axis = days since first acquisition,
                  y-axis = perpendicular baseline [m])
        - Right : Horizontal bar chart showing the number of connections per SAR scene

    Args:
        pairs (list[Pair] | PairGroup):
            A flat list of pairs or a dictionary keyed by (path, frame)
            with lists of pairs. Each pair is a tuple `(earlier_scene, later_scene)`.
        baselines (BaselineTable):
            Table or mapping containing temporal and perpendicular baseline
            information for each interferogram pair.
        title (str, optional):
            Main title of the network plot. Defaults to "Interferogram Network".
        figsize (tuple[int, int], optional):
            Figure size (width, height) in inches. Defaults to (18, 7).
        save_path (str | Path | None, optional):
            Path to save the generated figure. If None, figure is not saved.
            Defaults to None.

    Returns:
        matplotlib.figure.Figure:
            The created matplotlib figure containing the network and
            per-scene connection histogram.

    Raises:
        TypeError:
            If any scene name in `pairs` is not a string.
        ValueError:
            If a scene name cannot be parsed into a valid date.

    Notes:
        - Node positions: x = days since first acquisition, y = perpendicular baseline.
        - Node color represents the node degree (number of connections).
        - Edge color and width represent temporal baseline.
        - Scenes with fewer than 2 connections are highlighted in red in the histogram.
        - Legends show node degree, temporal baseline, and path/frame grouping.
        - The top axis of the network plot shows real acquisition dates for reference.
    """

    # ── 0. Normalise input ────────────────────────────────────────────────
    save_path = Path(save_path).expanduser()
    
    if isinstance(pairs, dict):
        flat_pairs: list[Pair] = []
        group_labels: list[str] = []
        for (path, frame), pair_list in pairs.items():
            flat_pairs.extend(pair_list)
            group_labels.append(f"P{path}/F{frame}: {len(pair_list)} pairs")
        subtitle = " | ".join(group_labels)
    else:
        flat_pairs = pairs
        subtitle = f"{len(flat_pairs)} pairs"

    # ── 1. Parse dates ────────────────────────────────────────────────────
    scenes: set[SceneID] = set()
    for a, b in flat_pairs:
        scenes.update([a, b])

    def _parse_date(scene_name: str) -> datetime:
        if not isinstance(scene_name, str):
            raise TypeError(
                f"Expected str, got {type(scene_name).__name__}: {scene_name!r}."
            )
        m = re.search(r"(\d{8})", scene_name)
        if m:
            return datetime.strptime(m.group(1), "%Y%m%d")
        m = re.search(r"(\d{4}-\d{2}-\d{2})", scene_name)
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        raise ValueError(f"Cannot parse date from scene name: {scene_name}")

    id_time: dict[SceneID, datetime] = {s: _parse_date(s) for s in scenes}
    t0      = min(id_time.values())
    id_days: dict[SceneID, float] = {
        s: (id_time[s] - t0).total_seconds() / 86_400.0 for s in scenes
    }

    # ── 2. Build graph ────────────────────────────────────────────────────
    G = nx.Graph()
    G.add_nodes_from(scenes)

    if isinstance(pairs, dict):
        for (path, frame), pair_list in pairs.items():
            for a, b in pair_list:
                dt, bp = baselines.get((a, b), (_MISSING, _MISSING))
                G.add_edge(a, b, dt=dt, bp=bp, path=path, frame=frame)
    else:
        for a, b in flat_pairs:
            dt, bp = baselines.get((a, b), (_MISSING, _MISSING))
            G.add_edge(a, b, dt=dt, bp=bp, path=0, frame=0)

    # ── 3. Node positions (x=days, y=bperp) ──────────────────────────────
    # Assign each scene a bperp position by averaging bperp of all its pairs.
    # baselines stores absolute bperp; we recover a relative position by anchoring
    # the earliest scene at y=0 and walking forward in time.
    bperp_accum: dict[SceneID, list[float]] = defaultdict(list)
    for (a, b), (dt, bp) in baselines.items():
        if bp >= _MISSING:
            continue
        bperp_accum[a].append(-bp / 2.0)
        bperp_accum[b].append(+bp / 2.0)

    bperp_pos: dict[SceneID, float] = {
        s: float(np.mean(v)) if v else 0.0
        for s, v in bperp_accum.items()
    }
    # anchor earliest scene to y=0
    sorted_by_time = sorted(scenes, key=lambda s: id_days[s])
    offset = bperp_pos.get(sorted_by_time[0], 0.0)
    bperp_pos = {s: bperp_pos.get(s, 0.0) - offset for s in scenes}

    pos: dict[SceneID, tuple[float, float]] = {
        s: (id_days[s], bperp_pos[s]) for s in scenes
    }

    # ── 4. Visual attributes ──────────────────────────────────────────────
    degrees      = dict(G.degree())
    max_deg      = max(degrees.values(), default=1)
    node_colours = [plt.cm.RdYlGn(degrees[n] / max_deg) for n in G.nodes()]

    edge_dts     = [G[a][b]["dt"] for a, b in G.edges()]
    max_dt       = max((d for d in edge_dts if d < _MISSING), default=1.0)
    edge_colours = [plt.cm.RdYlGn_r(min(dt, max_dt) / max_dt) for dt in edge_dts]
    edge_widths  = [0.5 + 2.5 * (1.0 - min(dt, max_dt) / max_dt) for dt in edge_dts]

    if isinstance(pairs, dict):
        group_keys  = list(pairs.keys())
        linestyles  = ["-", "--", "-.", ":"] * (len(group_keys) // 4 + 1)
        key_style   = {k: linestyles[i] for i, k in enumerate(group_keys)}
        edge_styles = [
            key_style[(G[a][b]["path"], G[a][b]["frame"])] for a, b in G.edges()
        ]
    else:
        edge_styles = ["-"] * len(G.edges())

    # ── 5. Figure layout ──────────────────────────────────────────────────
    fig = plt.figure(figsize=figsize)
    gs  = fig.add_gridspec(1, 2, width_ratios=[3, 1], wspace=0.35)
    ax_net  = fig.add_subplot(gs[0])
    ax_hist = fig.add_subplot(gs[1])

    # ── 6. Draw network ───────────────────────────────────────────────────
    edges_by_style: dict[str, list] = defaultdict(list)
    for (a, b), style, colour, width in zip(
        G.edges(), edge_styles, edge_colours, edge_widths
    ):
        edges_by_style[style].append((a, b, colour, width))

    for style, edge_data in edges_by_style.items():
        nx.draw_networkx_edges(
            G, pos, ax=ax_net,
            edgelist=[(a, b) for a, b, _, _ in edge_data],
            edge_color=[c for _, _, c, _ in edge_data],
            width=[w for _, _, _, w in edge_data],
            style=style,
            alpha=0.7,
        )

    nx.draw_networkx_nodes(
        G, pos, ax=ax_net,
        node_color=node_colours,
        node_size=80,
        linewidths=0.5,
        edgecolors="black",
    )
    nx.draw_networkx_labels(
        G, pos,
        labels={s: s[-8:] for s in G.nodes()},
        ax=ax_net,
        font_size=5,
    )

    # ── 7. Network axes ───────────────────────────────────────────────────
    ax_net.set_xlabel("Days since first acquisition", fontsize=11)
    ax_net.set_ylabel("Perpendicular baseline [m]", fontsize=11)    # ✅ real unit
    ax_net.set_title(
        f"{title}\n{subtitle}\n"
        f"{len(scenes)} scenes · {len(flat_pairs)} pairs · "
        f"mean degree {np.mean(list(degrees.values())):.1f}",
        fontsize=11,
    )
    ax_net.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True)
    ax_net.set_frame_on(True)

    # real date ticks on top axis
    x_vals  = [p[0] for p in pos.values()]
    x_ticks = np.linspace(min(x_vals), max(x_vals), min(8, len(pos)))
    ax2 = ax_net.twiny()
    ax2.set_xlim(ax_net.get_xlim())
    ax2.set_xticks(x_ticks)
    ax2.set_xticklabels(
        [
            (t0 + __import__("datetime").timedelta(days=d)).strftime("%Y-%m-%d")
            for d in x_ticks
        ],
        rotation=30, ha="left", fontsize=7,
    )
    ax2.set_xlabel("Acquisition date (UTC)", fontsize=9)

    # ── 8. Per-scene connection histogram ─────────────────────────────────
    # Sort scenes by date so the histogram reads chronologically top→bottom
    sorted_scene_names = sorted(scenes, key=lambda s: id_days[s])
    scene_degrees      = [degrees[s] for s in sorted_scene_names]
    short_names        = [s[-12:] for s in sorted_scene_names]   # trim for readability
    y_positions        = range(len(sorted_scene_names))

    bar_colours = [plt.cm.RdYlGn(degrees[s] / max_deg) for s in sorted_scene_names]

    bars = ax_hist.barh(
        y_positions,
        scene_degrees,
        color=bar_colours,
        edgecolor="white",
        linewidth=0.4,
        height=0.7,
    )

    # annotate each bar with connection count
    for bar, count in zip(bars, scene_degrees):
        ax_hist.text(
            bar.get_width() + 0.1,
            bar.get_y() + bar.get_height() / 2,
            str(count),
            va="center", fontsize=7,
        )

    # vertical line at mean degree
    mean_deg = np.mean(scene_degrees)
    ax_hist.axvline(
        mean_deg, color="steelblue", linestyle="--", linewidth=1.0, alpha=0.8
    )
    ax_hist.text(
        mean_deg + 0.1, len(sorted_scene_names) - 0.5,
        f"mean\n{mean_deg:.1f}",
        color="steelblue", fontsize=7, va="top",
    )

    # mark scenes below min connectivity in red
    for i, (s, deg) in enumerate(zip(sorted_scene_names, scene_degrees)):
        if deg < 2:
            ax_hist.get_children()[i].set_edgecolor("red")
            ax_hist.get_children()[i].set_linewidth(1.5)

    ax_hist.set_yticks(y_positions)
    ax_hist.set_yticklabels(short_names, fontsize=6)
    ax_hist.set_xlabel("Number of connections", fontsize=9)
    ax_hist.set_title("Connections\nper scene", fontsize=10)
    ax_hist.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax_hist.set_frame_on(True)
    # match vertical order to network: earliest at top
    ax_hist.invert_yaxis()

    # ── 9. Legends ────────────────────────────────────────────────────────
    deg_legend = ax_net.legend(
        handles=[
            mpatches.Patch(color=plt.cm.RdYlGn(v / max_deg), label=f"degree {v}")
            for v in sorted(set(degrees.values()))
        ],
        title="Node degree", loc="upper left", fontsize=7, title_fontsize=8,
    )
    ax_net.add_artist(deg_legend)

    ax_net.legend(
        handles=[
            mpatches.Patch(
                color=plt.cm.RdYlGn_r(v / max_dt), label=f"{v:.0f} days"
            )
            for v in [0, max_dt * 0.33, max_dt * 0.66, max_dt]
        ],
        title="Temporal baseline", loc="lower right", fontsize=7, title_fontsize=8,
    )

    if isinstance(pairs, dict):
        ax_net.add_artist(
            ax_net.legend(
                handles=[
                    mpatches.Patch(
                        linestyle=key_style[k], fill=False,
                        edgecolor="grey", label=f"P{k[0]}/F{k[1]}",
                    )
                    for k in group_keys
                ],
                title="Path / Frame", loc="upper right", fontsize=7, title_fontsize=8,
            )
        )

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Saved → {save_path}")

    return fig

def earth_credit_pool(earthdata_credentials_pool_path = Path.home().joinpath('.credit_pool')) -> dict:
    """
    Load Earthdata credentials from a local credit pool file.

    The function reads a simple key-value file where each line contains
    `username:password` (or `key:value`) pairs, and returns them as a dictionary.

    Args:
        earthdata_credentials_pool_path (Path, optional):
            Path to the Earthdata credentials file. Defaults to
            `~/.credit_pool`. The path is expanded and resolved to an absolute path.

    Returns:
        dict:
            Dictionary mapping credential keys to their corresponding values.
            Example:
            ```
            {
                "username1": "password1",
                "username2": "password2",
            }
            ```

    Raises:
        FileNotFoundError:
            If the specified credentials file does not exist.
        ValueError:
            If any line in the file does not contain a single ':' separating key and value.
        OSError:
            For any other I/O related errors while reading the file.

    Notes:
        - Each line of the file must be formatted as `key:value`.
        - Leading/trailing whitespace is stripped from both key and value.
        - Useful for managing multiple Earthdata credentials for automated downloads.
    """
    earthdata_credentials_pool_path = Path(earthdata_credentials_pool_path).expanduser().resolve()
    earthdata_credentials_pool = {}
    with open(earthdata_credentials_pool_path, 'r') as f:
        for line in f:
            key, value = line.strip().split(':')
            earthdata_credentials_pool[key] = value
    return earthdata_credentials_pool

@dataclass
class Slurmjob_Config:
    """Configuration for a SLURM job submission script.
    
    This class encapsulates all parameters needed to generate a SLURM batch script,
    including resource allocation, job settings, environment configuration, and
    execution commands.
    
    Attributes:
        job_name: Name of the SLURM job.
        output_file: Path for standard output. Use %j for job ID.
        error_file: Path for standard error. Use %j for job ID.
        time: Maximum wall time in HH:MM:SS format.
        partition: SLURM partition name to submit to.
        nodes: Number of nodes to allocate.
        ntasks: Number of tasks to run.
        cpus_per_task: CPUs per task.
        mem: Memory allocation per node (e.g., "4G", "500M").
        nodelist: Specific nodes to use (e.g., "node[01-05]").
        gpus: GPU allocation (e.g., "1", "2", "1g").
        array: Array job specification (e.g., "0-9", "1-100%10").
        dependency: Job dependency condition (e.g., "afterok:123456").
        mail_user: Email address for job notifications.
        mail_type: When to send email notifications (BEGIN, END, FAIL, ALL).
        account: Account to charge resources to.
        qos: Quality of Service specification.
        modules: List of environment modules to load.
        conda_env: Name of conda environment to activate.
        export_env: Dictionary of environment variables to export.
        command: Bash command(s) to execute.
    
    Examples:
        Basic job configuration:
        
        >>> config = SlurmJobConfig(
        ...     job_name="my_analysis",
        ...     time="02:00:00",
        ...     command="python analyze.py"
        ... )
        >>> config.to_script("analysis.slurm")
        PosixPath('analysis.slurm')
        
        GPU job with conda environment:
        
        >>> config = SlurmJobConfig(
        ...     job_name="training",
        ...     time="12:00:00",
        ...     mem="32G",
        ...     gpus="2",
        ...     conda_env="pytorch",
        ...     modules=["cuda/11.8"],
        ...     command="python train.py --epochs 100"
        ... )
        >>> config.to_script("train.slurm")
        PosixPath('train.slurm')
        
        Array job with environment variables:
        
        >>> config = SlurmJobConfig(
        ...     job_name="param_sweep",
        ...     array="0-99",
        ...     export_env={"PARAM_ID": "$SLURM_ARRAY_TASK_ID"},
        ...     command="python run_experiment.py $PARAM_ID"
        ... )
        >>> config.to_script()
        PosixPath('job.slurm')
    """
    job_name: str = "my_job"
    output_file: str = "job_%j.out"
    error_file: str = "job_%j.err"
    time: str = "04:00:00"
    partition: str = "all"
    nodes: int = 1
    ntasks: int = 1
    cpus_per_task: int = 1
    mem: str = "4G"
    
    # Optional parameters
    nodelist: Optional[str] = None
    gpus: Optional[str] = None
    array: Optional[str] = None
    dependency: Optional[str] = None
    mail_user: Optional[str] = None
    mail_type: str = "ALL"
    account: Optional[str] = None
    qos: Optional[str] = None
    
    # Environment
    modules: List[str] = field(default_factory=list)
    conda_env: Optional[str] = None
    export_env: Dict[str, str] = field(default_factory=dict)
    
    # Execution
    command: str = "echo Hello SLURM!"
    
    def to_script(self, filename: str = "job.slurm") -> Path:
        """Generate the SLURM script file."""
        lines = ["#!/bin/bash"]
        
        # Required directives
        lines.extend([
            f"#SBATCH --job-name={self.job_name}",
            f"#SBATCH --output={self.output_file}",
            f"#SBATCH --error={self.error_file}",
            f"#SBATCH --time={self.time}",
            f"#SBATCH --partition={self.partition}",
            f"#SBATCH --nodes={self.nodes}",
            f"#SBATCH --ntasks={self.ntasks}",
            f"#SBATCH --cpus-per-task={self.cpus_per_task}",
            f"#SBATCH --mem={self.mem}",
        ])
        
        # Optional directives
        if self.gpus:
            lines.append(f"#SBATCH --gres=gpu:{self.gpus}")
        if self.array:
            lines.append(f"#SBATCH --array={self.array}")
        if self.dependency:
            lines.append(f"#SBATCH --dependency={self.dependency}")
        if self.mail_user:
            lines.append(f"#SBATCH --mail-user={self.mail_user}")
            lines.append(f"#SBATCH --mail-type={self.mail_type}")
        if self.account:
            lines.append(f"#SBATCH --account={self.account}")
        if self.qos:
            lines.append(f"#SBATCH --qos={self.qos}")
        if self.nodelist:
            lines.append(f"#SBATCH --nodelist={self.nodelist}")
        
        lines.append("")
        
        # Environment setup
        lines.extend([f"module load {mod}" for mod in self.modules])
        if self.conda_env:
            lines.append(f"source activate {self.conda_env}")
        lines.extend([f"export {k}={v}" for k, v in self.export_env.items()])
        
        lines.append("")
        
        # Execution
        lines.extend([
            'echo "Starting job on $(date)"',
            self.command,
            'echo "Job finished on $(date)"'
        ])
        
        filepath = Path(filename).expanduser().resolve()
        filepath.write_text("\n".join(lines))
        
        return filepath

