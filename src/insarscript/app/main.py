"""
Self-hosted Panel frontend for InSARScript.

All buttons call the same command classes used by the HPC CLI, so there
is no duplicated business logic.

Launch
------
    insarscript-app                  # starts on http://localhost:5006
    insarscript-app --port 8080
    panel serve src/insarscript/app/main.py --port 5006 --allow-websocket-origin='*'
"""

import argparse
import sys
import threading
from pathlib import Path

import panel as pn

pn.extension(sizing_mode="stretch_width")

# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------

def _make_log() -> pn.widgets.TextAreaInput:
    return pn.widgets.TextAreaInput(
        name="Log", value="", height=220, disabled=True,
    )


def _make_progress() -> pn.widgets.Progress:
    return pn.widgets.Progress(value=0, max=100, bar_color="primary", width=400)


def _make_status() -> pn.pane.Alert:
    return pn.pane.Alert("Ready.", alert_type="info", height=50)


def _panel_callback(progress: pn.widgets.Progress, log: pn.widgets.TextAreaInput):
    """Return a progress_callback that safely updates Panel widgets from a thread."""
    def callback(message: str, percent: int):
        def _update():
            progress.value = percent
            log.value = (log.value + f"\n[{percent:3d}%] {message}").lstrip()
        pn.state.execute(_update)
    return callback


def _run_in_thread(fn):
    t = threading.Thread(target=fn, daemon=True)
    t.start()


def _set_status(status: pn.pane.Alert, result, success_type="success"):
    def _update():
        if result.success:
            status.alert_type = success_type
            status.object = f"✓ {result.message}"
        else:
            status.alert_type = "danger"
            status.object = f"✗ {result.errors[0] if result.errors else result.message}"
    pn.state.execute(_update)


# ---------------------------------------------------------------------------
# Download page
# ---------------------------------------------------------------------------

class DownloaderPage(pn.viewable.Viewer):
    """Search and download satellite scenes."""

    def __init__(self, **params):
        super().__init__(**params)
        self._downloader = None

        # --- form widgets ---
        self._platform = pn.widgets.Select(
            name="Platform", value="S1_SLC",
            options=["S1_SLC"], width=150,
        )
        self._bbox_w = pn.widgets.FloatInput(name="West lon",  value=-113.05, width=120)
        self._bbox_s = pn.widgets.FloatInput(name="South lat", value=37.74,   width=120)
        self._bbox_e = pn.widgets.FloatInput(name="East lon",  value=-112.68, width=120)
        self._bbox_n = pn.widgets.FloatInput(name="North lat", value=38.00,   width=120)
        self._start  = pn.widgets.DatePicker(name="Start date", width=160)
        self._end    = pn.widgets.DatePicker(name="End date",   width=160)
        self._orbit  = pn.widgets.IntInput(name="Relative orbit", width=120)
        self._frame  = pn.widgets.IntInput(name="Frame",          width=120)
        self._direction = pn.widgets.Select(
            name="Direction", value="(any)",
            options=["(any)", "ASCENDING", "DESCENDING"], width=150,
        )
        self._max_results = pn.widgets.IntInput(name="Max results", value=1000, width=120)
        self._workdir = pn.widgets.TextInput(name="Work directory", value="./data", width=300)

        # --- action buttons ---
        self._btn_search    = pn.widgets.Button(name="Search",    button_type="primary", width=120)
        self._btn_footprint = pn.widgets.Button(name="Footprint", button_type="default", width=120, disabled=True)
        self._btn_summary   = pn.widgets.Button(name="Summary",   button_type="default", width=120, disabled=True)
        self._btn_filter    = pn.widgets.Button(name="Reset filter", button_type="warning", width=130, disabled=True)
        self._btn_download  = pn.widgets.Button(name="Download",  button_type="success", width=120, disabled=True)
        self._orbit_files   = pn.widgets.Checkbox(name="Download orbit files", value=False)
        self._workers       = pn.widgets.IntInput(name="Workers", value=3, width=80)
        self._footprint_path = pn.widgets.TextInput(
            name="Save footprint to (leave blank to display)", value="", width=300,
        )

        # --- output widgets ---
        self._progress = _make_progress()
        self._log      = _make_log()
        self._status   = _make_status()

        # wire buttons
        self._btn_search.on_click(self._on_search)
        self._btn_footprint.on_click(self._on_footprint)
        self._btn_summary.on_click(self._on_summary)
        self._btn_filter.on_click(self._on_reset)
        self._btn_download.on_click(self._on_download)

    # -- handlers --

    def _on_search(self, event):
        from insarscript import Downloader
        from insarscript.commands import SearchCommand

        self._btn_search.disabled = True
        self._log.value = ""
        self._progress.value = 0

        overrides = {
            "intersectsWith": [self._bbox_w.value, self._bbox_s.value,
                                self._bbox_e.value, self._bbox_n.value],
            "workdir": self._workdir.value or ".",
            "maxResults": self._max_results.value,
        }
        if self._start.value:
            overrides["start"] = str(self._start.value)
        if self._end.value:
            overrides["end"] = str(self._end.value)
        if self._orbit.value:
            overrides["relativeOrbit"] = self._orbit.value
        if self._frame.value:
            overrides["frame"] = self._frame.value
        if self._direction.value != "(any)":
            overrides["flightDirection"] = self._direction.value

        platform = self._platform.value

        def _run():
            try:
                downloader = Downloader.create(platform, **overrides)
                self._downloader = downloader
                cb = _panel_callback(self._progress, self._log)
                result = SearchCommand(downloader, progress_callback=cb).run()
                _set_status(self._status, result)
                if result.success:
                    def _enable():
                        self._btn_footprint.disabled = False
                        self._btn_summary.disabled   = False
                        self._btn_filter.disabled    = False
                        self._btn_download.disabled  = False
                    pn.state.execute(_enable)
            finally:
                pn.state.execute(lambda: setattr(self._btn_search, "disabled", False))

        _run_in_thread(_run)

    def _on_footprint(self, event):
        from insarscript.commands import FootprintCommand
        if self._downloader is None:
            return

        save_path = self._footprint_path.value.strip() or None

        def _run():
            cb = _panel_callback(self._progress, self._log)
            result = FootprintCommand(self._downloader, save_path=save_path, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def _on_summary(self, event):
        from insarscript.commands import SummaryCommand
        if self._downloader is None:
            return

        def _run():
            cb = _panel_callback(self._progress, self._log)
            result = SummaryCommand(self._downloader, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def _on_reset(self, event):
        from insarscript.commands import ResetCommand
        if self._downloader is None:
            return
        result = ResetCommand(self._downloader).run()
        _set_status(self._status, result)

    def _on_download(self, event):
        from insarscript.commands import DownloadScenesCommand
        if self._downloader is None:
            return

        self._btn_download.disabled = True
        dl_kwargs = {"max_workers": self._workers.value}
        if hasattr(self._downloader, "download") and \
                "download_orbit" in self._downloader.download.__code__.co_varnames:
            dl_kwargs["download_orbit"] = self._orbit_files.value

        def _run():
            cb = _panel_callback(self._progress, self._log)
            result = DownloadScenesCommand(self._downloader, progress_callback=cb, **dl_kwargs).run()
            _set_status(self._status, result)
            pn.state.execute(lambda: setattr(self._btn_download, "disabled", False))

        _run_in_thread(_run)

    def __panel__(self):
        form = pn.Column(
            pn.pane.Markdown("### Configuration"),
            pn.Row(self._platform, self._direction, self._max_results),
            pn.pane.Markdown("**Bounding box**"),
            pn.Row(self._bbox_w, self._bbox_s, self._bbox_e, self._bbox_n),
            pn.Row(self._start, self._end),
            pn.Row(self._orbit, self._frame),
            self._workdir,
            pn.layout.Divider(),
            pn.pane.Markdown("### Actions"),
            pn.Row(self._btn_search, self._btn_footprint, self._btn_summary, self._btn_filter),
            self._footprint_path,
            pn.layout.Divider(),
            pn.pane.Markdown("### Download"),
            pn.Row(self._workers, self._orbit_files),
            self._btn_download,
        )
        output = pn.Column(
            self._status,
            self._progress,
            self._log,
        )
        return pn.Row(form, pn.layout.HSpacer(), output)


# ---------------------------------------------------------------------------
# Process page
# ---------------------------------------------------------------------------

class ProcessorPage(pn.viewable.Viewer):
    """Submit and manage HyP3 InSAR processing jobs."""

    def __init__(self, **params):
        super().__init__(**params)
        self._processor = None

        self._workdir   = pn.widgets.TextInput(name="Work directory", value="./data", width=300)
        self._job_file  = pn.widgets.TextInput(name="Saved job file (leave blank for default)", value="", width=300)
        self._pairs     = pn.widgets.TextAreaInput(
            name='Pairs (one "reference,secondary" per line, or load from JSON file)',
            height=120, width=400,
        )
        self._pairs_file = pn.widgets.TextInput(name="Pairs JSON file path", value="", width=300)
        self._looks      = pn.widgets.Select(name="Looks", value="20x4",
                                             options=["20x4", "10x2", "5x1"], width=100)
        self._water_mask = pn.widgets.Checkbox(name="Apply water mask", value=True)
        self._interval   = pn.widgets.IntInput(name="Watch interval (sec)", value=300, width=120)

        self._btn_submit   = pn.widgets.Button(name="Submit",          button_type="primary",  width=130)
        self._btn_refresh  = pn.widgets.Button(name="Refresh status",  button_type="default",  width=140)
        self._btn_dl       = pn.widgets.Button(name="Download results",button_type="success",  width=150)
        self._btn_retry    = pn.widgets.Button(name="Retry failed",    button_type="warning",  width=130)
        self._btn_watch    = pn.widgets.Button(name="Watch (blocking)",button_type="danger",   width=150)
        self._btn_save     = pn.widgets.Button(name="Save job IDs",    button_type="light",    width=130)
        self._btn_credits  = pn.widgets.Button(name="Check credits",   button_type="light",    width=130)

        self._progress = _make_progress()
        self._log      = _make_log()
        self._status   = _make_status()

        self._btn_submit.on_click(self._on_submit)
        self._btn_refresh.on_click(self._on_refresh)
        self._btn_dl.on_click(self._on_download)
        self._btn_retry.on_click(self._on_retry)
        self._btn_watch.on_click(self._on_watch)
        self._btn_save.on_click(self._on_save)
        self._btn_credits.on_click(self._on_credits)

    def _build_processor(self, pairs=None):
        from insarscript import Processor

        workdir  = Path(self._workdir.value or ".").expanduser().resolve()
        job_file = self._job_file.value.strip() or None
        overrides: dict = {"workdir": workdir, "looks": self._looks.value,
                           "apply_water_mask": self._water_mask.value}
        if pairs:
            overrides["pairs"] = pairs
        if job_file:
            overrides["saved_job_path"] = job_file
        elif not pairs:
            default = workdir / "hyp3_jobs.json"
            if default.is_file():
                overrides["saved_job_path"] = default
        return Processor.create("Hyp3_InSAR", **overrides)

    def _parse_pairs_from_ui(self) -> list[tuple[str, str]] | None:
        if self._pairs_file.value.strip():
            import json
            raw = json.loads(Path(self._pairs_file.value.strip()).read_text())
            return [tuple(p) for p in raw]
        text = self._pairs.value.strip()
        if not text:
            return None
        pairs = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 2:
                pairs.append((parts[0], parts[1]))
        return pairs or None

    def _on_submit(self, event):
        from insarscript.commands import SubmitCommand, SaveJobsCommand

        self._btn_submit.disabled = True
        self._log.value = ""

        def _run():
            try:
                pairs = self._parse_pairs_from_ui()
                if not pairs:
                    pn.state.execute(lambda: setattr(self._status, "object",
                                                     "✗ No pairs provided"))
                    return
                self._processor = self._build_processor(pairs=pairs)
                cb = _panel_callback(self._progress, self._log)
                result = SubmitCommand(self._processor, progress_callback=cb).run()
                _set_status(self._status, result)
                if result.success:
                    SaveJobsCommand(self._processor).run()
            finally:
                pn.state.execute(lambda: setattr(self._btn_submit, "disabled", False))

        _run_in_thread(_run)

    def _on_refresh(self, event):
        from insarscript.commands import RefreshCommand

        def _run():
            if self._processor is None:
                self._processor = self._build_processor()
            cb = _panel_callback(self._progress, self._log)
            result = RefreshCommand(self._processor, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def _on_download(self, event):
        from insarscript.commands import DownloadResultsCommand

        def _run():
            if self._processor is None:
                self._processor = self._build_processor()
            cb = _panel_callback(self._progress, self._log)
            result = DownloadResultsCommand(self._processor, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def _on_retry(self, event):
        from insarscript.commands import RetryCommand

        def _run():
            if self._processor is None:
                self._processor = self._build_processor()
            cb = _panel_callback(self._progress, self._log)
            result = RetryCommand(self._processor, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def _on_watch(self, event):
        from insarscript.commands import WatchCommand

        self._btn_watch.disabled = True

        def _run():
            try:
                if self._processor is None:
                    self._processor = self._build_processor()
                cb = _panel_callback(self._progress, self._log)
                result = WatchCommand(self._processor,
                                      refresh_interval=self._interval.value,
                                      progress_callback=cb).run()
                _set_status(self._status, result)
            finally:
                pn.state.execute(lambda: setattr(self._btn_watch, "disabled", False))

        _run_in_thread(_run)

    def _on_save(self, event):
        from insarscript.commands import SaveJobsCommand

        if self._processor is None:
            return
        result = SaveJobsCommand(self._processor).run()
        _set_status(self._status, result)

    def _on_credits(self, event):
        from insarscript.commands import CheckCreditsCommand

        def _run():
            if self._processor is None:
                self._processor = self._build_processor()
            cb = _panel_callback(self._progress, self._log)
            result = CheckCreditsCommand(self._processor, progress_callback=cb).run()
            _set_status(self._status, result)

        _run_in_thread(_run)

    def __panel__(self):
        form = pn.Column(
            pn.pane.Markdown("### Configuration"),
            self._workdir,
            self._job_file,
            pn.Row(self._looks, self._water_mask),
            pn.layout.Divider(),
            pn.pane.Markdown("### Pairs"),
            self._pairs_file,
            self._pairs,
            pn.layout.Divider(),
            pn.pane.Markdown("### Actions"),
            pn.Row(self._btn_submit, self._btn_refresh, self._btn_dl),
            pn.Row(self._btn_retry, self._btn_save, self._btn_credits),
            pn.Row(self._interval, self._btn_watch),
        )
        output = pn.Column(
            self._status,
            self._progress,
            self._log,
        )
        return pn.Row(form, pn.layout.HSpacer(), output)


# ---------------------------------------------------------------------------
# Analyze page
# ---------------------------------------------------------------------------

class AnalyzerPage(pn.viewable.Viewer):
    """Prepare HyP3 outputs and run MintPy SBAS time-series analysis."""

    def __init__(self, **params):
        super().__init__(**params)
        self._analyzer = None

        self._workdir = pn.widgets.TextInput(name="Work directory", value="./data", width=300)
        self._steps   = pn.widgets.TextAreaInput(
            name="MintPy steps (one per line, blank = full workflow)",
            height=120, width=400,
        )

        self._btn_prep    = pn.widgets.Button(name="Prep data",  button_type="primary", width=130)
        self._btn_analyze = pn.widgets.Button(name="Run analysis", button_type="success", width=140)
        self._btn_prep_and_analyze = pn.widgets.Button(name="Prep + Analyze",
                                                        button_type="success", width=150)

        self._progress = _make_progress()
        self._log      = _make_log()
        self._status   = _make_status()

        self._btn_prep.on_click(self._on_prep)
        self._btn_analyze.on_click(self._on_analyze)
        self._btn_prep_and_analyze.on_click(self._on_prep_and_analyze)

    def _build_analyzer(self):
        from insarscript import Analyzer

        workdir = Path(self._workdir.value or ".").expanduser().resolve()
        return Analyzer.create("Hyp3_SBAS", workdir=workdir)

    def _parse_steps(self) -> list[str] | None:
        text = self._steps.value.strip()
        if not text:
            return None
        return [s.strip() for s in text.splitlines() if s.strip()]

    def _on_prep(self, event):
        from insarscript.commands import PrepDataCommand

        self._btn_prep.disabled = True

        def _run():
            try:
                self._analyzer = self._build_analyzer()
                cb = _panel_callback(self._progress, self._log)
                result = PrepDataCommand(self._analyzer, progress_callback=cb).run()
                _set_status(self._status, result)
            finally:
                pn.state.execute(lambda: setattr(self._btn_prep, "disabled", False))

        _run_in_thread(_run)

    def _on_analyze(self, event):
        from insarscript.commands import AnalyzeCommand

        self._btn_analyze.disabled = True

        def _run():
            try:
                if self._analyzer is None:
                    self._analyzer = self._build_analyzer()
                cb = _panel_callback(self._progress, self._log)
                result = AnalyzeCommand(self._analyzer,
                                        steps=self._parse_steps(),
                                        progress_callback=cb).run()
                _set_status(self._status, result)
            finally:
                pn.state.execute(lambda: setattr(self._btn_analyze, "disabled", False))

        _run_in_thread(_run)

    def _on_prep_and_analyze(self, event):
        from insarscript.commands import PrepDataCommand, AnalyzeCommand

        self._btn_prep_and_analyze.disabled = True

        def _run():
            try:
                self._analyzer = self._build_analyzer()
                cb = _panel_callback(self._progress, self._log)
                r = PrepDataCommand(self._analyzer, progress_callback=cb).run()
                if not r.success:
                    _set_status(self._status, r)
                    return
                result = AnalyzeCommand(self._analyzer,
                                        steps=self._parse_steps(),
                                        progress_callback=cb).run()
                _set_status(self._status, result)
            finally:
                pn.state.execute(lambda: setattr(self._btn_prep_and_analyze, "disabled", False))

        _run_in_thread(_run)

    def __panel__(self):
        form = pn.Column(
            pn.pane.Markdown("### Configuration"),
            self._workdir,
            self._steps,
            pn.layout.Divider(),
            pn.pane.Markdown("### Actions"),
            pn.Row(self._btn_prep, self._btn_analyze),
            self._btn_prep_and_analyze,
        )
        output = pn.Column(
            self._status,
            self._progress,
            self._log,
        )
        return pn.Row(form, pn.layout.HSpacer(), output)


# ---------------------------------------------------------------------------
# App composition
# ---------------------------------------------------------------------------

def create_app():
    header = pn.pane.Markdown(
        "# InSARScript\nEnd-to-end InSAR processing — download · process · analyze",
        sizing_mode="stretch_width",
    )
    tabs = pn.Tabs(
        ("Download",  DownloaderPage()),
        ("Process",   ProcessorPage()),
        ("Analyze",   AnalyzerPage()),
        dynamic=True,
    )
    return pn.Column(header, tabs, sizing_mode="stretch_width")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def serve():
    """Entry point for the `insarscript-app` CLI command."""
    parser = argparse.ArgumentParser(prog="insarscript-app",
                                     description="Launch the InSARScript Panel web UI")
    parser.add_argument("--port",  type=int, default=5006, help="Server port (default: 5006)")
    parser.add_argument("--host",  type=str, default="localhost", help="Bind address (default: localhost)")
    parser.add_argument("--open",  action="store_true", default=True,
                        help="Open browser automatically (default: True)")
    args = parser.parse_args()

    print(f"Starting InSARScript UI at http://{args.host}:{args.port}")
    pn.serve(
        create_app,
        port=args.port,
        address=args.host,
        show=args.open,
        title="InSARScript",
    )


# Allow `panel serve src/insarscript/app/main.py` to discover the app
app = create_app()

if __name__ == "__main__":
    serve()
