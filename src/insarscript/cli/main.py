"""
HPC-compatible CLI for InSARScript.

Every command handler builds an instance from CLI args, then delegates all
logic to the shared command layer (insarscript.commands). The same command
classes are used by the Panel frontend, so there is no duplicated business logic.

Usage examples
--------------
insarscript search --bbox -113.05 37.74 -112.68 38.00 --start 2021-01-01 --end 2022-01-01
insarscript search ... --download --orbit-files
insarscript submit --workdir /data/bryce --pairs-file pairs.json
insarscript refresh --workdir /data/bryce
insarscript download-results --workdir /data/bryce
insarscript retry --workdir /data/bryce
insarscript watch --workdir /data/bryce --interval 300
insarscript credits --workdir /data/bryce
insarscript prep --workdir /data/bryce
insarscript analyze --workdir /data/bryce
insarscript analyze --workdir /data/bryce --prep-first
"""

import argparse
import json
import sys
from pathlib import Path

from insarscript._version import __version__


# ---------------------------------------------------------------------------
# Shared argument helpers
# ---------------------------------------------------------------------------

def _add_workdir(p: argparse.ArgumentParser, required: bool = True):
    p.add_argument("-w", "--workdir", metavar="PATH", required=required,
                   help="Working directory (where data and job files live)")


def _add_job_file(p: argparse.ArgumentParser):
    p.add_argument("--job-file", metavar="PATH",
                   help="Path to a saved HyP3 job JSON file (overrides default hyp3_jobs.json)")


def _add_credential_pool(p: argparse.ArgumentParser):
    p.add_argument("--credential-pool", metavar="PATH",
                   help='JSON file mapping {username: password} for multi-account HyP3 submission')


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insarscript",
        description="InSAR processing pipeline CLI",
        epilog="Use 'insarscript <command> --help' for details on each command.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"insarscript {__version__}")

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # ------------------------------------------------------------------ #
    # search — search + optionally download satellite scenes
    #
    # Config fields for the chosen downloader are passed as extra --KEY VALUE
    # flags and resolved dynamically at runtime.
    # Use --list-options to see all fields for the selected downloader.
    # ------------------------------------------------------------------ #
    p_search = sub.add_parser(
        "search",
        help="Search (and optionally download) satellite scenes",
        description=(
            "Search for scenes using any registered downloader.\n"
            "Downloader config fields are passed as extra --KEY VALUE flags.\n"
            "Run with --list-options to see all available fields for the selected downloader."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    g_dl = p_search.add_argument_group("downloader")
    g_dl.add_argument(
        "--list-downloaders", action="store_true",
        help="Print all registered downloaders and exit",
    )
    g_dl.add_argument(
        "-N", "--name", metavar="STR", default="S1_SLC", dest="downloader_name",
        help="Downloader name (default: S1_SLC; see --list-downloaders)",
    )
    g_dl.add_argument(
        "--list-options", action="store_true",
        help="Print all additional config fields for the selected downloader",
    )
    g_dl.add_argument("-w", "--workdir", metavar="PATH",
                      help="Working directory (default: current directory)")
    g_dl.add_argument(
        "--AOI", nargs="+", metavar="AOI",
        help="Area of interest: shapefile/GeoJSON path, WKT string, or 4 floats W S E N. "
             "Sets intersectsWith automatically.",
    )

    g_pairs = p_search.add_argument_group("pair selection  (requires --select-pairs)")
    g_pairs.add_argument(
        "--select-pairs", action="store_true", dest="select_pairs",
        help="Select interferogram pairs after search and save to pairs.json",
    )
    g_pairs.add_argument(
        "--dt-targets", nargs="+", type=int, default=[6, 12, 24, 36, 48, 72, 96],
        metavar="DAYS", help="Target temporal spacings in days (default: 6 12 24 36 48 72 96)",
    )
    g_pairs.add_argument("--dt-tol",  type=int,   default=3,     metavar="DAYS", help="Temporal tolerance in days (default: 3)")
    g_pairs.add_argument("--dt-max",  type=int,   default=120,   metavar="DAYS", help="Max temporal baseline in days (default: 120)")
    g_pairs.add_argument("--pb-max",  type=float, default=150.0, metavar="M",    help="Max perpendicular baseline in metres (default: 150.0)")
    g_pairs.add_argument("--min-degree", type=int, default=3,   metavar="INT",   help="Min connections per scene (default: 3)")
    g_pairs.add_argument("--max-degree", type=int, default=999, metavar="INT",   help="Max connections per scene (default: 999)")
    g_pairs.add_argument("--force-connect", action=argparse.BooleanOptionalAction, default=True,
                         help="Force connectivity for isolated scenes (default: True)")
    g_pairs.add_argument("--sp-workers", type=int, default=8, metavar="INT",
                         help="Threads for baseline API fallback (default: 8)")
    g_pairs.add_argument("--pairs-output", metavar="PATH", default=None,
                         help="Output file for pairs (default: <workdir>/pairs.json)")

    g_down = p_search.add_argument_group("download")
    g_down.add_argument("-d", "--download",    action="store_true", help="Download scenes after search")
    g_down.add_argument("-O", "--orbit-files", action="store_true", help="Also download orbit files (S1 only)")
    g_down.add_argument("--workers", metavar="INT", type=int, default=3,
                        help="Parallel download workers (default: 3)")
    g_down.add_argument("--footprint", metavar="PATH",
                        help="Save footprint map image to this path")

    # ------------------------------------------------------------------ #
    # submit — build pairs + submit to HyP3
    # ------------------------------------------------------------------ #
    p_submit = sub.add_parser("submit", help="Submit InSAR pairs to HyP3")
    _add_workdir(p_submit)
    pairs_group = p_submit.add_mutually_exclusive_group(required=True)
    pairs_group.add_argument("--pairs-file", metavar="PATH",
                             help='JSON file with list of ["ref", "sec"] pairs')
    pairs_group.add_argument("--pairs", metavar='"ref,sec"', nargs="+",
                             help='Inline pairs as "reference,secondary" strings')
    p_submit.add_argument("--looks",         metavar="STR", default="20x4",
                          help="Look factor (default: 20x4)")
    p_submit.add_argument("--no-water-mask", action="store_true",
                          help="Disable water masking")
    p_submit.add_argument("--name-prefix",   metavar="STR", default="ifg",
                          help="Job name prefix (default: ifg)")
    _add_credential_pool(p_submit)

    # ------------------------------------------------------------------ #
    # refresh — pull latest statuses
    # ------------------------------------------------------------------ #
    p_refresh = sub.add_parser("refresh", help="Refresh HyP3 job statuses")
    _add_workdir(p_refresh)
    _add_job_file(p_refresh)

    # ------------------------------------------------------------------ #
    # download-results — download succeeded job outputs
    # ------------------------------------------------------------------ #
    p_dl = sub.add_parser("download-results", help="Download completed HyP3 job outputs")
    _add_workdir(p_dl)
    _add_job_file(p_dl)

    # ------------------------------------------------------------------ #
    # retry — resubmit failed jobs
    # ------------------------------------------------------------------ #
    p_retry = sub.add_parser("retry", help="Resubmit failed HyP3 jobs")
    _add_workdir(p_retry)
    _add_job_file(p_retry)

    # ------------------------------------------------------------------ #
    # watch — poll until all jobs complete, downloading as they finish
    # ------------------------------------------------------------------ #
    p_watch = sub.add_parser("watch",
                              help="Poll HyP3 until all jobs complete, downloading results as they succeed")
    _add_workdir(p_watch)
    _add_job_file(p_watch)
    p_watch.add_argument("--interval", metavar="SEC", type=int, default=300,
                         help="Seconds between refreshes (default: 300)")

    # ------------------------------------------------------------------ #
    # credits — show remaining processing credits
    # ------------------------------------------------------------------ #
    p_credits = sub.add_parser("credits", help="Show remaining HyP3 processing credits")
    _add_workdir(p_credits)
    _add_credential_pool(p_credits)

    # ------------------------------------------------------------------ #
    # prep — prepare HyP3 outputs for MintPy
    # ------------------------------------------------------------------ #
    p_prep = sub.add_parser("prep", help="Prepare HyP3 outputs for MintPy (unzip, clip, align)")
    _add_workdir(p_prep)

    # ------------------------------------------------------------------ #
    # analyze — run MintPy SBAS time-series
    # ------------------------------------------------------------------ #
    p_analyze = sub.add_parser("analyze", help="Run MintPy SBAS time-series analysis")
    _add_workdir(p_analyze)
    p_analyze.add_argument("--steps", metavar="STEP", nargs="+",
                           help="Specific MintPy steps to run (default: full workflow)")
    p_analyze.add_argument("--prep-first", action="store_true",
                           help="Run prep_data before the analysis")

    return parser


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------

def _resolve_workdir(raw: str | None) -> Path:
    return Path(raw).expanduser().resolve() if raw else Path.cwd()


def _resolve_job_file(workdir: Path, override: str | None) -> Path | None:
    if override:
        return Path(override).expanduser().resolve()
    default = workdir / "hyp3_jobs.json"
    return default if default.is_file() else None


def _load_credential_pool(path: str | None) -> dict | None:
    if not path:
        return None
    return json.loads(Path(path).expanduser().resolve().read_text())


def _parse_pairs(args) -> list[tuple[str, str]]:
    if args.pairs_file:
        raw = json.loads(Path(args.pairs_file).read_text())
        return [tuple(p) for p in raw]
    pairs = []
    for item in args.pairs:
        parts = [x.strip() for x in item.split(",")]
        if len(parts) != 2:
            print(f"[ERROR] Invalid pair '{item}' — expected 'reference,secondary'", file=sys.stderr)
            sys.exit(1)
        pairs.append((parts[0], parts[1]))
    return pairs


def _fail(result, label: str):
    """Print error and exit if a CommandResult indicates failure."""
    if not result.success:
        print(f"[ERROR] {label}: {result.errors[0] if result.errors else result.message}",
              file=sys.stderr)
        sys.exit(1)


def _load_hyp3_processor(workdir: Path, job_file_override: str | None = None,
                          credential_pool_path: str | None = None):
    """Build a Hyp3_InSAR processor, loading saved jobs when a job file exists."""
    from insarscript import Processor

    overrides: dict = {"workdir": workdir}
    job_file = _resolve_job_file(workdir, job_file_override)
    if job_file:
        overrides["saved_job_path"] = job_file

    pool = _load_credential_pool(credential_pool_path)
    if pool:
        overrides["earthdata_credentials_pool"] = pool

    return Processor.create("Hyp3_InSAR", **overrides)


# ---------------------------------------------------------------------------
# Dynamic config introspection helpers (used by cmd_search)
# ---------------------------------------------------------------------------


def _unwrap_optional(annotation):
    """Extract the non-None type from 'X | None' or 'Optional[X]'."""
    import types as _types
    import typing
    origin = typing.get_origin(annotation)
    # covers both Union[X, None] and X | None (Python 3.10+)
    if origin is typing.Union or isinstance(annotation, getattr(_types, "UnionType", type(None))):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return args[0] if args else str
    return annotation


def _field_argparse_kwargs(annotation, default) -> dict:
    """Return kwargs for ArgumentParser.add_argument() inferred from a type annotation."""
    import typing
    import dataclasses

    base = _unwrap_optional(annotation)
    origin = typing.get_origin(base)

    if base is bool:
        return {"action": argparse.BooleanOptionalAction, "default": default}

    if origin is list:
        inner_args = typing.get_args(base)
        inner = inner_args[0] if inner_args else str
        return {"nargs": "+", "type": inner, "default": default}

    if base in (int, float, str, Path):
        return {"type": str if base is Path else base, "default": default, "metavar": base.__name__.upper()}

    # Fallback for complex types (e.g. tuple, custom classes) — accept as string
    return {"type": str, "default": default, "metavar": "VALUE"}


_SEARCH_SKIP_FIELDS = {"name"}  # handled via CLI flags or internal


def _build_config_parser(config_cls) -> argparse.ArgumentParser:
    """Build an ArgumentParser populated with flags from a config dataclass."""
    import dataclasses
    import typing

    p = argparse.ArgumentParser(add_help=False)
    try:
        hints = typing.get_type_hints(config_cls)
    except Exception:
        hints = {}

    for field in dataclasses.fields(config_cls):
        if field.name in _SEARCH_SKIP_FIELDS:
            continue
        annotation = hints.get(field.name, str)
        if field.default is not dataclasses.MISSING:
            default = field.default
        elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            default = field.default_factory()
        else:
            default = None

        flag = "--" + field.name
        kwargs = _field_argparse_kwargs(annotation, default)
        kwargs["help"] = argparse.SUPPRESS  # hidden; shown only via --list-options
        try:
            p.add_argument(flag, dest=field.name, **kwargs)
        except argparse.ArgumentError:
            pass  # skip duplicate flags (e.g. --workdir already added)

    return p


def _print_config_options(config_cls, downloader_name: str | None = None):
    """Pretty-print all config fields for --list-options."""
    import dataclasses
    import typing

    try:
        hints = typing.get_type_hints(config_cls)
    except Exception:
        hints = {}

    label = f"{downloader_name} downloader" if downloader_name else config_cls.__name__
    print(f"\nConfig fields for {label}:\n")
    print(f"  {'FLAG':<35}  {'TYPE':<25}  DEFAULT")
    print(f"  {'-'*35}  {'-'*25}  {'-'*20}")
    for field in dataclasses.fields(config_cls):
        if field.name in _SEARCH_SKIP_FIELDS:
            continue
        flag = "--" + field.name
        ann = hints.get(field.name, "?")
        if field.default is not dataclasses.MISSING:
            default = repr(field.default)
        elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            default = repr(field.default_factory())
        else:
            default = "(required)"
        print(f"  {flag:<35}  {str(ann):<25}  {default}")
    print()


def _generate_consecutive_pairs(results: dict) -> dict:
    """
    For each (path, frame) stack, sort scenes by date and generate consecutive
    (reference, secondary) pairs.

    Returns
    -------
    dict
        ``{"path_frame": [["ref_scene", "sec_scene"], ...], ...}``
    """
    from dateutil.parser import isoparse

    out = {}
    for key, scenes in results.items():
        sorted_scenes = sorted(scenes, key=lambda s: isoparse(s.properties["startTime"]))
        pairs = [
            [sorted_scenes[i].properties["sceneName"],
             sorted_scenes[i + 1].properties["sceneName"]]
            for i in range(len(sorted_scenes) - 1)
        ]
        if pairs:
            out[f"{key[0]}_{key[1]}"] = pairs
    return out


# ---------------------------------------------------------------------------
# Command handlers  (each one: build instance → call Command → check result)
# ---------------------------------------------------------------------------

def cmd_search(args, extra_args: list[str]):
    import dataclasses
    from insarscript import Downloader
    from insarscript.commands import SearchCommand, SummaryCommand, FootprintCommand, DownloadScenesCommand

    # --list-downloaders
    if args.list_downloaders:
        print("Available downloaders:")
        for name in Downloader.available():
            print(f"  {name}")
        return

    # Resolve downloader class
    if args.downloader_name not in Downloader._registry:
        print(f"[ERROR] Unknown downloader '{args.downloader_name}'. Use --list-downloaders.",
              file=sys.stderr)
        sys.exit(1)
    downloader_cls = Downloader._registry[args.downloader_name]

    # --list-options
    if args.list_options:
        config_cls = getattr(downloader_cls, "default_config", None)
        if config_cls is None:
            print(f"Downloader '{args.downloader_name}' has no config class.")
        else:
            _print_config_options(config_cls, downloader_name=args.downloader_name)
        return

    # Parse extra_args as downloader config overrides
    overrides: dict = {}
    config_cls = getattr(downloader_cls, "default_config", None)
    if config_cls is not None and dataclasses.is_dataclass(config_cls):
        config_parser = _build_config_parser(config_cls)
        config_ns, unknown = config_parser.parse_known_args(extra_args)
        if unknown:
            print(f"[ERROR] Unknown flags for '{args.downloader_name}': {unknown}", file=sys.stderr)
            sys.exit(1)
        for f in dataclasses.fields(config_cls):
            val = getattr(config_ns, f.name, None)
            if val is not None:
                overrides[f.name] = val
    elif extra_args:
        print(f"[WARNING] Extra args ignored (no config dataclass): {extra_args}", file=sys.stderr)

    if args.AOI:
        from insarscript.utils.tool import _to_wkt
        aoi_input = args.AOI
        if len(aoi_input) == 4:
            try:
                aoi_input = [float(x) for x in aoi_input]
            except ValueError:
                pass  # not floats — treat as single-string WKT or path
        if isinstance(aoi_input, list) and len(aoi_input) == 1:
            aoi_input = aoi_input[0]
        overrides.setdefault("intersectsWith", _to_wkt(aoi_input))

    workdir = _resolve_workdir(args.workdir)
    overrides["workdir"] = workdir

    downloader = Downloader.create(args.downloader_name, **overrides)

    result = SearchCommand(downloader).run()
    _fail(result, "search")

    SummaryCommand(downloader).run()

    if args.footprint:
        FootprintCommand(downloader, save_path=args.footprint).run()

    if args.select_pairs:
        from insarscript.utils import select_pairs as _select_pairs
        from insarscript.utils import plot_pair_network as _plot_pair_network
        pairs, baselines = _select_pairs(
            result.data,
            dt_targets=tuple(args.dt_targets),
            dt_tol=args.dt_tol,
            dt_max=args.dt_max,
            pb_max=args.pb_max,
            min_degree=args.min_degree,
            max_degree=args.max_degree,
            force_connect=args.force_connect,
            max_workers=args.sp_workers,
        )
        figures = _plot_pair_network(pairs, baselines, save_path=args.workdir)
        # Serialize: dict keys are (relativeOrbit, frame) tuples → "path_frame" strings
        if isinstance(pairs, dict):
            serializable = {f"p{k[0]}_f{k[1]}": [list(p) for p in v] for k, v in pairs.items()}
        else:
            serializable = [list(p) for p in pairs]
        pairs_path = (
            Path(args.pairs_output) if args.pairs_output else workdir / "pairs.json"
        )
        pairs_path.parent.mkdir(parents=True, exist_ok=True)
        pairs_path.write_text(json.dumps(serializable, indent=2))
        print(f"[pairs] Saved {sum(len(v) for v in serializable.values()) if isinstance(serializable, dict) else len(serializable)} pairs → {pairs_path}")

    if args.download:
        dl_kwargs: dict = {"max_workers": args.workers}
        if hasattr(downloader, "download") and "download_orbit" in downloader.download.__code__.co_varnames:
            dl_kwargs["download_orbit"] = args.orbit_files
        result = DownloadScenesCommand(downloader, **dl_kwargs).run()
        _fail(result, "download")


def cmd_submit(args):
    from insarscript import Processor
    from insarscript.commands import SubmitCommand, SaveJobsCommand

    workdir = _resolve_workdir(args.workdir)
    pairs = _parse_pairs(args)
    pool = _load_credential_pool(args.credential_pool)

    overrides: dict = {
        "workdir": workdir,
        "pairs": pairs,
        "looks": args.looks,
        "apply_water_mask": not args.no_water_mask,
        "name_prefix": args.name_prefix,
    }
    if pool:
        overrides["earthdata_credentials_pool"] = pool

    processor = Processor.create("Hyp3_InSAR", **overrides)

    result = SubmitCommand(processor).run()
    _fail(result, "submit")
    SaveJobsCommand(processor).run()


def cmd_refresh(args):
    from insarscript.commands import RefreshCommand

    processor = _load_hyp3_processor(
        _resolve_workdir(args.workdir),
        job_file_override=args.job_file,
    )
    result = RefreshCommand(processor).run()
    _fail(result, "refresh")


def cmd_download_results(args):
    from insarscript.commands import RefreshCommand, DownloadResultsCommand

    processor = _load_hyp3_processor(
        _resolve_workdir(args.workdir),
        job_file_override=args.job_file,
    )
    # Refresh first to get latest statuses, then download
    RefreshCommand(processor).run()
    result = DownloadResultsCommand(processor).run()
    _fail(result, "download-results")


def cmd_retry(args):
    from insarscript.commands import RetryCommand

    processor = _load_hyp3_processor(
        _resolve_workdir(args.workdir),
        job_file_override=args.job_file,
    )
    result = RetryCommand(processor).run()
    _fail(result, "retry")


def cmd_watch(args):
    from insarscript.commands import WatchCommand

    processor = _load_hyp3_processor(
        _resolve_workdir(args.workdir),
        job_file_override=args.job_file,
    )
    result = WatchCommand(processor, refresh_interval=args.interval).run()
    _fail(result, "watch")


def cmd_credits(args):
    from insarscript.commands import CheckCreditsCommand

    processor = _load_hyp3_processor(
        _resolve_workdir(args.workdir),
        credential_pool_path=args.credential_pool,
    )
    CheckCreditsCommand(processor).run()


def cmd_prep(args):
    from insarscript import Analyzer
    from insarscript.commands import PrepDataCommand

    workdir = _resolve_workdir(args.workdir)
    analyzer = Analyzer.create("Hyp3_SBAS", workdir=workdir)
    result = PrepDataCommand(analyzer).run()
    _fail(result, "prep")


def cmd_analyze(args):
    from insarscript import Analyzer
    from insarscript.commands import PrepDataCommand, AnalyzeCommand

    workdir = _resolve_workdir(args.workdir)
    analyzer = Analyzer.create("Hyp3_SBAS", workdir=workdir)

    if args.prep_first:
        result = PrepDataCommand(analyzer).run()
        _fail(result, "prep")

    result = AnalyzeCommand(analyzer, steps=args.steps).run()
    _fail(result, "analyze")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    "search":           cmd_search,
    "submit":           cmd_submit,
    "refresh":          cmd_refresh,
    "download-results": cmd_download_results,
    "retry":            cmd_retry,
    "watch":            cmd_watch,
    "credits":          cmd_credits,
    "prep":             cmd_prep,
    "analyze":          cmd_analyze,
}


def main():
    parser = create_parser()
    args, extra_args = parser.parse_known_args()
    if extra_args and args.command != "search":
        print(f"[WARNING] Unrecognized arguments ignored: {extra_args}", file=sys.stderr)
    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    if args.command == "search":
        # No config overrides and no action flags → show search help
        if (not extra_args
                and not args.list_downloaders
                and not args.list_options
                and not args.AOI
                and not args.download
                and not args.select_pairs
                and args.footprint is None):
            parser.parse_args(["search", "--help"])  # prints and exits
        handler(args, extra_args)
    else:
        handler(args)


if __name__ == "__main__":
    main()
