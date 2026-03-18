# Processor

The Processor panel submits interferogram pairs to HyP3 for online processing.

## Submitting Jobs

1. Open a job folder that contains a `pairs.json` file
2. Open the **Processor** panel
3. Select a processor (`Hyp3_InSAR`)
4. Click **Submit**

<!-- screenshot: processor panel before submit -->
![Processor Panel](fig/processor_light.png#only-light){: .doc-img}
![Processor Panel](fig/processor_dark.png#only-dark){: .doc-img}
/// caption
Processor panel ready to submit interferogram pairs to HyP3.
///

---

## Monitoring Jobs

Click **Refresh** to update job statuses. Each job shows `SUCCEEDED`, `FAILED`, or `RUNNING`.

<!-- screenshot: job status list -->
![Job Status](fig/processor_status_light.png#only-light){: .doc-img}
![Job Status](fig/processor_status_dark.png#only-dark){: .doc-img}
/// caption
HyP3 job status after refresh.
///

---

## Downloading Results

Once jobs complete, click **Download** to fetch the processed interferograms.

<!-- screenshot: download complete -->
![Download Complete](fig/processor_download_light.png#only-light){: .doc-img}
![Download Complete](fig/processor_download_dark.png#only-dark){: .doc-img}
/// caption
Completed HyP3 results downloaded to the work directory.
///

---

## Other Actions

| Button | Description |
|--------|-------------|
| **Retry** | Resubmit failed jobs |
| **Watch** | Poll HyP3 until all jobs complete |
| **Credits** | Check remaining HyP3 processing credits |
