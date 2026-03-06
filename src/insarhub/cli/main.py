"""
HPC-compatible CLI for InSARScript.

Every command handler builds an instance from CLI args, then delegates all
logic to the shared command layer (insarhub.commands). The same command
classes are used by the Panel frontend, so there is no duplicated business logic.

Pipeline subcommands
--------------------
insarhub downloader -N S1_SLC --AOI -113.05 37.74 -112.68 38.00 --start 2021-01-01 --end 2022-01-01
insarhub downloader ... --select-pairs --download --orbit-files
insarhub processor  -N Hyp3_InSAR --workdir /data/bryce
insarhub analyzer   -N Hyp3_SBAS  --workdir /data/bryce --prep-first
insarhub analyzer   -N Hyp3_SBAS  --workdir /data/bryce --prep-only

Job management (under processor)
---------------------------------
insarhub processor refresh          --workdir /data/bryce
insarhub processor download --workdir /data/bryce
insarhub processor retry            --workdir /data/bryce
insarhub processor watch            --workdir /data/bryce --interval 300
insarhub processor credits          --workdir /data/bryce
"""

import argparse
import json
import sys
from pathlib import Path

from insarhub._version import __version__


# ---------------------------------------------------------------------------
# Shared argument helpers
# ---------------------------------------------------------------------------


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
        prog="insarhub",
        description="InSAR processing pipeline CLI",
        epilog="Use 'insarhub <command> --help' for details on each command.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"insarhub {__version__}")

    sub = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    # ------------------------------------------------------------------ #
    # downloader — search + optionally download satellite scenes
    #
    # Config fields for the chosen downloader are passed as extra --KEY VALUE
    # flags and resolved dynamically at runtime.
    # Use --list-options to see all fields for the selected downloader.
    # ------------------------------------------------------------------ #
    p_search = sub.add_parser(
        "downloader",
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
    g_dl.add_argument(
        "--stacks", nargs="+", metavar="PATH:FRAME",
        help="Select specific track/frame stacks as PATH:FRAME tokens, "
             "e.g. --stacks 100:466 20:118 20:123. "
             "Sets relativeOrbit and frame; takes precedence over --relativeOrbit/--frame.",
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
    # processor — submit + manage InSAR processing jobs
    #
    # Actions: submit | refresh | download | retry | watch | credits
    # Config fields for the chosen processor are passed as extra --KEY VALUE
    # flags (submit only) and resolved dynamically at runtime.
    # ------------------------------------------------------------------ #
    p_proc = sub.add_parser(
        "processor",
        help="Submit and manage InSAR processing jobs",
        description=(
            "Submit interferogram pairs and manage HyP3 job lifecycle.\n"
            "\nActions:\n"
            "  submit           Submit pairs to a registered processor\n"
            "  refresh          Pull latest job statuses from HyP3\n"
            "  download Download completed job outputs\n"
            "  retry            Resubmit failed jobs\n"
            "  watch            Poll until all jobs complete\n"
            "  credits          Show remaining HyP3 processing credits\n"
            "\nRun 'insarhub processor <action> --help' for action details."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_proc.add_argument(
        "--list-processors", action="store_true",
        help="Print all registered processors and exit",
    )
    proc_sub = p_proc.add_subparsers(dest="proc_action", required=False, metavar="ACTION")

    # --- submit -------------------------------------------------------- #
    p_proc_submit = proc_sub.add_parser(
        "submit",
        help="Submit interferogram pairs to a registered processor",
        description=(
            "Submit pairs to any registered processor (default: Hyp3_InSAR).\n"
            "Processor config fields are passed as extra --KEY VALUE flags.\n"
            "Run with --list-options to see all available fields.\n"
            "When pairs.json has multiple groups (from 'downloader --select-pairs'),\n"
            "a separate job folder is created under workdir for each group."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g_sub = p_proc_submit.add_argument_group("processor")
    g_sub.add_argument(
        "-N", "--name", metavar="STR", default="Hyp3_InSAR", dest="processor_name",
        help="Processor name (default: Hyp3_InSAR; see --list-processors)",
    )
    g_sub.add_argument(
        "--list-options", action="store_true",
        help="Print all config fields for the selected processor and exit",
    )
    g_sub.add_argument("-w", "--workdir", metavar="PATH", default=None,
                       help="Working directory (default: current directory)")
    g_sub.add_argument("--credential-pool", metavar="PATH",
                       help="JSON {username: password} for multi-account HyP3 submission")
    g_sub_common = p_proc_submit.add_argument_group("common processing options")
    g_sub_common.add_argument("--name-prefix", metavar="STR", default="ifg",
                              help="Job name prefix (default: ifg)")
    g_sub_common.add_argument("--max-workers", metavar="INT", type=int, default=4,
                              help="Parallel submission workers (default: 4)")
    g_sub_common.add_argument("--dry-run", action="store_true",
                              help="Print what would be submitted without sending any jobs to HyP3")
    g_sub_pairs = p_proc_submit.add_argument_group(
        "pairs input",
        "Provide pairs explicitly, or omit to auto-load pairs.json from workdir",
    )
    g_sub_pairs.add_argument(
        "--pairs-file", metavar="PATH",
        help="JSON file from 'downloader --select-pairs' (flat list or grouped dict)",
    )
    g_sub_pairs.add_argument(
        "--pairs", metavar='"ref,sec"', nargs="+",
        help='Inline pairs as "reference,secondary" strings (single group)',
    )

    # --- refresh ------------------------------------------------------- #
    p_proc_refresh = proc_sub.add_parser("refresh", help="Refresh HyP3 job statuses")
    p_proc_refresh.add_argument("-w", "--workdir", metavar="PATH", default=None,
                                help="Working directory (default: current directory)")
    _add_job_file(p_proc_refresh)

    # --- download ---------------------------------------------- #
    p_proc_dl = proc_sub.add_parser("download",
                                    help="Download completed HyP3 job outputs")
    p_proc_dl.add_argument("-w", "--workdir", metavar="PATH", default=None,
                           help="Working directory (default: current directory)")
    _add_job_file(p_proc_dl)

    # --- retry --------------------------------------------------------- #
    p_proc_retry = proc_sub.add_parser("retry", help="Resubmit failed HyP3 jobs")
    p_proc_retry.add_argument("-w", "--workdir", metavar="PATH", default=None,
                              help="Working directory (default: current directory)")
    _add_job_file(p_proc_retry)

    # --- watch --------------------------------------------------------- #
    p_proc_watch = proc_sub.add_parser(
        "watch", help="Poll HyP3 until all jobs complete, downloading results as they succeed")
    p_proc_watch.add_argument("-w", "--workdir", metavar="PATH", default=None,
                              help="Working directory (default: current directory)")
    _add_job_file(p_proc_watch)
    p_proc_watch.add_argument("--interval", metavar="SEC", type=int, default=300,
                              help="Seconds between refreshes (default: 300)")

    # --- credits ------------------------------------------------------- #
    p_proc_credits = proc_sub.add_parser("credits",
                                         help="Show remaining HyP3 processing credits")
    p_proc_credits.add_argument("-w", "--workdir", metavar="PATH", default=None,
                                help="Working directory (default: current directory)")
    _add_credential_pool(p_proc_credits)

    # ------------------------------------------------------------------ #
    # analyzer — prepare + run MintPy SBAS time-series analysis
    #
    # Config fields for the chosen analyzer are passed as extra --KEY VALUE
    # flags and resolved dynamically at runtime.
    # ------------------------------------------------------------------ #
    p_analyzer = sub.add_parser(
        "analyzer",
        help="Prepare data and run MintPy SBAS time-series analysis",
        description=(
            "Run any registered analyzer (default: Hyp3_SBAS).\n"
            "Analyzer config fields are passed as extra --KEY VALUE flags.\n"
            "Run with --list-options to see all available fields."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    g_az = p_analyzer.add_argument_group("analyzer")
    g_az.add_argument(
        "--list-analyzers", action="store_true",
        help="Print all registered analyzers and exit",
    )
    g_az.add_argument(
        "-N", "--name", metavar="STR", default="Hyp3_SBAS", dest="analyzer_name",
        help="Analyzer name (default: Hyp3_SBAS; see --list-analyzers)",
    )
    g_az.add_argument(
        "--list-options", action="store_true",
        help="Print all additional config fields for the selected analyzer",
    )
    g_az.add_argument("-w", "--workdir", metavar="PATH", default=None,
                      help="Working directory containing HyP3 results (default: current directory)")

    g_az_common = p_analyzer.add_argument_group("common analysis options")
    g_az_common.add_argument("--steps", metavar="STEP", nargs="+",
                             help="Specific MintPy steps to run (default: full workflow)")
    g_az_common.add_argument("--prep-first", action="store_true",
                             help="Run prep_data before analysis")
    g_az_common.add_argument("--prep-only", action="store_true",
                             help="Run only prep_data and exit")
    g_az_common.add_argument("--debug", action="store_true",
                             help="Enable MintPy debug mode")

    return parser


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------

def _resolve_workdir(raw: str | None) -> Path:
    return Path(raw).expanduser().resolve() if raw else Path.cwd()


def _find_job_files(job_dir: Path, override: str | None = None) -> list[Path]:
    """Return all hyp3*.json job files in job_dir, or just the override file if given."""
    if override:
        return [Path(override).expanduser().resolve()]
    return sorted(job_dir.glob("hyp3*.json"))


def _load_credential_pool(path: str | None) -> dict | None:
    from insarhub.utils import earth_credit_pool
    if not path:
        return None
    return earth_credit_pool(Path(path).expanduser().resolve())



def _fail(result, label: str):
    """Print error and exit if a CommandResult indicates failure."""
    if not result.success:
        print(f"[ERROR] {label}: {result.errors[0] if result.errors else result.message}",
              file=sys.stderr)
        sys.exit(1)


def _iter_job_dirs(workdir: Path, job_file_override: str | None) -> list[Path]:
    """
    Return the list of directories to operate on for lifecycle commands.

    Resolution order:
      1. --job-file given  → parent directory of that file only
      2. p*_f* subdirs that contain any hyp3*.json  → each subdir
      3. workdir itself  (flat / single-group case)
    """
    if job_file_override:
        return [Path(job_file_override).expanduser().resolve().parent]
    subdirs = sorted(
        d for d in workdir.iterdir()
        if d.is_dir() and _parse_group_key(d.name) and any(d.glob("hyp3*.json"))
    )
    return subdirs if subdirs else [workdir]


def _load_hyp3_processor(workdir: Path, job_file: Path | None = None,
                          credential_pool_path: str | None = None):
    """Build a Hyp3_InSAR processor, loading saved jobs from job_file when provided."""
    from insarhub import Processor

    overrides: dict = {"workdir": workdir}
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
    """Extract the non-None type from 'X | None' or 'Optional[X]'.

    When the union contains both a scalar and list type (e.g. int | list[int] | None),
    prefer the list type so CLI flags accept multiple values with nargs="+".
    """
    import types as _types
    import typing
    origin = typing.get_origin(annotation)
    # covers both Union[X, None] and X | None (Python 3.10+)
    if origin is typing.Union or isinstance(annotation, getattr(_types, "UnionType", type(None))):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        # Prefer list[X] over scalar X so multi-value fields get nargs="+"
        list_types = [a for a in args if typing.get_origin(a) is list]
        return list_types[0] if list_types else (args[0] if args else str)
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

# Fields handled by static flags or internal state in cmd_processor
_SUBMIT_SKIP_FIELDS = {
    "name", "workdir", "pairs", "saved_job_path",
    "earthdata_credentials_pool",
    "name_prefix", "max_workers",
}

# Fields handled by static flags or internal state in cmd_analyzer
_ANALYZER_SKIP_FIELDS = {"name", "workdir", "debug"}


def _build_config_parser(config_cls, skip_fields: set | None = None) -> argparse.ArgumentParser:
    """Build an ArgumentParser populated with flags from a config dataclass."""
    import dataclasses
    import typing

    if skip_fields is None:
        skip_fields = _SEARCH_SKIP_FIELDS

    p = argparse.ArgumentParser(add_help=False)
    try:
        hints = typing.get_type_hints(config_cls)
    except Exception:
        hints = {}

    for field in dataclasses.fields(config_cls):
        if field.name in skip_fields:
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


def _print_config_options(config_cls, display_label: str | None = None,
                          skip_fields: set | None = None):
    """Pretty-print all config fields for --list-options."""
    import dataclasses
    import typing

    if skip_fields is None:
        skip_fields = _SEARCH_SKIP_FIELDS

    try:
        hints = typing.get_type_hints(config_cls)
    except Exception:
        hints = {}

    label = display_label or config_cls.__name__
    print(f"\nConfig fields for {label}:\n")
    print(f"  {'FLAG':<35}  {'TYPE':<25}  DEFAULT")
    print(f"  {'-'*35}  {'-'*25}  {'-'*20}")
    for field in dataclasses.fields(config_cls):
        if field.name in skip_fields:
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


def _parse_group_key(key: str) -> tuple[int, int] | None:
    """Parse 'p100_f466' → (100, 466); return None if key doesn't match pattern."""
    import re
    m = re.fullmatch(r"p(\d+)_f(\d+)", key)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _load_pairs(args, workdir: Path) -> dict | list:
    """
    Return pairs as either:
      dict  – {"p100_f466": [["ref", "sec"], ...], ...}  (multi-group from select_pairs)
      list  – [["ref", "sec"], ...]                       (flat / inline)

    Resolution order:
      1. --pairs-file  (explicit file)
      2. --pairs       (inline on CLI)
      3. p*_f* subdirs containing pairs_p*_f*.json  (auto, multi-group)
      4. workdir/pairs.json  (auto, single group)
    """
    if getattr(args, "pairs_file", None):
        return json.loads(Path(args.pairs_file).expanduser().resolve().read_text())
    if getattr(args, "pairs", None):
        result = []
        for item in args.pairs:
            parts = [x.strip() for x in item.split(",")]
            if len(parts) != 2:
                print(f"[ERROR] Invalid pair '{item}' — expected 'reference,secondary'",
                      file=sys.stderr)
                sys.exit(1)
            result.append(parts)
        return result
    # Auto-detect per-group subdirs created by `downloader --select-pairs`
    subdir_pairs: dict[str, list] = {}
    for subdir in sorted(workdir.iterdir()) if workdir.is_dir() else []:
        pf = _parse_group_key(subdir.name)
        if pf is None or not subdir.is_dir():
            continue
        pjson = subdir / f"pairs_{subdir.name}.json"
        if pjson.is_file():
            subdir_pairs[subdir.name] = json.loads(pjson.read_text())
    if subdir_pairs:
        print(f"[pairs] Auto-loading {len(subdir_pairs)} group(s) from subdirs")
        return subdir_pairs
    # Fall back to flat pairs.json
    auto = workdir / "pairs.json"
    if auto.is_file():
        print(f"[pairs] Auto-loading {auto}")
        return json.loads(auto.read_text())
    print("[ERROR] No pairs provided. Use --pairs-file, --pairs, or run "
          "'insarhub downloader --select-pairs' first.", file=sys.stderr)
    sys.exit(1)


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

def cmd_downloader(args, extra_args: list[str]):
    import dataclasses
    from insarhub import Downloader
    from insarhub.commands import SearchCommand, SummaryCommand, FootprintCommand, DownloadScenesCommand

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
            _print_config_options(config_cls,
                                  display_label=f"{args.downloader_name} downloader",
                                  skip_fields=_SEARCH_SKIP_FIELDS)
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
        from insarhub.utils.tool import _to_wkt
        aoi_input = args.AOI
        if len(aoi_input) == 4:
            try:
                aoi_input = [float(x) for x in aoi_input]
            except ValueError:
                pass  # not floats — treat as single-string WKT or path
        if isinstance(aoi_input, list) and len(aoi_input) == 1:
            aoi_input = aoi_input[0]
        overrides.setdefault("intersectsWith", _to_wkt(aoi_input))

    stacks_filter: list[tuple] | None = None
    if args.stacks:
        parsed = []
        for token in args.stacks:
            parts = token.split(":")
            if len(parts) != 2:
                print(f"[ERROR] Invalid --stacks token '{token}' — expected PATH:FRAME", file=sys.stderr)
                sys.exit(1)
            try:
                parsed.append((int(parts[0]), int(parts[1])))
            except ValueError:
                print(f"[ERROR] PATH and FRAME must be integers, got '{token}'", file=sys.stderr)
                sys.exit(1)
        # Broad search to reduce API response; exact-pair filter applied after search
        overrides["relativeOrbit"] = [p for p, _ in parsed]
        overrides["frame"]         = [f for _, f in parsed]
        stacks_filter = parsed

    workdir = _resolve_workdir(args.workdir)
    overrides["workdir"] = workdir

    downloader = Downloader.create(args.downloader_name, **overrides)

    result = SearchCommand(downloader).run()
    _fail(result, "search")

    if stacks_filter:
        from insarhub.commands import FilterCommand
        _fail(FilterCommand(downloader, {"path_frame": stacks_filter}).run(), "filter")

    SummaryCommand(downloader).run()

    if args.footprint:
        FootprintCommand(downloader, save_path=args.footprint).run()

    if args.select_pairs:
        from insarhub.utils import select_pairs as _select_pairs
        from insarhub.utils import plot_pair_network as _plot_pair_network
        pairs, baselines = _select_pairs(  # type: ignore[misc]
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
        if isinstance(pairs, dict):
            # Multiple groups → one subdir per (path, frame)
            for (path, frame), group_pairs in pairs.items():
                subdir = workdir / f"p{path}_f{frame}"
                subdir.mkdir(parents=True, exist_ok=True)
                pjson = subdir / f"pairs_p{path}_f{frame}.json"
                pjson.write_text(json.dumps([list(p) for p in group_pairs], indent=2))
                _plot_pair_network(
                    group_pairs, baselines[(path, frame)],
                    title=f"Interferogram Network — P{path}/F{frame}",
                    save_path=subdir / f"network_p{path}_f{frame}.png",
                )
                print(f"[pairs] p{path}_f{frame}: {len(group_pairs)} pairs → {pjson}")
        else:
            # Single group → flat pairs.json in workdir
            pairs_path = (
                Path(args.pairs_output) if args.pairs_output else workdir / "pairs.json"
            )
            pairs_path.parent.mkdir(parents=True, exist_ok=True)
            pairs_path.write_text(json.dumps([list(p) for p in pairs], indent=2))
            _plot_pair_network(pairs, baselines, save_path=workdir / "network.png")
            print(f"[pairs] Saved {len(pairs)} pairs → {pairs_path}")

    if args.download:
        dl_kwargs: dict = {"max_workers": args.workers}
        if hasattr(downloader, "download") and "download_orbit" in downloader.download.__code__.co_varnames:
            dl_kwargs["download_orbit"] = args.orbit_files
        result = DownloadScenesCommand(downloader, **dl_kwargs).run()
        _fail(result, "download")


def cmd_processor(args, extra_args: list[str]):
    # --list-processors (works without a sub-action)
    if getattr(args, "list_processors", False):
        from insarhub import Processor
        print("Available processors:")
        for name in Processor.available():
            print(f"  {name}")
        return

    action = getattr(args, "proc_action", None)

    if action == "submit":
        _proc_submit(args, extra_args)
    elif action == "refresh":
        _proc_refresh(args)
    elif action == "download":
        _proc_download_results(args)
    elif action == "retry":
        _proc_retry(args)
    elif action == "watch":
        _proc_watch(args)
    elif action == "credits":
        _proc_credits(args)
    else:
        # No action → help is shown by main() before reaching here
        pass


def _proc_submit(args, extra_args: list[str]):
    import dataclasses
    from insarhub import Processor
    from insarhub.commands import SubmitCommand, SaveJobsCommand

    processor_name = getattr(args, "processor_name", "Hyp3_InSAR")

    if processor_name not in Processor._registry:
        print(f"[ERROR] Unknown processor '{processor_name}'. Use --list-processors.",
              file=sys.stderr)
        sys.exit(1)
    processor_cls = Processor._registry[processor_name]

    if getattr(args, "list_options", False):
        config_cls = getattr(processor_cls, "default_config", None)
        if config_cls is None:
            print(f"Processor '{processor_name}' has no config class.")
        else:
            _print_config_options(config_cls,
                                  display_label=f"{processor_name} processor",
                                  skip_fields=_SUBMIT_SKIP_FIELDS)
        return

    overrides: dict = {}
    config_cls = getattr(processor_cls, "default_config", None)
    if config_cls is not None and dataclasses.is_dataclass(config_cls):
        config_parser = _build_config_parser(config_cls, skip_fields=_SUBMIT_SKIP_FIELDS)
        config_ns, unknown = config_parser.parse_known_args(extra_args)
        if unknown:
            print(f"[ERROR] Unknown flags for '{processor_name}': {unknown}", file=sys.stderr)
            sys.exit(1)
        for f in dataclasses.fields(config_cls):
            if f.name in _SUBMIT_SKIP_FIELDS:
                continue
            val = getattr(config_ns, f.name, None)
            if val is not None:
                overrides[f.name] = val
    elif extra_args:
        print(f"[WARNING] Extra args ignored (no config dataclass): {extra_args}", file=sys.stderr)

    overrides["name_prefix"] = args.name_prefix
    overrides["max_workers"] = args.max_workers

    pool = _load_credential_pool(getattr(args, "credential_pool", None))
    if pool:
        overrides["earthdata_credentials_pool"] = pool

    workdir = _resolve_workdir(args.workdir)
    pairs_data = _load_pairs(args, workdir)

    groups: dict[tuple[int, int] | None, list] = (
        {_parse_group_key(k): [tuple(p) for p in v] for k, v in pairs_data.items()}
        if isinstance(pairs_data, dict)
        else {None: [tuple(p) for p in pairs_data]}
    )

    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        print(f"[dry-run] Processor : {processor_name}")
        print(f"[dry-run] Workdir   : {workdir}")
        print(f"[dry-run] Groups    : {len(groups)}")

    for pf, group_pairs in groups.items():
        folder = f"p{pf[0]}_f{pf[1]}" if pf else None
        job_dir = workdir / folder if folder else workdir
        group_prefix = (f"{args.name_prefix}_p{pf[0]}_f{pf[1]}"
                        if pf else args.name_prefix)
        tag = f"[{folder}] " if folder else ""
        if dry_run:
            print(f"\n{tag}Would submit {len(group_pairs)} pairs → {job_dir}")
            print(f"{tag}  name_prefix : {group_prefix}")
            for ref, sec in group_pairs:
                print(f"{tag}  {ref}  ↔  {sec}")
            continue
        job_dir.mkdir(parents=True, exist_ok=True)
        group_overrides = {**overrides, "workdir": job_dir, "pairs": group_pairs,
                           "name_prefix": group_prefix}
        processor = Processor.create(processor_name, **group_overrides)
        print(f"{tag}Submitting {len(group_pairs)} pairs → {job_dir}")
        result = SubmitCommand(processor).run()
        _fail(result, f"submit {folder or ''}".strip())
        SaveJobsCommand(processor).run()


def _proc_refresh(args):
    from insarhub.commands import RefreshCommand
    workdir = _resolve_workdir(args.workdir)
    for job_dir in _iter_job_dirs(workdir, args.job_file):
        for jf in _find_job_files(job_dir, args.job_file):
            tag = f"[{job_dir.name}/{jf.name}] " if job_dir != workdir else f"[{jf.name}] "
            print(f"{tag}Refreshing…")
            processor = _load_hyp3_processor(job_dir, job_file=jf)
            _fail(RefreshCommand(processor).run(), f"refresh {tag}".strip())


def _proc_download_results(args):
    from insarhub.commands import RefreshCommand, DownloadResultsCommand
    workdir = _resolve_workdir(args.workdir)
    for job_dir in _iter_job_dirs(workdir, args.job_file):
        for jf in _find_job_files(job_dir, args.job_file):
            tag = f"[{job_dir.name}/{jf.name}] " if job_dir != workdir else f"[{jf.name}] "
            print(f"{tag}Downloading results…")
            processor = _load_hyp3_processor(job_dir, job_file=jf)
            RefreshCommand(processor).run()
            _fail(DownloadResultsCommand(processor).run(), f"download {tag}".strip())


def _proc_retry(args):
    from insarhub.commands import RetryCommand
    workdir = _resolve_workdir(args.workdir)
    for job_dir in _iter_job_dirs(workdir, args.job_file):
        for jf in _find_job_files(job_dir, args.job_file):
            tag = f"[{job_dir.name}/{jf.name}] " if job_dir != workdir else f"[{jf.name}] "
            print(f"{tag}Retrying failed jobs…")
            processor = _load_hyp3_processor(job_dir, job_file=jf)
            _fail(RetryCommand(processor).run(), f"retry {tag}".strip())


def _proc_watch(args):
    import io
    import time
    from contextlib import redirect_stdout, redirect_stderr
    from tqdm import tqdm
    from hyp3_sdk import Batch as HyP3Batch

    workdir = _resolve_workdir(args.workdir)
    # Build (job_dir, job_file, processor) for every job file across all dirs
    from insarhub.processor.hyp3_base import Hyp3Base
    entries: list[tuple[Path, Path, Hyp3Base]] = []
    for job_dir in _iter_job_dirs(workdir, args.job_file):
        for jf in _find_job_files(job_dir, args.job_file):
            entries.append((job_dir, jf, _load_hyp3_processor(job_dir, job_file=jf)))

    downloaded: dict[Path, set] = {jf: set() for _, jf, _ in entries}

    def _bar_label(job_dir: Path, jf: Path) -> str:
        prefix = job_dir.name if job_dir != workdir else ""
        return f"[{prefix}/{jf.name}]" if prefix else f"[{jf.name}]"

    bars = [
        tqdm(
            total=0,
            desc=_bar_label(d, jf),
            position=i,
            leave=True,
            bar_format="{desc}: {postfix}",
            file=sys.stderr,
        )
        for i, (d, jf, _) in enumerate(entries)
    ]
    for bar in bars:
        bar.set_postfix_str("waiting for first refresh…")

    tqdm.write(f"Watching {len(entries)} job file(s), refreshing every {args.interval}s. Ctrl+C to stop.")

    try:
        while True:
            done_count = 0
            for i, (job_dir, jf, processor) in enumerate(entries):
                sink = io.StringIO()
                with redirect_stdout(sink), redirect_stderr(sink):
                    processor.refresh()

                total = active = failed = succeeded = 0
                new_succeeded: dict = {}
                for username, batch in processor.batchs.items():
                    total += len(batch)
                    active += len(batch.filter_jobs(
                        running=True, pending=True, succeeded=False, failed=False))
                    failed += len(batch.filter_jobs(
                        running=False, pending=False, succeeded=False, failed=True))
                    succ = batch.filter_jobs(
                        running=False, pending=False, succeeded=True, failed=False)
                    succeeded += len(succ)
                    new = [j for j in succ if j.job_id not in downloaded[jf]]
                    if new:
                        new_succeeded[username] = new
                        for j in new:
                            downloaded[jf].add(j.job_id)

                ts = time.strftime("%H:%M:%S")
                bars[i].set_postfix_str(
                    f"[{ts}] {succeeded}/{total} Done | {active} Running | {failed} Failed"
                )

                if new_succeeded:
                    label = _bar_label(job_dir, jf)
                    n = sum(len(v) for v in new_succeeded.values())
                    old_batchs = processor.batchs
                    processor.batchs = {u: HyP3Batch(jobs) for u, jobs in new_succeeded.items()}
                    with tqdm.external_write_mode(file=sys.stderr):
                        print(f"{label} {n} job(s) succeeded — downloading…")
                        processor.download()
                    processor.batchs = old_batchs

                if total > 0 and active == 0:
                    done_count += 1

            if done_count == len(entries):
                tqdm.write("All groups complete.")
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        tqdm.write("\nStopped by user.")
    finally:
        for bar in bars:
            bar.close()


def _proc_credits(args):
    from insarhub.commands import CheckCreditsCommand
    workdir = _resolve_workdir(args.workdir)
    # credits is per-credential-pool, not per job_dir — run once
    processor = _load_hyp3_processor(workdir, credential_pool_path=args.credential_pool)
    CheckCreditsCommand(processor).run()


def cmd_analyzer(args, extra_args: list[str]):
    import dataclasses
    from insarhub import Analyzer
    from insarhub.commands import PrepDataCommand, AnalyzeCommand

    if args.list_analyzers:
        print("Available analyzers:")
        for name in Analyzer.available():
            print(f"  {name}")
        return

    if args.analyzer_name not in Analyzer._registry:
        print(f"[ERROR] Unknown analyzer '{args.analyzer_name}'. Use --list-analyzers.",
              file=sys.stderr)
        sys.exit(1)
    analyzer_cls = Analyzer._registry[args.analyzer_name]

    if args.list_options:
        config_cls = getattr(analyzer_cls, "default_config", None)
        if config_cls is None:
            print(f"Analyzer '{args.analyzer_name}' has no config class.")
        else:
            _print_config_options(config_cls,
                                  display_label=f"{args.analyzer_name} analyzer",
                                  skip_fields=_ANALYZER_SKIP_FIELDS)
        return

    # Parse extra_args as analyzer config overrides
    overrides: dict = {}
    config_cls = getattr(analyzer_cls, "default_config", None)
    if config_cls is not None and dataclasses.is_dataclass(config_cls):
        config_parser = _build_config_parser(config_cls, skip_fields=_ANALYZER_SKIP_FIELDS)
        config_ns, unknown = config_parser.parse_known_args(extra_args)
        if unknown:
            print(f"[ERROR] Unknown flags for '{args.analyzer_name}': {unknown}",
                  file=sys.stderr)
            sys.exit(1)
        for f in dataclasses.fields(config_cls):
            if f.name in _ANALYZER_SKIP_FIELDS:
                continue
            val = getattr(config_ns, f.name, None)
            if val is not None:
                overrides[f.name] = val
    elif extra_args:
        print(f"[WARNING] Extra args ignored (no config dataclass): {extra_args}",
              file=sys.stderr)

    overrides["debug"] = args.debug
    workdir = _resolve_workdir(args.workdir)
    analyzer = Analyzer.create(args.analyzer_name, workdir=workdir, **overrides)

    if args.prep_only:
        result = PrepDataCommand(analyzer).run()
        _fail(result, "prep")
        return

    if args.prep_first:
        result = PrepDataCommand(analyzer).run()
        _fail(result, "prep")

    result = AnalyzeCommand(analyzer, steps=args.steps).run()
    _fail(result, "analyze")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    "downloader": cmd_downloader,
    "processor":  cmd_processor,
    "analyzer":   cmd_analyzer,
}


def main():
    parser = create_parser()
    args, extra_args = parser.parse_known_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    _EXTRA_ARGS_COMMANDS = {"downloader", "processor", "analyzer"}
    if extra_args and args.command not in _EXTRA_ARGS_COMMANDS:
        print(f"[WARNING] Unrecognized arguments ignored: {extra_args}", file=sys.stderr)
    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    if args.command == "downloader":
        if (not extra_args
                and not args.list_downloaders
                and not args.list_options
                and not args.AOI
                and not args.download
                and not args.select_pairs
                and args.footprint is None):
            parser.parse_args(["downloader", "--help"])  # prints and exits
        handler(args, extra_args)
    elif args.command == "processor":
        if (not getattr(args, "list_processors", False)
                and not getattr(args, "proc_action", None)):
            parser.parse_args(["processor", "--help"])  # prints and exits
        handler(args, extra_args)
    else:
        # analyzer (and any future extra-args commands)
        handler(args, extra_args)


if __name__ == "__main__":
    main()
