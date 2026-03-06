from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class CommandResult:
    """Unified result returned by every command, consumed by both CLI and frontend."""
    success: bool
    message: str
    data: Any = None
    errors: list[str] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)


class BaseCommand:
    """
    All commands inherit from this.
    - CLI calls .run() directly, captures CommandResult
    - Frontend calls .run() in a thread, updates widgets via callbacks
    """

    def __init__(self, progress_callback: Optional[Callable[[str, int], None]] = None):
        # progress_callback(message, percent) — Panel widgets or tqdm use this
        self.progress_callback = progress_callback or self._default_progress

    def _default_progress(self, message: str, percent: int):
        """CLI fallback: just log."""
        logger.info(f"[{percent:3d}%] {message}")

    def progress(self, message: str, percent: int):
        self.progress_callback(message, percent)

    def run(self) -> CommandResult:
        raise NotImplementedError