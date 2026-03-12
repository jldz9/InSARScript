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
import uuid
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import wkt as shapely_wkt
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from insarhub.commands.downloader import DownloadScenesCommand, SearchCommand
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

_settings: dict[str, Any] = {
    "workdir":              str(Path.cwd()),
    "max_download_workers": 3,
    "downloader":           _DEFAULT_DOWNLOADER,
    "downloader_config":    _default_config_values(_DEFAULT_DOWNLOADER, _DOWNLOADERS_META),
    "processor":            _DEFAULT_PROCESSOR,
    "processor_config":     _default_config_values(_DEFAULT_PROCESSOR, _PROCESSORS_META),
    "analyzer":             _DEFAULT_ANALYZER,
    "analyzer_config":      _default_config_values(_DEFAULT_ANALYZER,  _ANALYZERS_META),
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
    start: str   = Field(..., example="2021-01-01")
    end: str     = Field(..., example="2022-01-01")
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


@app.get("/api/settings")
async def get_settings():
    """Return current settings including downloader/processor/analyzer config."""
    return {
        "workdir":              _settings["workdir"],
        "max_download_workers": _settings["max_download_workers"],
        "downloader":           _settings["downloader"],
        "downloader_config":    _settings["downloader_config"],
        "processor":            _settings["processor"],
        "processor_config":     _settings["processor_config"],
        "analyzer":             _settings["analyzer"],
        "analyzer_config":      _settings["analyzer_config"],
    }


class SettingsUpdate(BaseModel):
    workdir:              str | None             = None
    max_download_workers: int | None             = None
    downloader:           str | None             = None
    downloader_config:    dict[str, Any] | None  = None
    processor:            str | None             = None
    processor_config:     dict[str, Any] | None  = None
    analyzer:             str | None             = None
    analyzer_config:      dict[str, Any] | None  = None


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
        _settings["downloader_config"] = _default_config_values(req.downloader, _DOWNLOADERS_META)
    if req.downloader_config is not None:
        _settings["downloader_config"].update(req.downloader_config)
    if req.processor is not None:
        _settings["processor"] = req.processor
        _settings["processor_config"] = _default_config_values(req.processor, _PROCESSORS_META)
    if req.processor_config is not None:
        _settings["processor_config"].update(req.processor_config)
    if req.analyzer is not None:
        _settings["analyzer"] = req.analyzer
        _settings["analyzer_config"] = _default_config_values(req.analyzer, _ANALYZERS_META)
    if req.analyzer_config is not None:
        _settings["analyzer_config"].update(req.analyzer_config)
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
            # ASF search sends intersectsWith as a GET param; complex shapefiles can
            # produce WKT with thousands of vertices that exceed OS URL length limits.
            intersects_with = req.wkt if req.wkt else (req.west, req.south, req.east, req.north)
            if isinstance(intersects_with, str):
                try:
                    geom = shapely_wkt.loads(intersects_with)
                    # Simplify until WKT fits in ~2000 chars; tolerance in degrees (~100m–10km)
                    for tol in (0.001, 0.005, 0.01, 0.05, 0.1):
                        simplified = geom.simplify(tol, preserve_topology=True)
                        if len(simplified.wkt) <= 2000:
                            break
                    intersects_with = simplified.wkt
                except Exception:
                    pass  # leave as-is if shapely fails; let ASF report the error

            config = S1_SLC_Config(
                intersectsWith=intersects_with,
                start=req.start,
                end=req.end,
                workdir=req.workdir,
                maxResults=req.maxResults,
            )
            if req.beamMode:
                config.beamMode = req.beamMode
            if req.polarization:
                config.polarization = req.polarization
            if req.flightDirection:
                config.flightDirection = req.flightDirection
            if rel_orbit:
                config.relativeOrbit = rel_orbit
            if asf_frame:
                config.asfFrame = asf_frame
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
    def run():
        try:
            import asf_search as asf

            workdir = Path(req.workdir)
            workdir.mkdir(parents=True, exist_ok=True)

            filename = req.filename or req.url.rstrip("/").split("/")[-1].split("?")[0]
            _jobs[job_id]["message"] = f"Downloading {filename}…"

            asf.download_urls(
                urls=[req.url],
                path=str(workdir),
                processes=1,
            )

            _jobs[job_id] = {
                "status":   "done",
                "progress": 100,
                "message":  f"Saved {filename}",
                "data":     str(workdir / filename),
            }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

    await asyncio.to_thread(run)


@app.post("/api/download-stack", response_model=JobResponse)
async def download_stack(req: DownloadStackRequest, background_tasks: BackgroundTasks):
    """
    Download all scenes in a stack by their ASF URLs.
    Authentication is handled via ~/.netrc (Earthdata Login).
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "message": "Starting stack download...", "data": None}
    background_tasks.add_task(_run_download_stack, job_id, req)
    return {"job_id": job_id}


async def _run_download_stack(job_id: str, req: DownloadStackRequest):
    def run():
        try:
            import asf_search as asf

            workdir = Path(req.workdir)
            workdir.mkdir(parents=True, exist_ok=True)

            total = len(req.urls)
            _jobs[job_id]["message"] = f"Downloading {total} scenes…"

            asf.download_urls(
                urls=req.urls,
                path=str(workdir),
                processes=min(_settings["max_download_workers"], total),
            )

            _jobs[job_id] = {
                "status":   "done",
                "progress": 100,
                "message":  f"Downloaded {total} scene{'s' if total != 1 else ''} to {workdir}",
                "data":     str(workdir),
            }
        except Exception as e:
            _jobs[job_id] = {"status": "error", "progress": 0, "message": str(e), "data": None}

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


@app.get("/api/folder-image")
async def get_folder_image(path: str):
    """Serve a PNG image from the filesystem by absolute path."""
    img_path = Path(path)
    if not img_path.exists() or img_path.suffix.lower() != ".png":
        raise HTTPException(status_code=404, detail="Image not found")
    return StreamingResponse(open(img_path, "rb"), media_type="image/png")


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

            dl_result = DownloadScenesCommand(downloader, progress_callback=_make_progress(job_id)).run()
            _jobs[job_id] = {
                "status":   "done" if dl_result.success else "error",
                "progress": 100,
                "message":  dl_result.message,
                "data":     None,
            }
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