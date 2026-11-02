from __future__ import annotations

import sys
import time
from typing import Optional


class ProgressTracker:
    """POSIX-compliant CLI progress indicator for terminal and file redirection."""

    def __init__(
        self,
        task_name: str,
        total: int,
        enabled: Optional[bool] = None,
        stream=sys.stderr,
    ):
        self.task_name = task_name
        self.total = max(1, total)
        self.stream = stream
        self.start_time = time.time()
        self.last_update_time = 0.0

        # Enable interactive carriage-return updates if explicitly requested or stream is a tty
        if enabled is None:
            self.interactive = getattr(self.stream, "isatty", lambda: False)()
        else:
            self.interactive = enabled

    def update(self, current: int, item_info: str = "") -> None:
        """Update and display progress indicator."""
        now = time.time()
        # Limit update frequency for interactive TTY to 10 Hz (every 0.1s)
        if self.interactive and (now - self.last_update_time < 0.1) and current < self.total:
            return

        self.last_update_time = now
        elapsed = now - self.start_time
        pct = min(100.0, (current / self.total) * 100)
        rate = current / elapsed if elapsed > 0 else 0.0
        remaining_sec = (self.total - current) / rate if rate > 0 else 0

        # Format ETA as HH:MM:SS
        eta_str = time.strftime("%H:%M:%S", time.gmtime(max(0, remaining_sec)))

        if self.interactive:
            # Interactive Terminal: Overwrite line using carriage return \r
            bar_width = 20
            filled = int(bar_width * current // self.total)
            bar = "=" * filled + (">" if filled < bar_width else "") + " " * (bar_width - filled - 1)
            line = f"\r[{self.task_name}] {current}/{self.total} ({pct:5.1f}%) [{bar}] {rate:3.1f}/s ETA: {eta_str} {item_info[:20]}"
            self.stream.write(line.ljust(80)[:80])
            self.stream.flush()
        else:
            # File Redirection (!isatty): Output discrete status lines periodically (every 10% or at end)
            if current == self.total or (current % max(1, self.total // 10) == 0):
                line = f"[{self.task_name}] Progress: {current}/{self.total} ({pct:.1f}%) - Rate: {rate:.1f} items/s - ETA: {eta_str}\n"
                self.stream.write(line)
                self.stream.flush()

    def finish(self, message: str = "") -> None:
        """Complete progress tracking and finalize line."""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

        if self.interactive:
            self.stream.write(f"\r[{self.task_name}] Completed in {elapsed_str}. {message}".ljust(80) + "\n")
            self.stream.flush()
        else:
            self.stream.write(f"[{self.task_name}] Finished in {elapsed_str}. {message}\n")
            self.stream.flush()
