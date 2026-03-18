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
2. Open the **Search** panel in the job panel
3. Set the date range and select a downloader (default is `S1_SLC`)
4. Click **Search**

<!-- screenshot: search panel with results -->
![Search Panel](fig/search_light.png#only-light){: .doc-img}
![Search Panel](fig/search_dark.png#only-dark){: .doc-img}
/// caption
Search panel showing available Sentinel-1 stacks.
///

Search results appear as a list of stacks grouped by path and frame. Each stack shows the scene count and date range.

---

## Selecting Pairs

Click **Select Pairs** to automatically generate an interferogram network from the search results.

<!-- screenshot: pair network image shown -->
![Pair Network](fig/pairs_light.png#only-light){: .doc-img}
![Pair Network](fig/pairs_dark.png#only-dark){: .doc-img}
/// caption
Interferogram pair network generated from search results.
///

---

## Downloading

Click **Download** to start downloading scenes to the work directory. Progress is shown per worker.

<!-- screenshot: download in progress -->
![Download Progress](fig/download_light.png#only-light){: .doc-img}
![Download Progress](fig/download_dark.png#only-dark){: .doc-img}
/// caption
Scene download in progress with per-worker status.
///

### Orbit Files

Orbit file download is not available in the Web UI. Use the CLI instead:

```bash
insarhub downloader --AOI ... --download -O
```

See [CLI reference](../quickstart/cli.md#download) for details.
