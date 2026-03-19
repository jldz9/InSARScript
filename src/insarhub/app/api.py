# -*- coding: utf-8 -*-
"""
FastAPI backend for InSARHub.

Exposes the existing commands layer as REST endpoints.
React frontend calls these endpoints over HTTP.

Run with:
    uvicorn insarhub.app.api:app --reload --port 8000

Interactive API docs (test without any frontend):
    http://localhost:8000/docs
"""

import asyncio
import base64
import dataclasses
import json
import os
import tempfile
import threading as _threading
import uuid
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import wkt as shapely_wkt
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rasterio.crs import CRS
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.transform import from_origin, from_bounds
from pyproj import Transformer

from insarhub.commands.downloader import DownloadScenesCommand, SearchCommand
from insarhub.commands.processor import SaveJobsCommand, SubmitCommand
from insarhub.config import S1_SLC_Config
from insarhub.core.registry import Downloader, Processor, Analyzer
# Import processor/analyzer modules to trigger auto-registration in the registries
import insarhub.downloader.s1_slc       # noqa: F401
import insarhub.processor.hyp3_insar   # noqa: F401
import insarhub.analyzer.hyp3_sbas     # noqa: F401
import insarhub.analyzer.mintpy_base   # noqa: F401


def _dataclass_defaults(cls) -> dict[str, Any]:
    """Return {field_name: default_value} for a dataclass, skipping fields with no default."""
    out: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            try:
                out[f.name] = f.default_factory()           # type: ignore[misc]
            except Exception:
                pass
    return out


def _build_ui_meta(cfg_cls) -> tuple[list[dict], list[dict]]:
    """Extract groups + UI field list from a config dataclass using its ClassVar metadata."""
    groups: list[dict] = list(getattr(cfg_cls, "_ui_groups", []))
    ui_field_meta: dict = getattr(cfg_cls, "_ui_fields", {})
    live = _dataclass_defaults(cfg_cls)
    fields: list[dict] = []
    for key, meta in ui_field_meta.items():
        entry: dict = {"key": key, "label": key, **meta}
        if key in live:
            entry["default"] = live[key]
        fields.append(entry)
    return groups, fields


def _build_registry_meta(registry) -> dict[str, Any]:
    """Dynamically build component metadata from every entry in a registry."""
    result: dict[str, Any] = {}
    for name in registry.available():
        cls = registry._registry[name]
        cfg_cls = getattr(cls, "default_config", None)
        if cfg_cls is None or not dataclasses.is_dataclass(cfg_cls):
            continue
        if not getattr(cfg_cls, "_ui_groups", None):   # skip base classes with no UI metadata
            continue
        groups, fields = _build_ui_meta(cfg_cls)
        result[name] = {
            "label":                name,
            "description":          getattr(cls, "description", ""),
            "compatible_downloader":getattr(cls, "compatible_downloader", None),
            "compatible_processor": getattr(cls, "compatible_processor", None),
            "groups":               groups,
            "fields":               fields,
        }
    return result

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="InSARHub API", version="0.1.0")

# Allow React dev server to call this API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory stores  (good enough for single-user; swap for Redis in production)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}
_stop_events: dict[str, Any] = {}    # job_id → threading.Event for cancellable jobs
_sessions: dict[str, Any] = {}       # session_id → downloader instance
_auth_cache: dict[str, Any] | None = None   # populated at startup, refreshed on demand

# ── Build component metadata dynamically from the registries ─────────────────
_DOWNLOADERS_META: dict[str, Any] = _build_registry_meta(Downloader)
_PROCESSORS_META:  dict[str, Any] = _build_registry_meta(Processor)
_ANALYZERS_META:   dict[str, Any] = _build_registry_meta(Analyzer)

# ── Persistent settings (in-memory; survives the process lifetime) ──────────
def _default_config_values(component_name: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Return {key: default} for every UI field of a registered component."""
    entry = meta.get(component_name, {})
    return {f["key"]: f["default"] for f in entry.get("fields", []) if "default" in f}

_DEFAULT_DOWNLOADER = next(iter(_DOWNLOADERS_META), "")
_DEFAULT_PROCESSOR  = next(iter(_PROCESSORS_META), "")
_DEFAULT_ANALYZER   = next(iter(_ANALYZERS_META),  "")

_TOPBAR_FIELDS = {"intersectsWith", "start", "end"}

def _safe_config_values(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Like _default_config_values but excludes fields owned by the TopBar (AOI, dates)."""
    return {k: v for k, v in _default_config_values(name, meta).items() if k not in _TOPBAR_FIELDS}

_settings: dict[str, Any] = {
    "workdir":              str(Path.cwd()),
    "max_download_workers": 3,
    "downloader":           _DEFAULT_DOWNLOADER,
    "downloader_config":    _safe_config_values(_DEFAULT_DOWNLOADER, _DOWNLOADERS_META),
    "processor":            _DEFAULT_PROCESSOR,
    "processor_config":     _default_config_values(_DEFAULT_PROCESSOR, _PROCESSORS_META),
    "analyzer":             _DEFAULT_ANALYZER,
    # Per-type configs: each analyzer type stores its own config independently
    "analyzer_configs":     {name: _default_config_values(name, _ANALYZERS_META) for name in _ANALYZERS_META},
}


_NETRC     = Path.home() / ".netrc"
_CSDAPI    = Path.home() / ".csdapi"
_CREDIT_POOL = Path.home() / ".credit_pool"

def _netrc_has(host: str) -> bool:
    """Simple string-search check — matches the pattern used throughout the codebase."""
    if not _NETRC.is_file():
        return False
    try:
        return f"machine {host}" in _NETRC.read_text()
    except Exception:
        return False

def _read_credit_pool_pairs() -> list[tuple[str, str]]:
    """Return list of (username, password) from ~/.credit_pool."""
    if not _CREDIT_POOL.is_file():
        return []
    try:
        pairs = []
        for line in _CREDIT_POOL.read_text().splitlines():
            line = line.strip()
            if line and ':' in line:
                user, pwd = line.split(':', 1)
                pairs.append((user.strip(), pwd.strip()))
        return pairs
    except Exception:
        return []

def _check_hyp3_account(username: str | None = None, password: str | None = None) -> dict[str, Any]:
    """Authenticate with HyP3 and return credits.  Uses check_credits() which returns a number."""
    try:
        from hyp3_sdk import HyP3
        kwargs: dict[str, Any] = {}
        if username:
            kwargs["username"] = username
        if password:
            kwargs["password"] = password
        hyp3    = HyP3(**kwargs)
        credits = hyp3.check_credits()   # returns remaining credits as a number
        display      = username
        per_month    = None
        try:
            info = hyp3.my_info()
            if hasattr(info, "__dict__"):
                info = vars(info)
            display   = display or info.get("user_id") or info.get("username")
            per_month = info.get("credits_per_month")
        except Exception:
            pass
        return {
            "username":          display or "—",
            "credits_remaining": credits,
            "credits_per_month": per_month,   # None if not returned by API
        }
    except Exception as e:
        return {"username": username or "—", "error": str(e)}


def _build_auth_status() -> dict[str, Any]:
    """Synchronous helper that computes the full auth-status payload."""
    earthdata_connected = _netrc_has("urs.earthdata.nasa.gov")
    cdse_connected      = _netrc_has("dataspace.copernicus.eu") or _CSDAPI.is_file()
    pool_pairs          = _read_credit_pool_pairs()
    hyp3_main           = _check_hyp3_account()
    credit_pool         = [_check_hyp3_account(u, p) for u, p in pool_pairs]
    return {
        "earthdata_connected": earthdata_connected,
        "cdse_connected":      cdse_connected,
        "hyp3":                hyp3_main,
        "credit_pool":         credit_pool,
        "credit_pool_exists":  _CREDIT_POOL.is_file() and bool(pool_pairs),
    }

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    west: float  = Field(..., example=-113.05)
    south: float = Field(..., example=37.74)
    east: float  = Field(..., example=-112.68)
    north: float = Field(..., example=38.00)
    wkt: str | None = Field(default=None, description="WKT polygon — overrides bbox when provided")
    start: str | None = Field(default=None, example="2021-01-01")
    end: str | None   = Field(default=None, example="2022-01-01")
    workdir: str = Field(default=".")
    maxResults: int | None = Field(default=2000)
    # Filters
    beamMode:        str | None       = Field(default=None, description="IW | EW | SM | WV")
    polarization:    list[str] | None = Field(default=None, description="e.g. ['VV', 'VV+VH']")
    flightDirection: str | None       = Field(default=None, description="ASCENDING | DESCENDING")
    pathStart:       int | None       = Field(default=None, description="Relative orbit start (path)")
    pathEnd:         int | None       = Field(default=None, description="Relative orbit end (path)")
    frameStart:      int | None       = Field(default=None, description="ASF frame start")
    frameEnd:        int | None       = Field(default=None, description="ASF frame end")
    # Granule name search — when set, overrides all spatial/temporal parameters
    granule_names:   list[str] | None = Field(default=None, description="List of granule/scene names")


class DownloadRequest(BaseModel):
    session_id: str = Field(..., description="session_id returned by /api/search")
    workdir: str    = Field(..., example="/data/bryce")


class DownloadSceneRequest(BaseModel):
    url:      str            = Field(..., description="Direct ASF download URL for the scene")
    filename: str | None     = Field(default=None, description="Output filename; derived from URL if omitted")
    workdir:  str            = Field(default=".", example="/data/bryce")


class DownloadStackRequest(BaseModel):
    urls:    list[str] = Field(..., description="List of ASF download URLs for the stack")
    workdir: str       = Field(default=".", example="/data/bryce")


class AddJobRequest(BaseModel):
    workdir: str
    relativeOrbit: int
    frame: int
    start: str
    end: str
    wkt: str | None = None
    flightDirection: str | None = None
    platform: str | None = None
    downloaderType: str = "S1_SLC"


class DownloadByNameRequest(BaseModel):
    scene_names: list[str] = Field(default=[], description="Explicit list of scene/granule names (with or without .zip/.SAFE extension)")
    scene_file: str | None = Field(default=None, description="Path to a CSV, XLSX, or TXT file containing scene names (used if scene_names is empty)")
    workdir: str = Field(default=".", description="Parent directory; subfolders p{path}_f{frame}/ are created automatically")
    downloaderType: str = Field(default="S1_SLC", description="Downloader to use")


class JobResponse(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    status: str        # "running" | "done" | "error"
    progress: int      # 0-100
    message: str
    data: Any = None


# ---------------------------------------------------------------------------
# Progress helper
# ---------------------------------------------------------------------------

def _make_progress(job_id: str):
    def callback(message: str, percent: int):
        _jobs[job_id]["progress"] = percent
        _jobs[job_id]["message"]  = message
    return callback


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Confirm the server is running."""
    return {"status": "ok"}


@app.get("/api/workdir")
async def get_workdir():
    """Return the current work directory (from settings or launch dir)."""
    return {"workdir": _settings["workdir"]}


@app.get("/api/pick-folder")
async def pick_folder():
    """Open a native folder-picker dialog and return the selected path."""
    import subprocess, sys
    from pathlib import Path as _Path

    # ── WSL: delegate to PowerShell's WinForms FolderBrowserDialog ──────────
    is_wsl = _Path("/proc/version").exists() and \
             "microsoft" in _Path("/proc/version").read_text().lower()
    if is_wsl:
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = 'Select work directory'; "
            "$null = $f.ShowDialog(); "
            "Write-Output $f.SelectedPath"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True
        )
        win_path = res.stdout.strip()
        if not win_path:
            return {"path": None}
        conv = subprocess.run(["wslpath", "-u", win_path], capture_output=True, text=True)
        return {"path": conv.stdout.strip() or None}

    # ── Windows native ───────────────────────────────────────────────────────
    if sys.platform == "win32":
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = 'Select work directory'; "
            "$null = $f.ShowDialog(); "
            "Write-Output $f.SelectedPath"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True
        )
        return {"path": res.stdout.strip() or None}

    # ── macOS ────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        res = subprocess.run(
            ["osascript", "-e", "POSIX path of (choose folder with prompt \"Select work directory\")"],
            capture_output=True, text=True
        )
        return {"path": res.stdout.strip().rstrip("/") or None}

    # ── Linux (native): zenity → kdialog → tkinter ──────────────────────────
    for cmd in [
        ["zenity", "--file-selection", "--directory", "--title=Select work directory"],
        ["kdialog", "--getexistingdirectory", "/"],
    ]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode == 0 and res.stdout.strip():
                return {"path": res.stdout.strip()}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # tkinter fallback (Linux without zenity/kdialog, or any platform)
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select work directory")
        root.destroy()
        return {"path": path or None}
    except Exception:
        pass

    return {"path": None}


@app.get("/api/job-folders")
async def get_job_folders():
    """
    List subfolders of workdir as jobs.
    Each folder is tagged based on the files it contains:
      - hyp3_jobs.json or hyp3_retry_jobs_*.json → 'HyP3'
      - mintpy.cfg                               → 'MintPy'
      - pairs_p*_f*.json                         → 'SBAS'
    """
    workdir = Path(_settings["workdir"])
    if not workdir.exists():
        return {"jobs": []}
    jobs = []
    for subfolder in sorted(workdir.iterdir()):
        if not subfolder.is_dir():
            continue
        tags: list[str] = []
        if (subfolder / "hyp3_jobs.json").exists() or list(subfolder.glob("hyp3_retry_jobs_*.json")):
            tags.append("HyP3")
        if (subfolder / "mintpy.cfg").exists():
            tags.append("MintPy")
        if list(subfolder.glob("pairs_p*_f*.json")):
            tags.append("SBAS")
        workflow: dict = {}
        wf_file = subfolder / "insarhub_workflow.json"
        if wf_file.exists():
            try:
                workflow = json.loads(wf_file.read_text())
            except Exception:
                pass
        jobs.append({"name": subfolder.name, "path": str(subfolder), "tags": tags, "workflow": workflow})
    return {"jobs": jobs}


@app.delete("/api/job-folder")
async def delete_job_folder(path: str):
    """Delete an entire job folder and all its contents."""
    folder = Path(path)
    workdir = Path(_settings["workdir"])
    # Safety: must be a direct child of workdir
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    try:
        folder.relative_to(workdir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Folder is not inside workdir")
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    import shutil as _shutil
    _shutil.rmtree(folder)
    return {"ok": True}


@app.get("/api/settings")
async def get_settings():
    """Return current settings including downloader/processor/analyzer config."""
    cur_analyzer = _settings["analyzer"]
    analyzer_configs: dict = _settings.get("analyzer_configs", {})
    return {
        "workdir":              _settings["workdir"],
        "max_download_workers": _settings["max_download_workers"],
        "downloader":           _settings["downloader"],
        "downloader_config":    _settings["downloader_config"],
        "processor":            _settings["processor"],
        "processor_config":     _settings["processor_config"],
        "analyzer":             cur_analyzer,
        "analyzer_configs":     analyzer_configs,
    }


class SettingsUpdate(BaseModel):
    workdir:              str | None             = None
    max_download_workers: int | None             = None
    downloader:           str | None             = None
    downloader_config:    dict[str, Any] | None  = None
    processor:            str | None             = None
    processor_config:     dict[str, Any] | None  = None
    analyzer:             str | None             = None
    analyzer_config:      dict[str, Any] | None  = None  # config for the `analyzer` type only


@app.patch("/api/settings")
async def update_settings(req: SettingsUpdate):
    """Update settings."""
    if req.workdir is not None:
        p = Path(req.workdir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        _settings["workdir"] = str(p)
    if req.max_download_workers is not None:
        _settings["max_download_workers"] = max(1, min(99, req.max_download_workers))
    if req.downloader is not None:
        _settings["downloader"] = req.downloader
        _settings["downloader_config"] = _safe_config_values(req.downloader, _DOWNLOADERS_META)
    if req.downloader_config is not None:
        # Never persist TopBar fields (AOI, dates) — they live in the TopBar state
        cfg = {k: v for k, v in req.downloader_config.items() if k not in _TOPBAR_FIELDS}
        _settings["downloader_config"].update(cfg)
    if req.processor is not None:
        _settings["processor"] = req.processor
        _settings["processor_config"] = _default_config_values(req.processor, _PROCESSORS_META)
    if req.processor_config is not None:
        _settings["processor_config"].update(req.processor_config)
    if req.analyzer is not None:
        _settings["analyzer"] = req.analyzer
        # Ensure this type has an entry; do NOT reset other types
        if req.analyzer not in _settings["analyzer_configs"]:
            _settings["analyzer_configs"][req.analyzer] = _default_config_values(req.analyzer, _ANALYZERS_META)
    if req.analyzer_config is not None:
        # Store config under the specific analyzer type it belongs to
        target = req.analyzer if req.analyzer is not None else _settings["analyzer"]
        if target not in _settings["analyzer_configs"]:
            _settings["analyzer_configs"][target] = _default_config_values(target, _ANALYZERS_META)
        _settings["analyzer_configs"][target].update(req.analyzer_config)
    return await get_settings()


@app.get("/api/workflows")
async def get_workflows():
    """Return component metadata for downloaders, processors, and analyzers."""
    return {
        "downloaders": _DOWNLOADERS_META,
        "processors":  _PROCESSORS_META,
        "analyzers":   _ANALYZERS_META,
    }


@app.on_event("startup")
async def _startup_auth_check():
    """Silently populate auth cache in the background when the server starts."""
    async def _run():
        global _auth_cache
        _auth_cache = await asyncio.to_thread(_build_auth_status)
    asyncio.create_task(_run())


@app.get("/api/auth-status")
async def get_auth_status(refresh: bool = False):
    """Return cached auth status (populated at startup).  Pass ?refresh=true to recheck."""
    global _auth_cache
    if refresh or _auth_cache is None:
        _auth_cache = await asyncio.to_thread(_build_auth_status)
    return _auth_cache


@app.get("/api/auth-status/stream")
async def stream_auth_status():
    """SSE endpoint — streams auth results as each check completes."""
    async def generate():
        # ── Instant: file-system checks ──────────────────────────────────────
        earthdata  = _netrc_has("urs.earthdata.nasa.gov")
        cdse       = _netrc_has("dataspace.copernicus.eu") or _CSDAPI.is_file()
        pool_pairs = _read_credit_pool_pairs()
        netrc_event = json.dumps({
            "type": "netrc",
            "earthdata_connected": earthdata,
            "cdse_connected": cdse,
            "credit_pool_exists": bool(pool_pairs),
        })
        yield f"data: {netrc_event}\n\n"

        # ── Parallel: all HyP3 checks at once ────────────────────────────────
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        async def _check(kind: str, u: str | None = None, p: str | None = None) -> None:
            result = await asyncio.to_thread(_check_hyp3_account, u, p)
            await queue.put((kind, result))

        n_tasks = 1 + len(pool_pairs)
        asyncio.create_task(_check("main"))
        for u, p in pool_pairs:
            asyncio.create_task(_check("pool", u, p))

        for _ in range(n_tasks):
            kind, data = await queue.get()
            yield f"data: {json.dumps({'type': kind, 'data': data})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/parse-granule-file")
async def parse_granule_file(file: UploadFile = File(...)):
    """Upload a CSV, XLSX, or TXT file and return the list of parsed granule names."""
    from insarhub.utils.tool import parse_scene_names_from_file
    suffix = Path(file.filename or '').suffix.lower() or '.tmp'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        names = parse_scene_names_from_file(tmp_path)
        return {"names": names, "count": len(names)}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/search", response_model=JobResponse)
async def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    """
    Start an ASF scene search in the background.
    Poll GET /api/jobs/{job_id} until status == 'done'.
    Response data contains: session_id, geojson (for map), summary string.
    """
    job_id    = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting search...", "data": None}
    background_tasks.add_task(_run_search, job_id, session_id, req)
    return {"job_id": job_id}


async def _run_search(job_id: str, session_id: str, req: SearchRequest):
    def run():
        try:
            if req.granule_names:
                # Granule-name search — bypass spatial/temporal parameters entirely
                config = S1_SLC_Config(workdir=req.workdir, granule_names=req.granule_names)
                downloader = Downloader.create("S1_SLC", config)
            else:
                # Build relative-orbit list from path range
                rel_orbit = None
                if req.pathStart is not None:
                    p_end = req.pathEnd if req.pathEnd is not None else req.pathStart
                    rel_orbit = list(range(req.pathStart, p_end + 1))

                # Build asfFrame list from frame range
                asf_frame = None
                if req.frameStart is not None:
                    f_end = req.frameEnd if req.frameEnd is not None else req.frameStart
                    asf_frame = list(range(req.frameStart, f_end + 1))

                # Simplify WKT geometry to avoid URL-too-long errors (OSError ENAMETOOLONG).
                intersects_with = req.wkt if req.wkt else (req.west, req.south, req.east, req.north)
                if isinstance(intersects_with, str):
                    try:
                        geom = shapely_wkt.loads(intersects_with)
                        for tol in (0.001, 0.005, 0.01, 0.05, 0.1):
                            simplified = geom.simplify(tol, preserve_topology=True)
                            if len(simplified.wkt) <= 2000:
                                break
                        intersects_with = simplified.wkt
                    except Exception:
                        pass

                config = S1_SLC_Config(
                    intersectsWith=intersects_with,
                    start=req.start,
                    end=req.end,
                    workdir=req.workdir,
                    maxResults=req.maxResults,
                    beamMode=req.beamMode or None,
                    polarization=req.polarization or None,
                    flightDirection=req.flightDirection or None,
                    relativeOrbit=rel_orbit or None,
                    asfFrame=asf_frame or None,
                )
                downloader = Downloader.create("S1_SLC", config)
            cmd = SearchCommand(downloader, progress_callback=_make_progress(job_id))
            result = cmd.run()

            if result.success:
                _sessions[session_id] = downloader
                _jobs[job_id] = {
                    "status":   "done",
                    "progress": 100,
                    "message":  result.message,
                    "data": {
                        "session_id": session_id,
                        "geojson":    _to_geojson(result.data),
                        "summary":    result.message,
                    },
                }
            else:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": result.message, "data": None}

        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


@app.post("/api/download", response_model=JobResponse)
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Download scenes for a previous search session.
    Poll GET /api/jobs/{job_id} for progress.
    """
    if req.session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found — run /api/search first")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting download...", "data": None}
    background_tasks.add_task(_run_download, job_id, req)
    return {"job_id": job_id}


async def _run_download(job_id: str, req: DownloadRequest):
    def run():
        try:
            downloader = _sessions[req.session_id]
            cmd = DownloadScenesCommand(downloader, progress_callback=_make_progress(job_id))
            result = cmd.run()
            _jobs[job_id] = {
                "status":   "done" if result.success else "error",
                "progress": 100,
                "message":  result.message,
                "data":     str(result.data) if result.data else None,
            }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    """Poll this for background job status and progress."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Signal a cancellable job (e.g. download) to stop."""
    event = _stop_events.get(job_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    event.set()
    _jobs[job_id]["message"] = "Stopping…"
    return {"ok": True}


@app.post("/api/download-scene", response_model=JobResponse)
async def download_single_scene(req: DownloadSceneRequest, background_tasks: BackgroundTasks):
    """
    Download a single SAR scene by its direct ASF URL.
    Authentication is handled via ~/.netrc (Earthdata Login).
    Poll GET /api/jobs/{job_id} for progress.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting download...", "data": None}
    background_tasks.add_task(_run_download_scene, job_id, req)
    return {"job_id": job_id}


async def _run_download_scene(job_id: str, req: DownloadSceneRequest):
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev

    def run():
        file_path = None
        try:
            import asf_search as asf
            from asf_search.download.download import _try_get_response

            workdir = Path(req.workdir)
            workdir.mkdir(parents=True, exist_ok=True)

            filename = req.filename or req.url.rstrip("/").split("/")[-1].split("?")[0]
            file_path = workdir / filename
            _jobs[job_id]["message"] = f"Downloading {filename}…"

            session = asf.ASFSession()
            response = _try_get_response(session=session, url=req.url)
            total_bytes = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if stop_ev.is_set():
                        response.close()
                        _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes:
                            pct = int(downloaded / total_bytes * 100)
                            _jobs[job_id]["progress"] = pct
                            _jobs[job_id]["message"] = f"Downloading {filename}… {pct}%"

            _jobs[job_id] = {
                "status":   "done",
                "progress": 100,
                "message":  f"Saved {filename}",
                "data":     str(file_path),
            }
        except InterruptedError:
            _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
        except Exception as e:
            # Clean up partial file on error
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


@app.post("/api/download-stack", response_model=JobResponse)
async def download_stack(req: AddJobRequest, background_tasks: BackgroundTasks):
    """Search and download all scenes for a stack into workdir/p{path}_f{frame}/."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting…", "data": None}
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev
    background_tasks.add_task(_run_download_stack, job_id, req, stop_ev)
    return {"job_id": job_id}


async def _run_download_stack(job_id: str, req: AddJobRequest, stop_ev: _threading.Event):
    def run():
        try:
            workdir = Path(req.workdir).expanduser().resolve()
            workdir.mkdir(parents=True, exist_ok=True)

            # workdir is the parent — download() creates p{path}_f{frame}/ subfolders itself
            cfg = S1_SLC_Config(workdir=workdir)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in _settings.get("downloader_config", {}).items():
                if key in valid_fields and key != "workdir" and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass
            for key, val in {
                "start": req.start, "end": req.end,
                "relativeOrbit": req.relativeOrbit, "frame": req.frame,
                "intersectsWith": req.wkt,
                "flightDirection": req.flightDirection, "platform": req.platform,
            }.items():
                if key in valid_fields and val is not None:
                    setattr(cfg, key, val)

            downloader = Downloader.create("S1_SLC", cfg)
            _jobs[job_id]["message"] = "Searching scenes…"
            search_result = SearchCommand(downloader).run()
            if not search_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": search_result.message, "data": None}
                return

            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
                return

            total = sum(len(v) for v in downloader.results.values())
            _jobs[job_id]["message"] = f"Downloading 0/{total}"
            _jobs[job_id]["progress"] = 0

            def _on_progress(msg: str, pct: int):
                # msg is "[X/N] ✔ filename" — extract just the X/N count
                count = msg.split(']')[0].lstrip('[') if ']' in msg else ''
                _jobs[job_id]["message"] = f"Downloading {count}" if count else msg
                _jobs[job_id]["progress"] = pct

            dl_result = DownloadScenesCommand(
                downloader,
                stop_event=stop_ev,
                on_progress=_on_progress,
            ).run()
            save_dir = workdir / f"p{req.relativeOrbit}_f{req.frame}"
            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
            else:
                _jobs[job_id] = {
                    "status":   "done" if dl_result.success else "error",
                    "progress": 100,
                    "message":  dl_result.message,
                    "data":     str(save_dir),
                }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


@app.post("/api/add-job")
async def add_job(req: AddJobRequest):
    """Create a job subfolder with downloader_config.json and workflow marker."""
    from insarhub.utils.tool import write_workflow_marker
    workdir = Path(req.workdir).expanduser().resolve()
    subdir = workdir / f"p{req.relativeOrbit}_f{req.frame}"
    subdir.mkdir(parents=True, exist_ok=True)

    dl_cls  = Downloader._registry.get(req.downloaderType)
    cfg_cls = getattr(dl_cls, "default_config", S1_SLC_Config) if dl_cls else S1_SLC_Config
    cfg_instance = cfg_cls(workdir=subdir)
    valid_fields = {f.name for f in dataclasses.fields(cfg_instance)}
    # Apply saved downloader settings from global settings first
    for key, val in _settings.get("downloader_config", {}).items():
        if key in valid_fields and key != "workdir" and val is not None:
            try:
                setattr(cfg_instance, key, val)
            except Exception:
                pass
    # Then apply request-specific fields (override saved settings)
    for key, val in {
        "start": req.start, "end": req.end,
        "relativeOrbit": req.relativeOrbit, "frame": req.frame,
        "intersectsWith": req.wkt,
        "flightDirection": req.flightDirection, "platform": req.platform,
    }.items():
        if key in valid_fields and val is not None:
            setattr(cfg_instance, key, val)
    cfg = {k: v for k, v in dataclasses.asdict(cfg_instance).items() if k != "workdir"}

    (subdir / "downloader_config.json").write_text(json.dumps(cfg, indent=2, default=str))
    write_workflow_marker(subdir, downloader=req.downloaderType)
    return {"path": str(subdir), "name": subdir.name}


@app.post("/api/download-orbit-stack", response_model=JobResponse)
async def download_orbit_stack(req: AddJobRequest, background_tasks: BackgroundTasks):
    """Search and download orbit files for a single stack (used from Stack Info panel)."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting orbit download…", "data": None}
    background_tasks.add_task(_run_download_orbit_stack, job_id, req)
    return {"job_id": job_id}


async def _run_download_orbit_stack(job_id: str, req: AddJobRequest):
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev

    def run():
        try:
            workdir = Path(req.workdir).expanduser().resolve()
            save_dir = workdir / f"p{req.relativeOrbit}_f{req.frame}"
            save_dir.mkdir(parents=True, exist_ok=True)

            cfg = S1_SLC_Config(workdir=save_dir)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in _settings.get("downloader_config", {}).items():
                if key in valid_fields and key != "workdir" and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass
            for key, val in {
                "start": req.start, "end": req.end,
                "relativeOrbit": req.relativeOrbit, "frame": req.frame,
                "intersectsWith": req.wkt,
                "flightDirection": req.flightDirection, "platform": req.platform,
            }.items():
                if key in valid_fields and val is not None:
                    setattr(cfg, key, val)

            downloader = Downloader.create("S1_SLC", cfg)
            _jobs[job_id]["message"] = "Searching scenes…"
            search_result = SearchCommand(downloader, progress_callback=_make_progress(job_id)).run()
            if not search_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": search_result.message, "data": None}
                return

            _jobs[job_id]["message"] = "Downloading orbit files…"
            downloader.download_orbit(save_dir=str(save_dir), stop_event=stop_ev)
            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
            else:
                _jobs[job_id] = {"status": "done", "progress": 100, "message": "Orbit files downloaded.", "data": None}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


class FolderDownloadRequest(BaseModel):
    folder_path: str


@app.get("/api/folder-details")
async def get_folder_details(path: str):
    """Return downloader config, pairs file presence, and network image path for a job folder."""
    folder = Path(path)
    result: dict[str, Any] = {
        "downloader_config": None,
        "has_pairs": False,
        "network_image": None,
    }
    cfg_file = folder / "downloader_config.json"
    if cfg_file.exists():
        try:
            result["downloader_config"] = json.loads(cfg_file.read_text())
        except Exception:
            pass
    pairs_files = list(folder.glob("pairs_p*_f*.json"))
    result["has_pairs"] = bool(pairs_files)
    network_files = sorted(folder.glob("network_p*_f*.png"))
    result["network_image"] = str(network_files[0]) if network_files else None
    return result


@app.get("/api/folder-pairs")
async def get_folder_pairs(path: str):
    """Return pairs list from the first pairs_p*_f*.json found in the folder."""
    folder = Path(path)
    pairs_files = sorted(folder.glob("pairs_p*_f*.json"))
    if not pairs_files:
        raise HTTPException(status_code=404, detail="No pairs file found")
    try:
        pairs = json.loads(pairs_files[0].read_text())
        return {"pairs": pairs, "count": len(pairs), "file": pairs_files[0].name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/folder-image")
async def get_folder_image(path: str):
    """Serve a PNG image from the filesystem by absolute path."""
    img_path = Path(path)
    workdir = Path(_settings["workdir"])
    try:
        img_path.resolve().relative_to(workdir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside workdir")
    if not img_path.exists() or img_path.suffix.lower() != ".png":
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=img_path.read_bytes(), media_type="image/png")


@app.post("/api/folder-download", response_model=JobResponse)
async def folder_download(req: FolderDownloadRequest, background_tasks: BackgroundTasks):
    """Re-search and download using the downloader_config.json saved in the job folder."""
    folder = Path(req.folder_path)
    cfg_file = folder / "downloader_config.json"
    if not cfg_file.exists():
        raise HTTPException(status_code=404, detail="downloader_config.json not found in folder")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting search…", "data": None}
    background_tasks.add_task(_run_folder_download, job_id, req.folder_path)
    return {"job_id": job_id}


async def _run_folder_download(job_id: str, folder_path: str):
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev

    def run():
        try:
            folder = Path(folder_path)
            raw: dict[str, Any] = json.loads((folder / "downloader_config.json").read_text())

            cfg = S1_SLC_Config(workdir=folder)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in raw.items():
                if key in valid_fields and key != "workdir" and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass

            downloader = Downloader.create("S1_SLC", cfg)
            search_result = SearchCommand(downloader, progress_callback=_make_progress(job_id)).run()
            if not search_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": search_result.message, "data": None}
                return

            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
                return

            total = sum(len(v) for v in downloader.results.values())
            _jobs[job_id]["message"] = f"Downloading 0/{total}"

            def _on_progress(msg: str, pct: int):
                count = msg.split(']')[0].lstrip('[') if ']' in msg else ''
                _jobs[job_id]["message"] = f"Downloading {count}" if count else msg
                _jobs[job_id]["progress"] = pct

            # Pass folder.parent so download() creates p{path}_f{frame}/ inside it,
            # landing files in the job folder itself rather than a nested subfolder.
            dl_result = DownloadScenesCommand(
                downloader,
                stop_event=stop_ev,
                on_progress=_on_progress,
                save_path=str(folder.parent),
            ).run()

            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
                return

            _jobs[job_id] = {
                "status":   "done" if dl_result.success else "error",
                "progress": 100,
                "message":  dl_result.message,
                "data":     None,
            }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


@app.post("/api/folder-download-orbit", response_model=JobResponse)
async def folder_download_orbit(req: FolderDownloadRequest, background_tasks: BackgroundTasks):
    """Download orbit files for scenes in a job folder."""
    folder = Path(req.folder_path)
    cfg_file = folder / "downloader_config.json"
    if not cfg_file.exists():
        raise HTTPException(status_code=404, detail="downloader_config.json not found in folder")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting orbit download…", "data": None}
    background_tasks.add_task(_run_folder_download_orbit, job_id, req.folder_path)
    return {"job_id": job_id}


async def _run_folder_download_orbit(job_id: str, folder_path: str):
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev

    def run():
        try:
            folder = Path(folder_path)
            raw: dict[str, Any] = json.loads((folder / "downloader_config.json").read_text())

            cfg = S1_SLC_Config(workdir=folder)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in raw.items():
                if key in valid_fields and key != "workdir" and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass

            downloader = Downloader.create("S1_SLC", cfg)
            _jobs[job_id]["message"] = "Searching scenes…"
            search_result = SearchCommand(downloader, progress_callback=_make_progress(job_id)).run()
            if not search_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": search_result.message, "data": None}
                return

            _jobs[job_id]["message"] = "Downloading orbit files…"
            downloader.download_orbit(save_dir=str(folder), stop_event=stop_ev)
            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
            else:
                _jobs[job_id] = {"status": "done", "progress": 100, "message": "Orbit files downloaded.", "data": None}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


class SelectPairsRequest(BaseModel):
    folder_path:   str
    dt_targets:    list[int] = Field(default=[6, 12, 24, 36, 48, 72, 96])
    dt_tol:        int   = 3
    dt_max:        int   = 120
    pb_max:        float = 150.0
    min_degree:    int   = 3
    max_degree:    int   = 999
    force_connect: bool  = True
    max_workers:   int   = 4


@app.post("/api/folder-select-pairs", response_model=JobResponse)
async def folder_select_pairs(req: SelectPairsRequest, background_tasks: BackgroundTasks):
    """Re-search using downloader_config.json and run select_pairs with given parameters."""
    folder = Path(req.folder_path)
    if not (folder / "downloader_config.json").exists():
        raise HTTPException(status_code=404, detail="downloader_config.json not found in folder")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting search…", "data": None}
    background_tasks.add_task(_run_folder_select_pairs, job_id, req)
    return {"job_id": job_id}


async def _run_folder_select_pairs(job_id: str, req: SelectPairsRequest):
    def run():
        try:
            folder  = Path(req.folder_path)
            raw: dict[str, Any] = json.loads((folder / "downloader_config.json").read_text())

            # Read downloader type from workflow marker
            dl_type = "S1_SLC"
            wf_file = folder / "insarhub_workflow.json"
            if wf_file.exists():
                try:
                    dl_type = json.loads(wf_file.read_text()).get("downloader", dl_type)
                except Exception:
                    pass

            dl_cls  = Downloader._registry.get(dl_type)
            cfg_cls = getattr(dl_cls, "default_config", S1_SLC_Config) if dl_cls else S1_SLC_Config

            # workdir = parent so select_pairs writes into the correct p{path}_f{frame} subfolder
            cfg = cfg_cls(workdir=folder.parent)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in raw.items():
                if key in valid_fields and key != "workdir" and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass

            downloader = Downloader.create(dl_type, cfg)
            _jobs[job_id]["message"] = "Searching scenes…"
            search_result = SearchCommand(downloader, progress_callback=_make_progress(job_id)).run()
            if not search_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": search_result.message, "data": None}
                return

            _jobs[job_id]["message"] = "Selecting pairs…"
            downloader.select_pairs(
                dt_targets=tuple(req.dt_targets),
                dt_tol=req.dt_tol,
                dt_max=req.dt_max,
                pb_max=req.pb_max,
                min_degree=req.min_degree,
                max_degree=req.max_degree,
                force_connect=req.force_connect,
                max_workers=req.max_workers,
                plot=True,
            )
            _jobs[job_id] = {"status": "done", "progress": 100, "message": "Pairs selected", "data": None}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


class ProcessRequest(BaseModel):
    folder_path:      str
    processor_type:   str = "Hyp3_InSAR"
    processor_config: dict[str, Any] = {}
    dry_run:          bool = False


@app.post("/api/folder-process", response_model=JobResponse)
async def folder_process(req: ProcessRequest, background_tasks: BackgroundTasks):
    """Read pairs from folder, submit to processor, save job IDs."""
    folder = Path(req.folder_path)
    pairs_files = sorted(folder.glob("pairs_p*_f*.json"))
    if not pairs_files:
        raise HTTPException(status_code=404, detail="No pairs file found in folder")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting…", "data": None}
    background_tasks.add_task(_run_folder_process, job_id, req)
    return {"job_id": job_id}


async def _run_folder_process(job_id: str, req: ProcessRequest):
    def run():
        try:
            from insarhub.utils.tool import write_workflow_marker

            folder = Path(req.folder_path)
            pairs_files = sorted(folder.glob("pairs_p*_f*.json"))
            if not pairs_files:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": "No pairs file found", "data": None}
                return

            raw = json.loads(pairs_files[0].read_text())
            pairs: list[tuple[str, str]] = [tuple(p) for p in raw]

            proc_cls  = Processor._registry.get(req.processor_type)
            if proc_cls is None:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": f"Unknown processor: {req.processor_type}", "data": None}
                return
            cfg_cls = getattr(proc_cls, "default_config", None)
            if cfg_cls is None or not dataclasses.is_dataclass(cfg_cls):
                _jobs[job_id] = {"status": "error", "progress": 0, "message": "Processor has no config", "data": None}
                return

            cfg = cfg_cls(workdir=folder)
            valid_fields = {f.name for f in dataclasses.fields(cfg)}
            for key, val in req.processor_config.items():
                if key in valid_fields and key not in ("workdir", "pairs") and val is not None:
                    try:
                        setattr(cfg, key, val)
                    except Exception:
                        pass
            cfg.pairs = pairs

            if req.dry_run:
                n = len(pairs)
                msgs = []
                try:
                    proc_cfg_path = folder / "processor_config.json"
                    proc_cfg_path.write_text(json.dumps({
                        "name": req.processor_type,
                        "processor_config": req.processor_config,
                    }, indent=2))
                    msgs.append("wrote  processor_config.json")
                except Exception as e:
                    msgs.append(f"could not write processor_config.json: {e}")
                try:
                    write_workflow_marker(folder, processor=req.processor_type)
                    msgs.append(f"marked insarhub_workflow.json  processor={req.processor_type}")
                except Exception as e:
                    msgs.append(f"could not update insarhub_workflow.json: {e}")
                _jobs[job_id] = {
                    "status": "done", "progress": 100,
                    "message": (
                        f"[Dry run] Would submit {n} pair{'s' if n != 1 else ''} "
                        f"via {req.processor_type} from {folder.name}\n"
                        + "\n".join(msgs)
                    ),
                    "data": None,
                }
                return

            _jobs[job_id]["message"] = "Submitting jobs…"
            processor = Processor.create(req.processor_type, cfg)
            submit_result = SubmitCommand(processor, progress_callback=_make_progress(job_id)).run()
            if not submit_result.success:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": submit_result.message, "data": None}
                return

            _jobs[job_id]["message"] = "Saving job IDs…"
            SaveJobsCommand(processor, progress_callback=_make_progress(job_id)).run()

            write_workflow_marker(folder, processor=req.processor_type)
            proc_cfg_path = folder / "processor_config.json"
            proc_cfg_path.write_text(json.dumps({
                "name": req.processor_type,
                "processor_config": req.processor_config,
            }, indent=2))
            _jobs[job_id] = {"status": "done", "progress": 100, "message": submit_result.message, "data": None}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


@app.get("/api/folder-hyp3-jobs")
async def get_folder_hyp3_jobs(path: str):
    """List hyp3*.json job files in a folder with stored job counts."""
    folder = Path(path)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    files = []
    for f in sorted(folder.glob("hyp3*.json")):
        try:
            data = json.loads(f.read_text())
            job_ids = data.get("job_ids", {})
            total = sum(len(v) for v in job_ids.values())
            users = list(job_ids.keys())
        except Exception:
            total = 0
            users = []
        files.append({"name": f.name, "total": total, "users": users})
    proc_type = None
    proc_cfg_path = folder / "processor_config.json"
    if proc_cfg_path.exists():
        try:
            pc = json.loads(proc_cfg_path.read_text())
            proc_type = pc.get("name") or pc.get("processor_type")
        except Exception:
            pass
    return {"files": files, "processor_type": proc_type}


class InitAnalyzerRequest(BaseModel):
    folder_path:   str
    analyzer_type: str


@app.post("/api/folder-init-analyzer")
async def folder_init_analyzer(req: InitAnalyzerRequest):
    """Mark a folder with an analyzer role in insarhub_workflow.json."""
    from insarhub.utils.tool import write_workflow_marker
    folder = Path(req.folder_path)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    if req.analyzer_type not in Analyzer._registry:
        raise HTTPException(status_code=400, detail=f"Unknown analyzer: {req.analyzer_type}")
    write_workflow_marker(folder, analyzer=req.analyzer_type)
    return {"ok": True, "analyzer": req.analyzer_type}


_MINTPY_STEPS = [
    'load_data', 'modify_network', 'reference_point', 'invert_network',
    'correct_LOD', 'correct_SET', 'correct_ionosphere', 'correct_troposphere',
    'deramp', 'correct_topography', 'residual_RMS', 'reference_date',
    'velocity', 'geocode', 'google_earth', 'hdfeos5', 'plot',
]


@app.get("/api/analyzer-steps")
async def get_analyzer_steps(analyzer_type: str):
    """Return the list of steps for a MintPy-based analyzer."""
    cls = Analyzer._registry.get(analyzer_type)
    if cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown analyzer: {analyzer_type}")
    # Check if it's a MintPy-based analyzer by inspecting the run method signature
    import inspect
    src = inspect.getsource(cls.run) if hasattr(cls, 'run') else ''
    if 'TimeSeriesAnalysis' in src or 'mintpy' in src.lower():
        steps = (['prep_data'] if hasattr(cls, 'prep_data') else []) + _MINTPY_STEPS
    else:
        steps = []
    return {"steps": steps}


class RunAnalyzerRequest(BaseModel):
    folder_path:   str
    analyzer_type: str
    steps:         list[str]


@app.post("/api/folder-run-analyzer", response_model=JobResponse)
async def folder_run_analyzer(req: RunAnalyzerRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting analyzer…", "data": None}
    background_tasks.add_task(_run_analyzer, job_id, req)
    return {"job_id": job_id}


async def _run_analyzer(job_id: str, req: RunAnalyzerRequest):
    import threading as _threading
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev

    def run():
        log: list[str] = []

        def update(msg: str, pct: int):
            log.append(msg)
            _jobs[job_id]["progress"] = pct
            _jobs[job_id]["message"]  = "\n".join(log)

        try:
            folder = Path(req.folder_path)
            cls = Analyzer._registry.get(req.analyzer_type)
            if cls is None:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": f"Unknown analyzer: {req.analyzer_type}", "data": None}
                return
            config_cls = getattr(cls, "default_config", None)
            if config_cls is None or not dataclasses.is_dataclass(config_cls):
                _jobs[job_id] = {"status": "error", "progress": 0, "message": "Analyzer has no config dataclass", "data": None}
                return

            # Each analyzer type has its own config stored independently
            saved_overrides = _settings.get("analyzer_configs", {}).get(req.analyzer_type, {})
            valid_keys = {f.name for f in dataclasses.fields(config_cls)}
            init_kwargs: dict = {k: v for k, v in saved_overrides.items() if k in valid_keys}
            init_kwargs["workdir"] = folder
            cfg = config_cls(**init_kwargs)
            analyzer = cls(cfg)

            total = len(req.steps)
            completed = 0
            for i, step in enumerate(req.steps):
                if stop_ev.is_set():
                    update(f"[stopped] Cancelled before {step}", int(i / total * 100))
                    break

                update(f"[{i+1}/{total}] {step} — running…", int(i / total * 100))
                try:
                    if step == 'prep_data':
                        analyzer.prep_data()
                    else:
                        analyzer.run(steps=[step])
                    update(f"[{i+1}/{total}] {step} — done", int((i+1) / total * 100))
                    completed += 1
                except Exception as e:
                    update(f"[{i+1}/{total}] {step} — ERROR: {e}", int(i / total * 100))
                    _jobs[job_id]["status"] = "error"
                    return

            _stop_events.pop(job_id, None)
            if stop_ev.is_set():
                _jobs[job_id]["status"] = "done"
            else:
                update(f"─── Finished {completed}/{total} step(s) ───", 100)
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["progress"] = 100

        except Exception as e:
            _stop_events.pop(job_id, None)
            log.append(f"FATAL: {e}")
            _jobs[job_id] = {"status": "error", "progress": 0, "message": "\n".join(log), "data": None}

    await asyncio.to_thread(run)


def _rgba_to_png_bytes(rgba) -> bytes:
    """Encode an H×W×4 uint8 numpy array as PNG bytes. Uses PIL when available."""
    try:
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.fromarray(rgba, 'RGBA').save(buf, format='PNG', optimize=False, compress_level=1)
        return buf.getvalue()
    except ImportError:
        pass
    import struct, zlib
    h, w = rgba.shape[:2]
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    raw  = b''.join(b'\x00' + bytes(row) for row in rgba)
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', zlib.compress(raw, 6)) + _chunk(b'IEND', b'')


def _colormap_numpy(data, mask, vmin: float, vmax: float, type_name: str):
    """Apply colormap to a 2-D float32 array; return H×W×4 uint8 RGBA."""
    import numpy as np
    rng = vmax - vmin or 1.0
    t   = np.clip((data - vmin) / rng, 0.0, 1.0)
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if type_name == 'unw_phase':
        hd  = (t * 360.0) % 360.0
        hi  = (hd / 60).astype(np.int32) % 6
        f   = hd / 60.0 - np.floor(hd / 60.0)
        r = np.select([hi==0,hi==1,hi==2,hi==3,hi==4,hi==5],[1,1-f,0,0,f,1])
        g = np.select([hi==0,hi==1,hi==2,hi==3,hi==4,hi==5],[f,1,1,f,0,0])
        b = np.select([hi==0,hi==1,hi==2,hi==3,hi==4,hi==5],[0,0,f,1,1,1-f])
        rgba[:,:,0] = (r*255).astype(np.uint8)
        rgba[:,:,1] = (g*255).astype(np.uint8)
        rgba[:,:,2] = (b*255).astype(np.uint8)
    elif type_name == 'corr':
        v = (t*255).astype(np.uint8)
        rgba[:,:,0] = v; rgba[:,:,1] = v; rgba[:,:,2] = v
    elif type_name == 'velocity':
        # RdBu_r diverging: blue (neg) → white (zero) → red (pos)
        stops_t = np.array([0.0, 0.5, 1.0])
        rgba[:,:,0] = np.interp(t, stops_t, [33,  247, 178]).astype(np.uint8)
        rgba[:,:,1] = np.interp(t, stops_t, [102, 247, 24 ]).astype(np.uint8)
        rgba[:,:,2] = np.interp(t, stops_t, [172, 247, 43 ]).astype(np.uint8)
    else:
        stops_t = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        rgba[:,:,0] = np.interp(t, stops_t, [68,  59,  33,  94,  253]).astype(np.uint8)
        rgba[:,:,1] = np.interp(t, stops_t, [1,   82,  145, 201, 231]).astype(np.uint8)
        rgba[:,:,2] = np.interp(t, stops_t, [84,  139, 140, 98,  37 ]).astype(np.uint8)
    rgba[:,:,3] = np.where(mask, 0, 255).astype(np.uint8)
    return rgba


def _tif_file_type(stem: str) -> str:
    for token in ("unw_phase", "corr", "dem", "lv_theta", "lv_phi", "water_mask",
                  "inc_map", "los_disp", "wrapped_phase", "browse"):
        if token in stem:
            return token
    return stem.split("_")[-1]


def _tif_bounds_wgs84(zip_path: str, tif_name: str) -> list | None:
    """Return [west, south, east, north] in WGS84 using /vsizip/ (no full extraction)."""
    try:
        try:
            import rasterio
            from rasterio.warp import transform_bounds
            with rasterio.open(f"/vsizip/{zip_path}/{tif_name}") as src:
                return list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
        except ImportError:
            from osgeo import gdal, osr
            ds = gdal.Open(f"/vsizip/{zip_path}/{tif_name}")
            if ds is None:
                return None
            gt = ds.GetGeoTransform()
            cols, rows = ds.RasterXSize, ds.RasterYSize
            src_srs = osr.SpatialReference()
            src_srs.ImportFromWkt(ds.GetProjection())
            tgt_srs = osr.SpatialReference()
            tgt_srs.ImportFromEPSG(4326)
            tgt_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            ct = osr.CoordinateTransformation(src_srs, tgt_srs)
            corners = [(gt[0], gt[3]), (gt[0] + cols * gt[1], gt[3]),
                       (gt[0] + cols * gt[1], gt[3] + rows * gt[5]),
                       (gt[0], gt[3] + rows * gt[5])]
            lons, lats = [], []
            for x, y in corners:
                pt = ct.TransformPoint(x, y)
                lons.append(pt[0]); lats.append(pt[1])
            ds = None
            return [min(lons), min(lats), max(lons), max(lats)]
    except Exception:
        return None


@app.get("/api/folder-ifg-list")
async def folder_ifg_list(path: str):
    """List interferogram zip files in a folder with per-file types and WGS84 bounds.

    Searches the folder itself first, then falls back to out_dir stored in any
    hyp3*.json batch file (the download destination may differ from the config folder).
    """
    import zipfile as _zipfile
    folder = Path(path)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # Determine search roots: folder itself + out_dir from .insarhub_cache.json / hyp3*.json
    search_roots: list[Path] = [folder]
    expected_names: list[str] = []

    # Prefer the filecache (written by refresh action — has exact filenames + out_dir)
    cache_file = folder / ".insarhub_cache.json"
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
            expected_names = cache.get("filenames", [])
            out_dir = cache.get("out_dir")
            if out_dir:
                p = Path(out_dir)
                if p.exists() and p not in search_roots:
                    search_roots.append(p)
        except Exception:
            pass
    else:
        # Fall back to reading out_dir from hyp3*.json batch files
        for job_file in sorted(folder.glob("hyp3*.json")):
            if job_file.name == ".insarhub_cache.json":
                continue
            try:
                data = json.loads(job_file.read_text())
                out_dir = data.get("out_dir")
                if out_dir:
                    p = Path(out_dir)
                    if p.exists() and p not in search_roots:
                        search_roots.append(p)
            except Exception:
                pass

    seen: set[str] = set()
    pairs = []

    def _process_zip(zip_path: Path):
        k = str(zip_path)
        if k in seen:
            return
        seen.add(k)
        try:
            with _zipfile.ZipFile(zip_path) as zf:
                # TIFs may be at root level OR inside a single subdirectory (HyP3 convention)
                all_names = zf.namelist()
                tif_names = sorted([n for n in all_names if n.endswith(".tif") and not n.endswith("/")])
                if not tif_names:
                    return
                bounds = _tif_bounds_wgs84(k, tif_names[0])
                files = [{"filename": t, "type": _tif_file_type(Path(t).stem)}
                         for t in tif_names]
                pairs.append({"name": zip_path.stem, "zip": k,
                              "files": files, "bounds": bounds})
        except Exception:
            pass

    if expected_names:
        # Fast path: search for exact filenames from the cache
        for root in search_roots:
            for name in expected_names:
                candidate = root / name
                if candidate.exists():
                    _process_zip(candidate)
            # Also rglob in case zips landed in subdirs
            if not pairs:
                for name in expected_names:
                    for found in root.rglob(name):
                        _process_zip(found)
    else:
        # No cache: glob all zips in every search root
        for root in search_roots:
            for zip_path in sorted(root.glob("*.zip")):
                _process_zip(zip_path)
            # Rglob fallback if still nothing found
            if not pairs:
                for zip_path in sorted(root.rglob("*.zip")):
                    _process_zip(zip_path)

    return {"pairs": pairs}


@app.get("/api/serve-tif")
async def serve_tif(zip: str, file: str):
    """Serve a TIF file extracted from a zip archive."""
    import zipfile as _zipfile
    from fastapi.responses import Response as _Resp
    try:
        with _zipfile.ZipFile(zip) as zf:
            data = zf.read(file)
            return _Resp(content=data, media_type="image/tiff",
                         headers={"Cache-Control": "no-store",
                                  "Content-Disposition": f"inline; filename={Path(file).name}"})
    except KeyError:
        raise HTTPException(status_code=404, detail=f"'{file}' not in archive")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/render-tif")
async def render_tif_colored(zip: str, file: str, type_hint: str = ""):
    """Server-side render a TIF to colored PNG + downsampled float32 for hover.

    Returns JSON:
      png_b64      – base64 PNG (display, max 1024 px on longer side)
      pixel_b64    – base64 float32 array (hover, max 256 px)
      bounds       – [W, S, E, N] WGS84
      vmin / vmax  – data range
      nodata       – nodata value or null
      width/height – original raster size
      pixel_width/pixel_height – downsampled pixel array size
    """
    import numpy as np, base64, zipfile as _zf

    MAX_DISPLAY = 1024
    MAX_PIXEL   = 256

    try:
        with _zf.ZipFile(zip) as zf:
            tif_bytes = zf.read(file)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.io import MemoryFile

        with MemoryFile(tif_bytes) as memf:
            with memf.open() as src:
                orig_h, orig_w = src.height, src.width
                # Downsample on read for display
                scale_d = min(1.0, MAX_DISPLAY / max(orig_h, orig_w))
                dh = max(1, int(orig_h * scale_d))
                dw = max(1, int(orig_w * scale_d))
                disp_data = src.read(1, out_shape=(dh, dw)).astype(np.float32)
                nodata_val = src.nodata
                bounds_wgs84 = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rasterio error: {e}")

    # Build nodata mask
    mask = ~np.isfinite(disp_data)
    if nodata_val is not None:
        mask |= (disp_data == float(nodata_val))

    valid = disp_data[~mask]
    vmin = float(valid.min()) if valid.size else 0.0
    vmax = float(valid.max()) if valid.size else 1.0

    type_name = type_hint or _tif_file_type(Path(file).stem)
    rgba = _colormap_numpy(disp_data, mask, vmin, vmax, type_name)
    png_bytes = _rgba_to_png_bytes(rgba)
    png_b64   = base64.b64encode(png_bytes).decode()

    # Pixel hover data (smaller)
    scale_p = min(1.0, MAX_PIXEL / max(dh, dw))
    ph = max(1, int(dh * scale_p))
    pw = max(1, int(dw * scale_p))
    row_idx = (np.arange(ph) * dh / ph).astype(int)
    col_idx = (np.arange(pw) * dw / pw).astype(int)
    pix_data = disp_data[np.ix_(row_idx, col_idx)]
    pixel_b64 = base64.b64encode(pix_data.astype(np.float32).tobytes()).decode()

    return {
        "png_b64":      png_b64,
        "pixel_b64":    pixel_b64,
        "bounds":       bounds_wgs84,
        "vmin":         vmin,
        "vmax":         vmax,
        "nodata":       nodata_val,
        "type":         type_name,
        "width":        orig_w,
        "height":       orig_h,
        "pixel_width":  pw,
        "pixel_height": ph,
    }


# ── MintPy helpers ────────────────────────────────────────────────────────────

_TS_PRIORITY = [
    'timeseries_ERA5_ramp_demErr.h5',
    'timeseries_ERA5_ramp.h5',
    'timeseries_ERA5_demErr.h5',
    'timeseries_ERA5.h5',
    'timeseriesResidual_ramp.h5',
    'timeseriesResidual.h5',
    'timeseries.h5',
]


def _mintpy_attr_val(attrs, key):
    """Return the value for key from attrs, decoding bytes/numpy scalars/arrays to Python native."""
    import numpy as np
    v = attrs[key]
    if isinstance(v, (bytes, bytearray)):
        return v.decode().strip()
    if isinstance(v, np.ndarray):
        # flatten and take first element (attribute arrays are always 1-element in MintPy)
        v = v.flat[0]
        if isinstance(v, (bytes, bytearray, np.bytes_)):
            return v.decode().strip() if hasattr(v, 'decode') else str(v)
        return v.item() if hasattr(v, 'item') else float(v)
    if hasattr(v, 'item'):            # numpy scalar
        return v.item()
    return v


def _mintpy_epsg(attrs) -> int:
    """Determine EPSG code from MintPy attributes; raises ValueError if not found."""
    import re
    # 1. Explicit EPSG attribute
    if 'EPSG' in attrs:
        try:
            return int(float(str(_mintpy_attr_val(attrs, 'EPSG')).strip()))
        except Exception:
            pass
    # 2. UTM_ZONE attribute  e.g. '10N', '10S', '10'
    for key in ('UTM_ZONE', 'utmZone', 'utm_zone'):
        if key in attrs:
            s = str(_mintpy_attr_val(attrs, key)).strip().upper()
            m = re.match(r'(\d+)([NS]?)', s)
            if m:
                zone = int(m.group(1))
                hemi = m.group(2) or 'N'
                return (32600 if hemi == 'N' else 32700) + zone
    raise ValueError(
        'Projected coordinates detected (X_FIRST out of ±360° range) '
        'but no EPSG or UTM_ZONE attribute found in the HDF5 file.'
    )


def _mintpy_bounds(attrs) -> list:
    """[west, south, east, north] in WGS84 degrees from MintPy HDF5 geo-attributes.

    Handles both geographic (degrees) and projected (UTM metres) coordinate systems.
    """
    x_first = float(_mintpy_attr_val(attrs, 'X_FIRST'))
    y_first = float(_mintpy_attr_val(attrs, 'Y_FIRST'))
    x_step  = float(_mintpy_attr_val(attrs, 'X_STEP'))
    y_step  = float(_mintpy_attr_val(attrs, 'Y_STEP'))
    width   = int(float(str(_mintpy_attr_val(attrs, 'WIDTH')).strip()))
    length  = int(float(str(_mintpy_attr_val(attrs, 'LENGTH')).strip()))
    # X_FIRST / Y_FIRST are pixel-centre coordinates; convert to pixel-edge bounds
    # so that MapLibre renders the image with pixel centres at the correct geographic locations.
    half_x = 0.5 * abs(x_step)
    half_y = 0.5 * abs(y_step)
    x_center_last = x_first + x_step * (width  - 1)
    y_center_last = y_first + y_step * (length - 1)
    west  = min(x_first, x_center_last) - half_x
    east  = max(x_first, x_center_last) + half_x
    south = min(y_first, y_center_last) - half_y
    north = max(y_first, y_center_last) + half_y
    # Detect projected coordinates (UTM easting ~100 000 – 900 000 m)
    if abs(x_first) > 360 or abs(y_first) > 90:
        epsg = _mintpy_epsg(attrs)
        from pyproj import Transformer
        tf = Transformer.from_crs(epsg, 4326, always_xy=True)
        xs, ys = tf.transform([west, east, west, east],
                               [south, south, north, north])
        return [min(xs), min(ys), max(xs), max(ys)]
    return [west, south, east, north]


@app.get("/api/mintpy-check")
async def mintpy_check(path: str):
    """Return whether velocity.h5 exists and list all available timeseries*.h5 files."""
    folder = Path(path)
    has_velocity = (folder / 'velocity.h5').exists()
    ts_files = [n for n in _TS_PRIORITY if (folder / n).exists()]
    return {"has_velocity": has_velocity, "timeseries_files": ts_files}


@app.get("/api/render-velocity")
async def render_velocity(path: str):
    """Render velocity.h5 → colored PNG + float32 pixel array for hover."""
    import numpy as np, base64

    MAX_PIXEL = 256

    vel_path = Path(path) / 'velocity.h5'
    if not vel_path.exists():
        raise HTTPException(status_code=404, detail='velocity.h5 not found')
    try:
        import h5py

        # ── Read pixel data and geo-attributes via h5py ───────────────────────
        with h5py.File(vel_path, 'r') as f:
            ds   = f['velocity']
            data = ds[:].astype(np.float32)
            attrs = {k: v for k, v in f.attrs.items()}
            attrs.update({k: v for k, v in ds.attrs.items()})
        if data.ndim == 3:
            data = data[0]
        orig_h, orig_w = data.shape

        # ── WGS84 pixel-edge bounds from actual data shape ────────────────────
        x_first = float(_mintpy_attr_val(attrs, 'X_FIRST'))
        y_first = float(_mintpy_attr_val(attrs, 'Y_FIRST'))
        x_step  = float(_mintpy_attr_val(attrs, 'X_STEP'))
        y_step  = float(_mintpy_attr_val(attrs, 'Y_STEP'))
        
        is_projected = abs(x_first) > 360 or abs(y_first) > 90
        src_epsg = _mintpy_epsg(attrs) if is_projected else 4326
        src_crs = CRS.from_epsg(src_epsg)
        dst_crs = CRS.from_epsg(3857)

        # Pixel-edge bounds in the SOURCE CRS (UTM meters or WGS84 degrees)
        half_x = 0.5 * abs(x_step)
        half_y = 0.5 * abs(y_step)
        src_west  = x_first - half_x
        src_east  = x_first + x_step * (orig_w - 1) + half_x
        src_north = y_first + half_y
        src_south = y_first + y_step * (orig_h - 1) - half_y

        # Source transform must stay in the original CRS so reproject samples correctly
        src_tf = from_bounds(src_west, src_south, src_east, src_north, orig_w, orig_h)

        # Convert source corners to WGS84 for Mercator reprojection
        if is_projected:
            tf_src_to_wgs = Transformer.from_crs(src_epsg, 4326, always_xy=True)
            xs, ys = tf_src_to_wgs.transform(
                [src_west, src_east, src_west, src_east],
                [src_south, src_south, src_north, src_north],
            )
            west, south, east, north = min(xs), min(ys), max(xs), max(ys)
        else:
            west, south, east, north = src_west, src_south, src_east, src_north

        # Convert exact WGS84 corners to EPSG:3857 (no asymmetric padding)
        tf_to_merc = Transformer.from_crs(4326, 3857, always_xy=True)
        merc_w, merc_s = tf_to_merc.transform(west, south)
        merc_e, merc_n = tf_to_merc.transform(east, north)
        dst_w, dst_h = orig_w, orig_h
        dst_tf = from_bounds(merc_w, merc_s, merc_e, merc_n, dst_w, dst_h)

        src_data = np.where(np.isfinite(data) & (data != 0), data, np.nan)
        dst_data = np.full((dst_h, dst_w), np.nan, dtype=np.float32)
        reproject(
            source=src_data,
            destination=dst_data,
            src_transform=src_tf,
            src_crs=src_crs,
            dst_transform=dst_tf,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )

        # WGS84 bounds for MapLibre (back-convert from exact Mercator corners)
        tf_to_wgs = Transformer.from_crs(3857, 4326, always_xy=True)
        wgs_w, wgs_s = tf_to_wgs.transform(merc_w, merc_s)
        wgs_e, wgs_n = tf_to_wgs.transform(merc_e, merc_n)
        bounds = [wgs_w, wgs_s, wgs_e, wgs_n]


    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Processing error: {str(e)}')

    # 7. Final PNG Generation
    data = dst_data
    mask = ~np.isfinite(data) | (data == 0)
    
    # Static limits for velocity visualization
    vmin, vmax = -0.1, 0.1
    rgba = _colormap_numpy(data, mask, vmin, vmax, 'velocity')
    png_bytes = _rgba_to_png_bytes(rgba)
    png_b64 = base64.b64encode(png_bytes).decode()

    # 8. Optimized Pixel Hover Data
    # Resample the projected data for the frontend hover array
    scale_p = min(1.0, MAX_PIXEL / max(dst_h, dst_w))
    ph, pw = max(1, int(dst_h * scale_p)), max(1, int(dst_w * scale_p))
    row_idx = (np.arange(ph) * dst_h / ph).astype(int)
    col_idx = (np.arange(pw) * dst_w / pw).astype(int)
    pix_data = data[np.ix_(row_idx, col_idx)]
    pixel_b64 = base64.b64encode(pix_data.astype(np.float32).tobytes()).decode()

    unit = str(attrs.get('UNIT', 'm/year'))
    return {
        'png_b64': png_b64,
        'pixel_b64': pixel_b64,
        'bounds': bounds, # [West, South, East, North]
        'vmin': vmin,
        'vmax': vmax,
        'width': dst_w,
        'height': dst_h,
        'pixel_width': pw,
        'pixel_height': ph,
        'unit': unit,
        'label': f'Velocity ({unit})'
    }
        
       


@app.post("/api/folder-analyzer-cleanup")
async def folder_analyzer_cleanup(req: RunAnalyzerRequest):
    """Run analyzer.cleanup() to remove tmp dirs and zip archives."""
    folder = Path(req.folder_path)
    cls = Analyzer._registry.get(req.analyzer_type)
    if cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown analyzer: {req.analyzer_type}")
    config_cls = getattr(cls, "default_config", None)
    if config_cls is None or not dataclasses.is_dataclass(config_cls):
        raise HTTPException(status_code=400, detail="Analyzer has no config dataclass")
    cfg = config_cls(workdir=folder)
    analyzer = cls(cfg)
    try:
        analyzer.cleanup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@app.get("/api/timeseries-pixel")
async def timeseries_pixel(path: str, lat: float, lon: float, ts_file: str | None = None):
    """Extract a single pixel time series without loading the full 3-D stack."""
    folder = Path(path)
    if ts_file:
        ts_name = ts_file if (folder / ts_file).exists() else None
    else:
        ts_name = next((n for n in _TS_PRIORITY if (folder / n).exists()), None)
    if ts_name is None:
        raise HTTPException(status_code=404, detail='No timeseries file found')
    try:
        import h5py
        with h5py.File(folder / ts_name, 'r') as f:
            ds_ts = f['timeseries']
            # Merge file-level and dataset-level attrs
            attrs = {k: v for k, v in f.attrs.items()}
            attrs.update({k: v for k, v in ds_ts.attrs.items()})
            raw_dates = f['date'][:]
            x_first = float(_mintpy_attr_val(attrs, 'X_FIRST'))
            y_first = float(_mintpy_attr_val(attrs, 'Y_FIRST'))
            x_step  = float(_mintpy_attr_val(attrs, 'X_STEP'))
            y_step  = float(_mintpy_attr_val(attrs, 'Y_STEP'))
            width   = int(float(str(_mintpy_attr_val(attrs, 'WIDTH')).strip()))
            length  = int(float(str(_mintpy_attr_val(attrs, 'LENGTH')).strip()))
            # If projected, convert the incoming (lon, lat) to native CRS
            query_x, query_y = lon, lat
            if abs(x_first) > 360 or abs(y_first) > 90:
                epsg = _mintpy_epsg(attrs)
                from pyproj import Transformer
                tf = Transformer.from_crs(4326, epsg, always_xy=True)
                query_x, query_y = tf.transform(lon, lat)
            col = max(0, min(int(round((query_x - x_first) / x_step)), width  - 1))
            row = max(0, min(int(round((query_y - y_first) / y_step)), length - 1))
            # Lazy slice — reads only T values for this one pixel
            values = [float(v) for v in ds_ts[:, row, col]]
        def _decode_date(d):
            s = d.decode() if isinstance(d, (bytes, bytearray)) else str(d)
            return s.strip()
        dates     = [_decode_date(d) for d in raw_dates]
        iso_dates = [f'{d[:4]}-{d[4:6]}-{d[6:8]}' for d in dates if len(d) >= 8]
        unit      = str(_mintpy_attr_val(attrs, 'UNIT')) if 'UNIT' in attrs else 'm'
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f'Missing geo-attribute: {e}')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'h5py error: {e}')

    return {'dates': iso_dates, 'values': values, 'file': ts_name, 'unit': unit}


class Hyp3ActionRequest(BaseModel):
    folder_path:    str
    job_file:       str
    action:         str   # "refresh" | "retry" | "download"
    processor_type: str = "Hyp3_InSAR"


@app.post("/api/folder-hyp3-action", response_model=JobResponse)
async def folder_hyp3_action(req: Hyp3ActionRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting…", "data": None}
    background_tasks.add_task(_run_hyp3_action, job_id, req)
    return {"job_id": job_id}


async def _run_hyp3_action(job_id: str, req: Hyp3ActionRequest):
    def run():
        try:
            folder = Path(req.folder_path)
            job_file = folder / req.job_file
            if not job_file.exists():
                _jobs[job_id] = {"status": "error", "progress": 0, "message": f"{req.job_file} not found", "data": None}
                return

            proc_cls = Processor._registry.get(req.processor_type)
            if proc_cls is None:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": f"Unknown processor: {req.processor_type}", "data": None}
                return
            cfg_cls = getattr(proc_cls, "default_config", None)
            if cfg_cls is None or not dataclasses.is_dataclass(cfg_cls):
                _jobs[job_id] = {"status": "error", "progress": 0, "message": "Processor has no config", "data": None}
                return

            cfg = cfg_cls(workdir=folder)
            cfg.saved_job_path = str(job_file)
            _jobs[job_id]["message"] = "Initializing processor…"
            processor = Processor.create(req.processor_type, cfg)

            if req.action == "refresh":
                _jobs[job_id]["message"] = "Refreshing job statuses…"
                batchs = processor.refresh()
                lines = []
                counts: dict[str, int] = {}
                filenames: list[str] = []
                for user, batch in batchs.items():
                    lines.append(f"[{user}]")
                    for j in batch.jobs:
                        sc = j.status_code
                        counts[sc] = counts.get(sc, 0) + 1
                        lines.append(f"  {j.name:<35} {j.job_id:<12} | {sc}")
                        if sc == "SUCCEEDED" and j.files:
                            for fm in j.files:
                                fn = fm.get("filename") or fm.get("s3", {}).get("key", "").split("/")[-1]
                                if fn and fn.endswith(".zip"):
                                    filenames.append(fn)
                # Save file list cache so folder-ifg-list can find zips without a live API call
                try:
                    cache = {"filenames": filenames, "out_dir": processor.output_dir.as_posix()}
                    cache_path = folder / ".insarhub_cache.json"
                    cache_path.write_text(json.dumps(cache, indent=2))
                except Exception:
                    pass
                total = sum(counts.values())
                summary = f"{total} jobs — " + ", ".join(
                    f"{v} {k.lower()}" for k, v in sorted(counts.items())
                )
                lines.insert(0, summary)
                _jobs[job_id] = {"status": "done", "progress": 100, "message": "\n".join(lines), "data": None}

            elif req.action == "retry":
                _jobs[job_id]["message"] = "Retrying failed jobs…"
                processor.retry()
                _jobs[job_id] = {"status": "done", "progress": 100, "message": "Retry submitted. New job file saved.", "data": None}

            elif req.action == "download":
                import threading as _threading
                dl_stop = _threading.Event()
                _stop_events[job_id] = dl_stop
                _jobs[job_id]["message"] = "Downloading succeeded jobs…"

                def _dl_progress(msg: str, pct: int):
                    _jobs[job_id]["progress"] = pct
                    _jobs[job_id]["message"]  = msg

                _, dl_results = processor.download(progress_callback=_dl_progress, stop_event=dl_stop)
                _stop_events.pop(job_id, None)
                r = dl_results
                summary = (f"{r['downloaded']} downloaded, {r['skipped']} existing, {r['failed']} failed")
                if dl_stop.is_set():
                    summary = f"Stopped. {summary}"
                pct = 100 if not dl_stop.is_set() else _jobs[job_id].get("progress", 0)
                _jobs[job_id] = {"status": "done", "progress": pct, "message": summary, "data": None}

            else:
                _jobs[job_id] = {"status": "error", "progress": 0, "message": f"Unknown action: {req.action}", "data": None}

        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


class ParseAoiRequest(BaseModel):
    filename: str
    data: str   # base64-encoded file bytes


@app.post("/api/parse-aoi")
async def parse_aoi(req: ParseAoiRequest):
    """
    Parse a vector file (.zip shapefile or .gpkg) and return the first feature as GeoJSON.
    Accepts base64-encoded file data — no multipart needed.
    """
    suffix = Path(req.filename).suffix.lower()
    tmp_path = None
    try:
        content = base64.b64decode(req.data)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        gdf = gpd.read_file(tmp_path)
        if gdf.empty:
            raise HTTPException(status_code=422, detail="No features found in file")

        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        feature = json.loads(gdf.iloc[[0]].to_json())["features"][0]
        return {"feature": feature}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Download by scene name
# ---------------------------------------------------------------------------

@app.post("/api/download-by-name", response_model=JobResponse)
async def download_by_name(req: DownloadByNameRequest, background_tasks: BackgroundTasks):
    """Search ASF by granule name(s) and download them into workdir subfolders.

    Provide either ``scene_names`` (explicit list) or ``scene_file`` (path to a
    CSV / XLSX / TXT file).  Both may be supplied; they are merged.
    """
    if not req.scene_names and not req.scene_file:
        raise HTTPException(status_code=422, detail="Provide scene_names or scene_file")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting…", "data": None}
    stop_ev = _threading.Event()
    _stop_events[job_id] = stop_ev
    background_tasks.add_task(_run_download_by_name, job_id, req, stop_ev)
    return {"job_id": job_id}


async def _run_download_by_name(job_id: str, req: DownloadByNameRequest, stop_ev: _threading.Event):
    def run():
        try:
            workdir = Path(req.workdir).expanduser().resolve()
            workdir.mkdir(parents=True, exist_ok=True)

            dl_cls  = Downloader._registry.get(req.downloaderType)
            cfg_cls = getattr(dl_cls, "default_config", S1_SLC_Config) if dl_cls else S1_SLC_Config
            cfg = cfg_cls(workdir=workdir)

            downloader = Downloader.create(req.downloaderType, cfg)

            from insarhub.utils.tool import parse_scene_names_from_file
            names: list[str] = list(req.scene_names)
            if req.scene_file:
                names = list(dict.fromkeys(names + parse_scene_names_from_file(req.scene_file)))
            cfg.granule_names = names
            _jobs[job_id]["message"] = f"Searching {len(names)} scene(s)…"
            downloader.search()

            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
                return

            total = sum(len(v) for v in downloader.results.values())
            _jobs[job_id]["message"] = f"Downloading 0/{total}"

            def _on_progress(msg: str, pct: int):
                count = msg.split(']')[0].lstrip('[') if ']' in msg else ''
                _jobs[job_id]["message"] = f"Downloading {count}" if count else msg
                _jobs[job_id]["progress"] = pct

            dl_result = DownloadScenesCommand(
                downloader,
                stop_event=stop_ev,
                on_progress=_on_progress,
            ).run()

            if stop_ev.is_set():
                _jobs[job_id] = {"status": "done", "progress": 0, "message": "Stopped.", "data": None}
            else:
                _jobs[job_id] = {
                    "status":   "done" if dl_result.success else "error",
                    "progress": 100,
                    "message":  dl_result.message,
                    "data":     str(workdir),
                }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}
        finally:
            _stop_events.pop(job_id, None)

    await asyncio.to_thread(run)


# ---------------------------------------------------------------------------
# GeoJSON helper — converts asf_search results to MapLibre-ready FeatureCollection
# ---------------------------------------------------------------------------

def _to_geojson(results: dict) -> dict:
    features = []
    for stack_key, scenes in results.items():
        for scene in scenes:
            try:
                features.append({
                    "type": "Feature",
                    "geometry":   scene.geometry,
                    "properties": {**scene.properties, "_stack": str(stack_key)},
                })
            except Exception:
                continue
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Serve React production build (only active after `npm run build`)
# ---------------------------------------------------------------------------

_frontend = Path(__file__).parent / "frontend" / "dist"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")