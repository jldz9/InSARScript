# Changelog

## [0.2.4] - 2026-03-25

### New Features
- **CLI & API**: `select_pairs()` is now a pure computation method — no file I/O inside the class. File writing (JSON, PNG, workflow marker) has been moved to the CLI and API call sites, keeping the core logic reusable and testable
- **Path handling**: All functions that accept path arguments now call `.expanduser().resolve()`, enabling `~` tilde paths everywhere
- **WebUI**: Added documentation button in the General Settings panel (bottom-left) linking to the InSARHub docs site
- **WebUI (`insarhub-app`)**: Auto-creates the working directory if it does not exist when `-w <path>` is passed
- **CLI (`insarhub-app`)**: Added `-v` / `--version` flag
- **Windows fix**: `insarhub-app` no longer returns immediately on Windows — sets `WindowsSelectorEventLoopPolicy` so uvicorn blocks correctly

### Bug Fixes
- **WebUI Processor**: Unchecking dry-run after a completed run no longer leaves the button stuck at "✓ Done" — the status resets to idle on checkbox change
- **WebUI Processor**: Clicking "✓ Done" after a real (non-dry-run) submit now correctly closes the modal
- **WebUI Processor**: "✓ Done" button now shows a pointer cursor on hover
- **Analyzer**: Fixed `NoneType` crash in troposphere correction when `Path.mkdir()` was called on an already-resolved path
- **CLI credential setup**: Removed spurious blank first line from `.cdsapirc` written by the interactive credential prompt

---

## [0.2.3] - 2026-03-18

### New Features
- **Documentation**: Completed full WebUI (frontend) documentation with screenshots and usage guide
- **Documentation**: Added version changelog and update log pages to the docs site
- **WebUI**: Added email and Discord contact buttons next to the light/dark mode toggle in the header
- **WebUI**: Reduced extra whitespace around the GitHub badge in the header


### Bug Fixes
- Fixed gh-pages CI push rejection when remote branch was ahead of local (`git fetch origin gh-pages` before `mike deploy`)
- Minor doc link and typo fixes
- Fixed broken image link in the WebUI overview documentation page

---

## [0.2.1] - 2026-03-06

### New Features
- **Frontend**: Download orbit file option added to the downloader panel
- **Frontend**: Granule name file upload — users can supply a text file of scene names for custom searches
- **Frontend**: Drawer now auto-hides when the user clicks on the map
- **Downloader**: Added `parse_granule_names()` to parse scene names from a string, list, or file for search
- **Downloader (`S1_SLC`)**: `-O <dir>` now downloads all orbit files to the specified directory
- **Downloader (`S1_SLC`)**: Skips orbit files that already exist (checked by acquisition time)
- **Downloader**: Automatically falls back to the ASF orbit server if the CDSE sentineleof server fails
- **Documentation**: Completed WebUI documentation

### Bug Fixes
- Fixed velocity map display shifting caused by incorrect EPSG selection in the frontend
- Fixed duplicate search results when multiple stacks share the same path (ASF server-side bug workaround)
- Fixed `[ERROR] download: not enough values to unpack` in the download future handler
- Fixed numpy deprecation warnings
- Pinned CI to Python 3.12 to avoid breakage on 3.13/3.14

---

## [0.2.0] - 2026-02-20

### New Features
- **WebUI (`insarhub-app`)**: Full Panel-based browser frontend for download, processing, and analysis
- **Frontend**: Interactive map for AOI selection with basemap overlay
- **Frontend**: Job queue drawer with dry-run toggle, live log streaming, and submit/cancel controls
- **Frontend**: Settings panel for credentials, working directory, and HyP3 account configuration
- **Frontend**: Velocity and time-series result visualization directly in the browser
- **CLI**: `insarhub-app` command to launch the WebUI server
- **Core**: Unified `CommandResult` pattern shared between CLI and Panel frontend
- **Core**: `InSAREngine` high-level pipeline runner with per-step skip flags and watch mode

---

## [0.1.0] - 2026-03-06

### Initial Release

First public release of **InSARHub** — a modular Python framework for automated InSAR time-series processing.

---

### Features

#### Downloader
- `ASF_Base_Downloader`: Search and download Sentinel-1, ALOS, and NISAR SLC data via the ASF Search API
- Spatial filtering with bounding box, WKT, or GeoJSON/shapefile AOI
- Post-search filtering by date range, path/frame, flight direction, polarization, season, coverage, and scene count
- Scene footprint visualization with basemap overlay (`footprint()`)
- DEM download via `dem-stitcher` aligned to search footprints
- Multi-threaded download with Ctrl+C cancellation and partial-file cleanup
- `S1_SLC`: Sentinel-1 SLC specialized downloader with orbit file (`sentineleof`) support

#### Processor
- `Hyp3_InSAR`: Submit, monitor, download, retry, and persist HyP3 InSAR jobs
- Multi-account credential pool with automatic credit-aware job rotation
- Batch job persistence (save/load JSON) for resumable workflows
- `watch()` mode: polls job status and downloads succeeded outputs continuously
- Retry failed jobs with automatic timestamp-stamped save files

#### Analyzer
- `Hyp3_SBAS`: End-to-end MintPy SBAS time-series analysis from HyP3 outputs
- Automatic unzip, file collection, common-overlap clipping, and MintPy config generation
- Optional pyAPS tropospheric correction with CDS API credential management
- `cleanup()` to remove temporary files after processing

#### Utilities
- `select_pairs`: Temporal and perpendicular baseline filtering with configurable targets and tolerances
- Local baseline computation (zero network calls for Sentinel-1 and ALOS)
- API fallback with threaded fetching for products without local baseline data
- Connectivity enforcement: minimum/maximum degree per scene with force-connect option
- `plot_pair_network`: Network visualization with per-scene connection histogram
- `ERA5Downloader`: Batch ERA5 reanalysis download for MintPy tropospheric correction, MintPy-compatible filenames
- `clip_hyp3_insar`: Clip HyP3 zip outputs to a custom AOI before analysis
- `Slurmjob_Config`: Generate SLURM batch scripts for HPC job submission
- `earth_credit_pool`: Load multi-account Earthdata credentials from a pool file

#### CLI (`insarhub`)
- `insarhub download` — search, filter, and download SLC scenes
- `insarhub processor submit/refresh/download/retry/watch/save/credits` — full HyP3 job lifecycle
- `insarhub analyzer prep/run` — prepare and run MintPy analysis
- `insarhub utils select-pairs/plot-network/era5/clip` — utility commands
- Workdir (`-w`) and credential pool (`--credential-pool`) flags across all subcommands

#### Core
- Auto-registering component registry (`Downloader`, `Processor`, `Analyzer`)
- `InSAREngine`: high-level pipeline runner with skip flags and watch mode
- Unified `CommandResult` pattern shared between CLI and Panel frontend


[0.2.4]: https://github.com/jldz9/InSARHub/releases/tag/v0.2.4
[0.2.3]: https://github.com/jldz9/InSARHub/releases/tag/v0.2.3
[0.2.1]: https://github.com/jldz9/InSARHub/releases/tag/v0.2.1
[0.2.0]: https://github.com/jldz9/InSARHub/releases/tag/v0.2.0
[0.1.0]: https://github.com/jldz9/InSARHub/releases/tag/v0.1.0
