
import time
from pathlib import Path

from asf_search.exceptions import ASFSearchError
from asf_search import ASFProduct
from collections import defaultdict
from colorama import Fore
from dateutil.parser import isoparse
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