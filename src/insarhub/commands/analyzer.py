# -*- coding: utf-8 -*-
from insarhub.core.base import BaseAnalyzer
from .base import BaseCommand, CommandResult


class PrepDataCommand(BaseCommand):
    """
    Wraps analyzer.prep_data() — unzips HyP3 products, collects files,
    clips rasters to common overlap, and sets MintPy load parameters.

    Only applies to analyzers that implement prep_data()
    (e.g. Hyp3_SBAS). Gracefully fails for other analyzer types.
    """

    def __init__(self, analyzer: BaseAnalyzer, progress_callback=None):
        super().__init__(progress_callback)
        self.analyzer = analyzer

    def run(self) -> CommandResult:
        if not hasattr(self.analyzer, "prep_data"):
            return CommandResult(
                success=False,
                message=f"{type(self.analyzer).__name__} does not support prep_data()",
                errors=[f"{type(self.analyzer).__name__} has no prep_data() method"],
            )
        try:
            self.progress("Preparing HyP3 data for MintPy...", 0)
            self.analyzer.prep_data()
            self.progress("Data preparation complete", 100)
            return CommandResult(success=True, message="Data preparation complete")
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])


class AnalyzeCommand(BaseCommand):
    """Wraps analyzer.run() — executes the MintPy SBAS time-series workflow."""

    def __init__(self, analyzer: BaseAnalyzer, steps: list[str] | None = None, progress_callback=None):
        super().__init__(progress_callback)
        self.analyzer = analyzer
        self.steps = steps

    def run(self) -> CommandResult:
        try:
            self.progress("Running MintPy time-series analysis...", 0)
            self.analyzer.run(self.steps)
            self.progress("Analysis complete", 100)
            return CommandResult(success=True, message="Analysis complete")
        except Exception as e:
            return CommandResult(success=False, message=str(e), errors=[str(e)])
