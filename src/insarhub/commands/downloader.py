# -*- coding: utf-8 -*-
from insarhub.core.base import BaseDownloader
from .base import BaseCommand, CommandResult


class SearchCommand(BaseCommand):
    """Wraps downloader.search() — works with any registered BaseDownloader."""

    def __init__(self, downloader: BaseDownloader, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader

    def run(self) -> CommandResult:
        try:
            self.progress("Starting search...", 0)
            results = self.downloader.search()
            total = sum(len(v) for v in results.values())
            stacks = len(results)
            self.progress(f"Found {total} scenes in {stacks} stacks", 100)
            return CommandResult(
                success=True,
                message=f"Found {total} scenes in {stacks} stacks",
                data=results,
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class FilterCommand(BaseCommand):
    """Wraps downloader.filter(**filter_kwargs) on existing search results."""

    def __init__(self, downloader: BaseDownloader, filter_kwargs: dict, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader
        self.filter_kwargs = filter_kwargs

    def run(self) -> CommandResult:
        try:
            self.progress("Applying filters...", 0)
            results = self.downloader.filter(**self.filter_kwargs)
            total = sum(len(v) for v in results.values())
            stacks = len(results)
            self.progress(f"Filter applied: {total} scenes in {stacks} stacks", 100)
            return CommandResult(
                success=True,
                message=f"Filter applied: {total} scenes in {stacks} stacks",
                data=results,
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class DownloadScenesCommand(BaseCommand):
    """Wraps downloader.download() with forwarded keyword arguments."""

    def __init__(self, downloader: BaseDownloader, progress_callback=None, **download_kwargs):
        super().__init__(progress_callback)
        self.downloader = downloader
        self.download_kwargs = download_kwargs

    def run(self) -> CommandResult:
        try:
            self.progress("Starting scene download...", 0)
            self.downloader.download(**self.download_kwargs)
            download_dir = getattr(self.downloader, "download_dir", None)
            self.progress("Download complete", 100)
            return CommandResult(
                success=True,
                message="Download complete",
                data=download_dir,
                output_files=[download_dir] if download_dir else [],
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class SummaryCommand(BaseCommand):
    """Wraps downloader.summary() — prints a text summary of active results."""

    def __init__(self, downloader: BaseDownloader, ls: bool = False, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader
        self.ls = ls

    def run(self) -> CommandResult:
        try:
            self.progress("Building summary...", 0)
            self.downloader.summary(ls=self.ls)
            self.progress("Done", 100)
            return CommandResult(success=True, message="Summary printed")
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class FootprintCommand(BaseCommand):
    """Wraps downloader.footprint() — renders or saves the scene footprint map."""

    def __init__(self, downloader: BaseDownloader, save_path: str | None = None, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader
        self.save_path = save_path

    def run(self) -> CommandResult:
        try:
            self.progress("Rendering footprint map...", 0)
            self.downloader.footprint(save_path=self.save_path)
            self.progress("Done", 100)
            msg = f"Footprint saved to {self.save_path}" if self.save_path else "Footprint displayed"
            return CommandResult(
                success=True,
                message=msg,
                output_files=[self.save_path] if self.save_path else [],
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class ResetCommand(BaseCommand):
    """Wraps downloader.reset() — clears the active filter subset."""

    def __init__(self, downloader: BaseDownloader, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader

    def run(self) -> CommandResult:
        try:
            self.downloader.reset()
            return CommandResult(success=True, message="Filter reset — showing all results")
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class DEMCommand(BaseCommand):
    """
    Wraps downloader.dem() — downloads a DEM for the active search footprint.

    Only works for downloaders that implement dem() (e.g. ASF_Base_Downloader
    and its subclasses). Gracefully fails for other downloader types.
    """

    def __init__(self, downloader: BaseDownloader, save_path: str | None = None, progress_callback=None):
        super().__init__(progress_callback)
        self.downloader = downloader
        self.save_path = save_path

    def run(self) -> CommandResult:
        if not hasattr(self.downloader, "dem"):
            return CommandResult(
                success=False,
                message=f"{type(self.downloader).__name__} does not support dem()",
                errors=[f"{type(self.downloader).__name__} has no dem() method"],
            )
        try:
            self.progress("Downloading DEM...", 0)
            self.downloader.dem(save_path=self.save_path)
            self.progress("DEM download complete", 100)
            return CommandResult(success=True, message="DEM download complete")
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])
