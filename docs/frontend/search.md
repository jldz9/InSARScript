# Search & Download

## Settings

By default, work directory will be the directory where `insarhub-app` is run, user may
specify the work directory under setting

<!-- screenshot: settings panel open -->
![Settings Panel](fig/settings_light.png#only-light){: .doc-img}
![Settings Panel](fig/settings_dark.png#only-dark){: .doc-img}
/// caption
Settings panel showing work directory and API configuration.
///

---

## Searching for Scenes

1. Draw an AOI on the map
2. Set the date range and select a downloader (default is `S1_SLC`)
3. Click **Search**

<!-- screenshot: search panel with results -->
![Search Panel](fig/search_light.png#only-light){: .doc-img}
![Search Panel](fig/search_dark.png#only-dark){: .doc-img}
/// caption
Search panel showing available Sentinel-1 stacks.
///

Search results appear as footprints overlaid on the map. Click any footprint to open the **Scene Detail** panel, which displays acquisition metadata including platform, orbit, beam mode, polarization, file size, and download options for that scene.

Click **▸ View Detail** in the Scene Detail panel to expand the job drawer showing the full list of individual scenes in the stack. Click **◂ Hide Detail** to collapse it.

<!-- screenshot: search results footprints on map -->
![Search Results](fig/search_results_light.png#only-light){: .doc-img style="width: 60%"}
![Search Results](fig/search_results_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Search result footprints displayed on the map. Click a footprint to view scene details.
///

---

## Downloading

Click **Download Stack** to start downloading scenes for the selected stack to the work directory. Progress is shown live during the download and can be stopped at any time.

For a full description of all downloader parameters and options, see the [Downloader Reference](../advanced/downloader.md).


## Downloading Orbit Files

Click **Download Orbit Files** to download the corresponding precise orbit files for the stack. Orbit files are required for accurate InSAR processing and will be saved alongside the scene data in the work directory.


## Adding a Job

Click **Add Job** to register the selected stack as a job in the Jobs panel. This saves the stack configuration for future downloading and processing without starting any download immediately.

---

Once your job is added, head to the Processor panel to select interferometric pairs and submit them for processing.

[Processor](processor.md){.md-button}
