# Processor

Once you have added a job via **Add Job** in the Search panel, the job folder appears in the **Jobs** drawer. Click the **Jobs** button in the top-right corner of the toolbar to open the drawer.

<!-- screenshot: jobs button in toolbar -->
![Jobs Button](fig/jobs_button_light.png#only-light){: .doc-img}
![Jobs Button](fig/jobs_button_dark.png#only-dark){: .doc-img}
/// caption
The **Jobs** button in the top-right toolbar opens the Job Folders drawer.
///

Then click the downloader tag (e.g. **S1_SLC**) on the job folder to open its detail panel.

<!-- screenshot: clicking downloader tag on job folder -->
![Downloader Tag](fig/downloader_tag_light.png#only-light){: .doc-img style="width: 60%"}
![Downloader Tag](fig/downloader_tag_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Click the downloader tag on a job folder to open its detail panel.
///

## Selecting Pairs

Constructing a well-designed interferometric pair network is a critical step in time-series InSAR analysis. A carefully chosen SBAS network balances temporal and perpendicular baseline constraints to maximize coherence while ensuring full temporal connectivity across the scene stack.

Click **Select Pairs** to automatically generate an SBAS interferogram network from the downloaded scenes.

<!-- screenshot: select pairs button -->
![Select Pairs Button](fig/select_pairs_light.png#only-light){: .doc-img style="width: 60%"}
![Select Pairs Button](fig/select_pairs_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Click **Select Pairs** to open the pair network configuration dialog.
///

A configuration dialog will appear with the following options:

| Parameter | Description |
|-----------|-------------|
| **Target Temporal Baselines** | Comma-separated list of target temporal separations (days) to form pairs around |
| **Tolerance** | Allowed deviation (days) from each target baseline when matching scene pairs |
| **Max Temporal** | Hard upper limit on temporal baseline (days); pairs exceeding this are excluded |
| **Max Perp. Baseline** | Hard upper limit on perpendicular baseline (m); pairs exceeding this are excluded |
| **Min Connections** | Minimum number of interferograms each scene must participate in to ensure network connectivity |
| **Max Connections** | Maximum number of interferograms per scene to avoid redundancy |
| **Force Connected Network** | When enabled, adds extra pairs as needed to guarantee the network has no isolated nodes |

Click **Run** to generate the network. The resulting pair network is displayed as a baseline–time graph and saved to the job folder.

<!-- screenshot: pair network -->
![Pair Network](fig/pairs_light.png#only-light){: .doc-img style="width: 60%"}
![Pair Network](fig/pairs_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Interferogram pair network generated from the scene stack.
///

Once pair selection is complete, two viewing options become available:

**View Network** — displays the interferometric baseline–time graph, showing how scenes are connected across the temporal and perpendicular baseline dimensions.

<!-- screenshot: view network button -->
![View Network](fig/view_network_light.png#only-light){: .doc-img style="width: 60%"}
![View Network](fig/view_network_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Click **View Network** to open the baseline–time graph.
///

<!-- screenshot: network graph -->
![Network Graph](fig/network_graph_light.png#only-light){: .doc-img }
![Network Graph](fig/network_graph_dark.png#only-dark){: .doc-img }
/// caption
Baseline–time graph showing the interferometric network connectivity.
///

**View Pairs** — lists all selected interferometric pairs with their temporal and perpendicular baseline values.

<!-- screenshot: view pairs -->
![View Pairs](fig/view_pairs_light.png#only-light){: .doc-img style="width: 60%"}
![View Pairs](fig/view_pairs_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
List of selected interferometric pairs with baseline information.
///

---

## Submitting Jobs

Once the pair network is reviewed and satisfactory, click **Process** to open the processor selection dialog.

<!-- screenshot: click process button -->
![Process Button](fig/process_button_light.png#only-light){: .doc-img style="width: 60%"}
![Process Button](fig/process_button_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Click **Process** to submit interferogram pairs to HyP3.
///

<!-- screenshot: processor selection dialog -->
![Processor Selection](fig/processor_dialog_light.png#only-light){: .doc-img style="width: 60%"}
![Processor Selection](fig/processor_dialog_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
Processor selection dialog. Choose a processor (e.g. `Hyp3_InSAR`) and confirm to submit all pairs to HyP3.
///

!!! tip "Test before submitting"
    For submitting jobs to an external server, check **Dry Run** in the processor dialog to validate your environment and credentials without submitting real jobs. A successful dry run produces output similar to:

    ```
    [Dry run] Would submit 65 pairs via Hyp3_InSAR from p93_f121
    wrote processor_config.json
    marked insarhub_workflow.json processor=Hyp3_InSAR
    ```

    This is recommended before your first submission to ensure everything is configured correctly.

For a full description of all processor parameters and options, see the [Processor Reference](../advanced/processor.md).

Once jobs are successfully submitted, a **Processor** tag with your processor name will appear in the job folder panel, indicating that HyP3 processing is active for this stack.

<!-- screenshot: processor tab appears -->
![Processor Tab](fig/processor_tab_light.png#only-light){: .doc-img style="width: 60%"}
![Processor Tab](fig/processor_tab_dark.png#only-dark){: .doc-img style="width: 60%"}
/// caption
The **Processor** tab appears in the job folder panel after jobs are successfully submitted.
///

---

## Monitoring Jobs

Once jobs are submitted, a job file is automatically saved to the job folder and loaded by default the next time you open the Processor panel. This allows you to resume monitoring even after closing the application.

A drop-down menu at the top of the Processor panel lists all job files found under the job folder, including the initial submission file (`hyp3_jobs.json`) and any retry files generated by subsequent **Retry** actions (e.g. `hyp3_retry_jobs_20260306t095505.json`). Select a different file from the list to inspect or monitor a specific submission.

Click **Refresh** to check the latest status of all submitted jobs from HyP3. Each job displays one of the following statuses:

| Status | Meaning |
|--------|---------|
| `RUNNING` | Job is actively being processed on HyP3 |
| `SUCCEEDED` | Processing completed successfully |
| `FAILED` | Processing failed |

<!-- screenshot: job status list -->
![Job Status](fig/processor_status_light.png#only-light){: .doc-img style="width: 80%"}
![Job Status](fig/processor_status_dark.png#only-dark){: .doc-img style="width: 80%"}
/// caption
The processor job panel
///

If any jobs have `FAILED`, click **Retry** to resubmit them. Once jobs show `SUCCEEDED`, click **Download** to fetch the processed interferograms to the work directory.

---

## Other Actions

| Button | Description |
|--------|-------------|
| **Retry** | Resubmit all failed jobs to HyP3 |
| **Download** | Download all succeeded interferograms to the work directory |
| **Watch** | Continuously poll HyP3 until all jobs complete, then download automatically |
| **Credits** | Check remaining HyP3 processing credits |

---

Once all jobs have succeeded and interferograms are downloaded, proceed to the Analyzer panel to run time-series InSAR analysis.

[Analyzer](analyzer.md){.md-button}


