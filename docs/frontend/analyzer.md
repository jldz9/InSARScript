# Analyzer

The Analyzer panel runs MintPy time-series analysis on downloaded HyP3 interferograms.

## Opening the Analyzer

Click a job folder that contains downloaded HyP3 results, then open the **Analyzer** tab.

<!-- screenshot: analyzer panel overview -->
![Analyzer Panel](fig/analyzer_light.png#only-light){: .doc-img}
![Analyzer Panel](fig/analyzer_dark.png#only-dark){: .doc-img}
/// caption
Analyzer panel showing available steps and configuration.
///

---

## Configuration

Click **Change Config** to open the analyzer settings. Each analyzer type (`Hyp3_SBAS`) has its own independent configuration that is saved separately.

<!-- screenshot: analyzer config panel -->
![Analyzer Config](fig/analyzer_config_light.png#only-light){: .doc-img}
![Analyzer Config](fig/analyzer_config_dark.png#only-dark){: .doc-img}
/// caption
Analyzer configuration for Hyp3_SBAS.
///

---

## Running Steps

Select the steps to run and click **Run**. Steps run sequentially and progress is shown in the log.

<!-- screenshot: analyzer running with log output -->
![Analyzer Running](fig/analyzer_running_light.png#only-light){: .doc-img}
![Analyzer Running](fig/analyzer_running_dark.png#only-dark){: .doc-img}
/// caption
Analyzer running `load_data` and `invert_network` steps.
///

Available MintPy steps:

| Step | Description |
|------|-------------|
| `load_data` | Load interferograms into MintPy HDF5 format |
| `modify_network` | Apply network modifications |
| `reference_point` | Select reference pixel |
| `invert_network` | SBAS inversion for time-series |
| `correct_troposphere` | Tropospheric delay correction |
| `deramp` | Remove orbital ramp |
| `correct_topography` | DEM error correction |
| `residual_RMS` | Residual RMS analysis |
| `reference_date` | Set reference date |
| `velocity` | Estimate linear velocity |
| `geocode` | Geocode to geographic coordinates |

---

## Cleanup

Click **Cleanup** to remove intermediate MintPy files and free disk space, allowing a clean rerun.

<!-- screenshot: cleanup confirmation -->
![Cleanup](fig/analyzer_cleanup_light.png#only-light){: .doc-img}
![Cleanup](fig/analyzer_cleanup_dark.png#only-dark){: .doc-img}
/// caption
Cleanup removes intermediate HDF5 files from the working directory.
///
