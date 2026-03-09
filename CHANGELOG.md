# Changelog

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


[0.1.0]: https://github.com/jldz9/InSARHub/releases/tag/v0.1.0
