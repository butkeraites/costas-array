"""Dependency-free terminal progress bar with ETA.

Designed for long-running shard campaigns: shows a live bar with percentage,
elapsed time, ETA (extrapolated from observed throughput), rate, and arbitrary
live fields (e.g. found/unsat/unknown counts). Renders with carriage returns on
a TTY; on a non-TTY (piped/captured output) it prints periodic status lines
instead so logs stay readable.
"""
from __future__ import annotations

import sys
import time


def format_duration(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # negative or NaN
        return "--:--:--"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}"


class ProgressBar:
    def __init__(
        self,
        total: int,
        *,
        stream=None,
        enabled: bool | None = None,
        width: int = 28,
        label: str = "",
        min_interval: float = 0.1,
        non_tty_interval: float = 30.0,
        show_rate: bool = True,
    ) -> None:
        self.total = max(0, total)
        self.done = 0
        self.stream = stream if stream is not None else sys.stderr
        self.is_tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.enabled = self.is_tty if enabled is None else enabled
        self.width = width
        self.label = label
        self.min_interval = min_interval
        self.non_tty_interval = non_tty_interval
        self.show_rate = show_rate
        self.fields: dict[str, object] = {}
        self.start = time.time()
        self._last_render = 0.0
        self._last_line_len = 0

    def update(self, *, done: int | None = None, inc: int = 1, **fields) -> None:
        self.done = done if done is not None else self.done + inc
        if fields:
            self.fields.update(fields)
        self._render(final=False)

    def _line(self) -> str:
        elapsed = time.time() - self.start
        frac = self.done / self.total if self.total else 1.0
        rate = self.done / elapsed if elapsed > 0 else 0.0
        eta = (self.total - self.done) / rate if rate > 0 else float("nan")
        filled = int(round(self.width * frac))
        bar = "#" * filled + "-" * (self.width - filled)
        extra = "  ".join(f"{k}={v}" for k, v in self.fields.items())
        prefix = f"{self.label} " if self.label else ""
        rate_str = ""
        if self.show_rate:
            rate_str = f"  {rate * 60:.1f}/min" if rate > 0 else "  --/min"
        return (
            f"{prefix}[{bar}] {self.done}/{self.total} {frac * 100:5.1f}%  "
            f"elapsed {format_duration(elapsed)}  ETA {format_duration(eta)}"
            f"{rate_str}" + (f"  {extra}" if extra else "")
        )

    def _render(self, *, final: bool) -> None:
        if not self.enabled:
            return
        now = time.time()
        if self.is_tty:
            if not final and now - self._last_render < self.min_interval:
                return
            line = self._line()
            pad = max(0, self._last_line_len - len(line))
            self.stream.write("\r" + line + " " * pad)
            if final:
                self.stream.write("\n")
            self.stream.flush()
            self._last_line_len = len(line)
        else:
            if not final and now - self._last_render < self.non_tty_interval:
                return
            self.stream.write(self._line() + "\n")
            self.stream.flush()
        self._last_render = now

    def close(self) -> None:
        self._render(final=True)

    def __enter__(self) -> "ProgressBar":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
