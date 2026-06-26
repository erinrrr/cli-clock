#!/usr/bin/env python3
"""
CLI Digital Clock — Terminal clock with Pomodoro, stopwatch, and countdown timer.

Architecture overview
---------------------
ClockConfig   – Frozen dataclass; single source of truth for display settings.
Colors        – ANSI SGR constants (not a class you ever instantiate).
SEGMENTS*     – Pure data; glyph tables are module-level constants, not re-created per call.
TimerState    – Encapsulates ALL pause/resume/elapsed logic in one place.
ResizeWatcher – Owns the SIGWINCH signal and exposes a clean polling API.
Terminal      – Stateless static helpers for low-level I/O (no subprocess).
InputHandler  – Context manager for raw-mode keyboard input.
Renderer      – Composable rendering primitives; queries terminal size once per frame.
Mode functions– Thin orchestrators; contain no timer math and no rendering primitives.
main()        – Parses args, validates eagerly, dispatches to a mode.
"""

import os
import sys
import signal
import select
import termios
import tty
import time
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Platform guard — checked in main(), NOT at import time.
# Importing this module for unit-testing on any platform is therefore safe.
# ---------------------------------------------------------------------------
_UNIX_SYSTEM: bool = (os.name == "posix")


# ---------------------------------------------------------------------------
# ANSI color constants
# ---------------------------------------------------------------------------
class Colors:
    """ANSI SGR color escape codes.

    Kept as a plain class of string constants rather than StrEnum so that
    the strings can be concatenated directly into f-strings without an
    explicit .value access.  The class is intentionally never instantiated.
    """
    RESET   = "\033[0m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    GRAY    = "\033[90m"
    WHITE   = "\033[97m"
    BLACK   = "\033[30m"


# ---------------------------------------------------------------------------
# ASCII-art glyph tables — module-level constants, allocated once.
# ---------------------------------------------------------------------------
_GLYPH_ROWS = 4  # Every character is exactly 4 rows tall.

SEGMENTS: dict = {
    "0": ["┌───┐", "│   │", "│   │", "└───┘"],
    "1": ["    ┐", "    │", "    │", "    ┴"],
    "2": ["┌───┐", "    │", "┌───┘", "└───┘"],
    "3": ["┌───┐", "    │", "  ──┤", "└───┘"],
    "4": ["┐   ┐", "└───┤", "    │", "    ┘"],
    "5": ["┌───┐", "└───┐", "┌   │", "└───┘"],
    "6": ["┌───┐", "├───┐", "│   │", "└───┘"],
    "7": ["┌───┐", "    │", "    │", "    ┘"],
    "8": ["┌───┐", "├───┤", "│   │", "└───┘"],
    "9": ["┌───┐", "└───┤", "    │", "    ┘"],
    ":": [" ", "●", "●", " "],
    " ": ["     ", "     ", "     ", "     "],
}

SEGMENTS_BOLD: dict = {
    "0": ["╔═════╗", "║     ║", "║     ║", "╚═════╝"],
    "1": ["      ║", "      ║", "      ║", "      ║"],
    "2": ["╔═════╗", "      ║", "╔═════╝", "╚═════╝"],
    "3": ["╔═════╗", "      ║", " ═════╣", "╚═════╝"],
    "4": ["╗     ║", "║     ║", "╚═════╣", "      ║"],
    "5": ["╔═════╗", "║      ", "╚═════╗", "╚═════╝"],
    "6": ["╔═════╗", "║      ", "╠═════╗", "╚═════╝"],
    "7": ["╔═════╗", "      ║", "      ║", "      ║"],
    "8": ["╔═════╗", "║     ║", "╠═════╣", "╚═════╝"],
    "9": ["╔═════╗", "║     ║", "╚═════╣", "╚═════╝"],
    ":": [" ", "●", "●", " "],
    " ": ["       ", "       ", "       ", "       "],
}

# Progress-bar sizing limits (characters)
_MIN_BAR_LEN = 20
_MAX_BAR_LEN = 100
_BAR_SUFFIX   = 9   # len(" 100.0%]") + len("[") exactly

# Render tick interval (seconds)
_TICK = 0.1


# ---------------------------------------------------------------------------
# Configuration — frozen so it can be passed around without defensive copies.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClockConfig:
    """Immutable display configuration.

    Frozen prevents accidental mutation after construction and makes the
    object hashable, enabling use as a dict key or set element if needed.
    """
    focus:        bool = False
    bold:         bool = False
    white:        bool = False
    black:        bool = False
    bell_enabled: bool = False

    def resolve_color(self, default: str) -> str:
        """Return the effective ANSI code, honouring any global override."""
        if self.white:
            return Colors.WHITE
        if self.black:
            return Colors.BLACK
        return default


# ---------------------------------------------------------------------------
# Timer state — the ONLY place that owns pause/resume/elapsed arithmetic.
#
# Previously, the pause/resume pattern (paused flag, pause_start, start_time
# adjustment) was copy-pasted verbatim into stopwatch_mode, countdown_timer,
# and pomodoro_mode — three independent implementations of the same FSM.
# Any bug or change needed to be applied three times.  This class fixes that.
# ---------------------------------------------------------------------------
class TimerState:
    """Thread-unsafe but re-entrant timer with pause/resume support.

    Uses time.monotonic() to avoid drift from wall-clock adjustments (NTP,
    DST, etc.).  elapsed_seconds is always a non-negative integer.
    """

    def __init__(self) -> None:
        self._start:       float = time.monotonic()
        self._elapsed:     float = 0.0
        self._paused:      bool  = False
        self._pause_start: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def elapsed_seconds(self) -> int:
        return int(self._elapsed)

    @property
    def paused(self) -> bool:
        return self._paused

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Advance elapsed time. Call once per render tick."""
        if not self._paused:
            self._elapsed = time.monotonic() - self._start

    def toggle_pause(self) -> None:
        """Pause if running; resume if paused.

        On resume, shift _start forward by the duration of the pause so
        that elapsed time continues from where it stopped without a jump.
        """
        if self._paused:
            self._start += time.monotonic() - self._pause_start
            self._paused = False
        else:
            self._pause_start = time.monotonic()
            self._paused = True

    def reset(self) -> None:
        """Restart elapsed time from zero (used by stopwatch reset key)."""
        self._start   = time.monotonic()
        self._elapsed = 0.0
        self._paused  = False


# ---------------------------------------------------------------------------
# Terminal — low-level I/O, zero instance state, no subprocess spawning.
# ---------------------------------------------------------------------------
class Terminal:
    """Static helpers for terminal control sequences.

    All methods write raw ANSI/VT100 escape sequences directly to stdout.
    Using os.system('clear') (original code) spawns a child process just to
    write two bytes — this is ~100× slower and unnecessary.
    """

    @staticmethod
    def size() -> Tuple[int, int]:
        """Return (columns, rows). Falls back to (80, 24) on any error."""
        try:
            s = os.get_terminal_size()
            return s.columns, s.lines
        except OSError:
            return 80, 24

    @staticmethod
    def clear() -> None:
        """Erase the entire screen and move cursor to the home position."""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    @staticmethod
    def cursor_home() -> None:
        """Move cursor to (1,1) without erasing — used for in-place redraws."""
        sys.stdout.write("\033[H")

    @staticmethod
    def hide_cursor() -> None:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    @staticmethod
    def show_cursor() -> None:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    @staticmethod
    def ring_bell(times: int = 3, interval: float = 0.15) -> None:
        """Emit BEL characters spaced apart to defeat terminal rate-limiting.

        Most modern terminal emulators ship with the audible bell disabled;
        they display a visual flash instead.  The spacing avoids coalescing.
        """
        for _ in range(times):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(interval)


# ---------------------------------------------------------------------------
# InputHandler — raw-mode keyboard; always used as a context manager.
# ---------------------------------------------------------------------------
class InputHandler:
    """Non-blocking keyboard reader in raw/cbreak mode.

    Deliberately requires the `with` statement — it is impossible to
    construct one and forget to restore terminal settings.

    Usage::
        with InputHandler() as kbd:
            key = kbd.get_key()   # str | None
    """

    def __init__(self) -> None:
        self._fd:    int  = sys.stdin.fileno()
        # Capture settings before we touch anything so __exit__ can
        # restore exactly the state we inherited from the shell.
        self._saved: list = termios.tcgetattr(self._fd)

    def __enter__(self) -> "InputHandler":
        # cbreak: signals (Ctrl-C) still delivered; characters available
        # immediately without waiting for newline.
        tty.setcbreak(self._fd)
        # Separately disable echo so typed characters don't appear on screen.
        attrs = termios.tcgetattr(self._fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self._fd, termios.TCSADRAIN, attrs)
        Terminal.hide_cursor()
        return self

    def __exit__(self, *_) -> None:
        # Unconditional restore — runs even if an exception propagates.
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        Terminal.show_cursor()

    def get_key(self) -> Optional[str]:
        """Return the next keypress character, or None if no input is waiting."""
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        return sys.stdin.read(1) if ready else None


# ---------------------------------------------------------------------------
# ResizeWatcher — encapsulates SIGWINCH so global state is not scattered.
#
# The original code used a bare module-level boolean and `global` keywords
# inside every single mode function.  This class makes the signal's effects
# observable through a clean polling interface and ensures the handler is
# registered in exactly one place.
# ---------------------------------------------------------------------------
class ResizeWatcher:
    """Polls for SIGWINCH (terminal resize) events."""

    def __init__(self) -> None:
        self._dirty = False
        if _UNIX_SYSTEM:
            signal.signal(signal.SIGWINCH, self._on_resize)

    def _on_resize(self, _signum: int, _frame: object) -> None:
        self._dirty = True

    def check_and_clear(self) -> bool:
        """Return True if a resize happened since the last call, then reset."""
        was_dirty, self._dirty = self._dirty, False
        return was_dirty


# ---------------------------------------------------------------------------
# Renderer — pure display logic; no timer state, no control flow.
#
# Key design decisions:
#   1. Terminal size is queried ONCE per public method call and passed to
#      every private helper — avoids multiple syscalls per frame.
#   2. All writes go through sys.stdout.write(); a single flush() closes
#      each frame — reduces write syscall count.
#   3. String rows built with join() instead of += to stay O(n), not O(n²).
# ---------------------------------------------------------------------------
class Renderer:
    """Composable display primitives for each clock mode."""

    def __init__(self, config: ClockConfig) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public composite frames  (one per mode)
    # ------------------------------------------------------------------

    def clock_frame(self, time_str: str, date_str: str) -> None:
        cols, rows = Terminal.size()
        Terminal.cursor_home()
        self._digits(time_str, Colors.CYAN, cols, rows)
        if not self._cfg.focus:
            self._label(date_str, Colors.MAGENTA, cols)
        sys.stdout.flush()

    def stopwatch_frame(self, time_str: str, paused: bool) -> None:
        cols, rows = Terminal.size()
        Terminal.cursor_home()
        self._digits(time_str, Colors.BLUE, cols, rows)
        if not self._cfg.focus:
            text = (
                "⏸ Paused (q: resume, r: reset)"
                if paused
                else "▶ Running (q: pause, r: reset)"
            )
            self._label(text, Colors.MAGENTA, cols)
        elif paused:
            self._label("⏸ Paused", Colors.GRAY, cols)
        else:
            self._blank_line()
        sys.stdout.flush()

    def timer_frame(
        self,
        time_str: str,
        label: str,
        color: str,
        progress: float,
        paused: bool,
    ) -> None:
        cols, rows = Terminal.size()
        Terminal.cursor_home()
        self._digits(time_str, color, cols, rows)

        # Build the status line once, reusing focus logic in one branch.
        if not self._cfg.focus:
            status = f"⏸ Paused — {label}" if paused else f"▶ {label}"
            self._label(status, Colors.MAGENTA, cols)
        elif paused:
            self._label("⏸ Paused", Colors.GRAY, cols)
        else:
            self._blank_line()

        bar_color = color if not self._cfg.focus else Colors.GRAY
        self._progress_bar(progress, bar_color, cols, rows)
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Private rendering primitives
    # ------------------------------------------------------------------

    def _digits(self, text: str, color: str, cols: int, rows: int) -> None:
        """Render text as large ASCII-art digits."""
        effective = self._cfg.resolve_color(color)

        if cols < 50 or rows < 15:
            # Terminal too small for art — fall back to plain inline text.
            sys.stdout.write(f"\033[2K\r{effective}{text}{Colors.RESET}\n")
            sys.stdout.write("\033[J")  # Erase stale art below
            return

        table = SEGMENTS_BOLD if self._cfg.bold else SEGMENTS

        # Build every glyph row with join() — O(n) vs the original's O(n²)
        # string concatenation inside a loop.
        glyph_rows = [
            " ".join(table.get(ch, table[" "])[row] for ch in text)
            for row in range(_GLYPH_ROWS)
        ]

        sys.stdout.write("\n")
        for row_text in glyph_rows:
            pad = max(0, (cols - len(row_text)) // 2)
            sys.stdout.write(
                f"\033[2K\r{' ' * pad}{effective}{row_text}{Colors.RESET}\n"
            )
        sys.stdout.write("\n")

    def _label(self, text: str, color: str, cols: int) -> None:
        effective = self._cfg.resolve_color(color)
        pad = max(0, (cols - len(text)) // 2)
        sys.stdout.write(
            f"\033[2K\r{' ' * pad}{effective}{text}{Colors.RESET}\n\n"
        )

    def _progress_bar(
        self, progress: float, color: str, cols: int, rows: int
    ) -> None:
        effective = self._cfg.resolve_color(color)
        clamped   = max(0.0, min(1.0, progress))

        if cols < 35 or rows < 8:
            pct = f"{clamped * 100:.1f}%"
            pad = max(0, (cols - len(pct)) // 2)
            sys.stdout.write(f"\033[2K\r{' ' * pad}{pct}\n")
            return

        bar_len = max(_MIN_BAR_LEN, min(_MAX_BAR_LEN, cols - _BAR_SUFFIX - 2))
        filled  = int(bar_len * clamped)
        bar     = "█" * filled + "░" * (bar_len - filled)
        pad     = max(0, (cols - bar_len - _BAR_SUFFIX) // 2)

        sys.stdout.write(
            f"\033[2K\r{' ' * pad}"
            f"[{effective}{bar}{Colors.RESET}] {clamped * 100:.1f}%\n"
        )
        sys.stdout.write("\033[K\n")  # Erase the line below to remove artifacts

    @staticmethod
    def _blank_line() -> None:
        sys.stdout.write("\033[2K\r\n")


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------
def format_seconds(total: int) -> str:
    """Convert non-negative seconds to HH:MM:SS or MM:SS display string."""
    total = max(0, total)
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_duration(value: str) -> int:
    """Parse a duration string into a total number of seconds.

    Accepted formats:
      "90"        → 90 seconds
      "10:30"     → 10 min 30 sec  (MM:SS)
      "1:30:00"   → 1 hr 30 min    (HH:MM:SS)

    Raises:
        ValueError: on any invalid format, negative component, or
                    out-of-range seconds/minutes (≥ 60).
    """
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"Expected 1–3 colon-separated parts, got {value!r}")

    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"Non-integer component in {value!r}")

    if any(n < 0 for n in nums):
        raise ValueError("Duration components must be non-negative")

    # Validate sub-components are in range for their position.
    if len(nums) >= 2 and nums[-1] >= 60:
        raise ValueError(f"Seconds value {nums[-1]} must be < 60")
    if len(nums) == 3 and nums[1] >= 60:
        raise ValueError(f"Minutes value {nums[1]} must be < 60")

    multipliers = {1: (1,), 2: (60, 1), 3: (3600, 60, 1)}
    total = sum(n * m for n, m in zip(nums, multipliers[len(nums)]))

    if total > 99 * 3600:
        raise ValueError(f"Duration {value!r} exceeds the 99-hour maximum")

    return total


# ---------------------------------------------------------------------------
# Mode orchestrators — thin; contain no rendering primitives or timer math.
# ---------------------------------------------------------------------------

def clock_mode(config: ClockConfig, watcher: ResizeWatcher) -> None:
    """Display current wall time, refreshing every tick.  Press q to quit."""
    Terminal.clear()
    renderer = Renderer(config)

    with InputHandler() as kbd:
        try:
            while True:
                if watcher.check_and_clear():
                    Terminal.clear()
                if kbd.get_key() == "q":
                    break

                now = datetime.now()
                renderer.clock_frame(
                    now.strftime("%H:%M:%S"),
                    now.strftime("%A, %B %d, %Y"),
                )
                time.sleep(_TICK)
        except KeyboardInterrupt:
            pass


def stopwatch_mode(config: ClockConfig, watcher: ResizeWatcher) -> None:
    """Count-up timer.  q = pause/resume, r = reset."""
    Terminal.clear()
    renderer = Renderer(config)
    state    = TimerState()

    with InputHandler() as kbd:
        try:
            while True:
                if watcher.check_and_clear():
                    Terminal.clear()

                key = kbd.get_key()
                if key == "q":
                    state.toggle_pause()
                elif key == "r":
                    state.reset()

                state.update()
                renderer.stopwatch_frame(
                    format_seconds(state.elapsed_seconds), state.paused
                )
                time.sleep(_TICK)
        except KeyboardInterrupt:
            pass


def _countdown_session(
    total_seconds: int,
    label: str,
    color: str,
    config: ClockConfig,
    watcher: ResizeWatcher,
    kbd: InputHandler,
) -> bool:
    """Run one countdown.  Returns True if interrupted by Ctrl-C.

    Separated from timer_mode so that pomodoro_mode can share a single
    InputHandler across multiple alternating sessions without tearing down
    and rebuilding the raw-mode terminal state between sessions.
    """
    renderer = Renderer(config)
    state    = TimerState()

    try:
        while True:
            if watcher.check_and_clear():
                Terminal.clear()

            if kbd.get_key() == "q":
                state.toggle_pause()

            state.update()
            remaining = max(0, total_seconds - state.elapsed_seconds)
            progress  = (
                (total_seconds - remaining) / total_seconds
                if total_seconds > 0
                else 1.0
            )

            renderer.timer_frame(
                format_seconds(remaining), label, color, progress, state.paused
            )

            if remaining <= 0 and not state.paused:
                return False  # Completed normally

            time.sleep(_TICK)

    except KeyboardInterrupt:
        return True  # User pressed Ctrl-C


def timer_mode(
    total_seconds: int,
    config: ClockConfig,
    watcher: ResizeWatcher,
) -> None:
    """Single countdown timer session."""
    Terminal.clear()
    with InputHandler() as kbd:
        interrupted = _countdown_session(
            total_seconds, "Countdown Timer", Colors.YELLOW, config, watcher, kbd
        )
    if config.bell_enabled and not interrupted:
        Terminal.ring_bell()


def pomodoro_mode(
    work_minutes: int,
    break_minutes: int,
    config: ClockConfig,
    watcher: ResizeWatcher,
) -> None:
    """Alternating work/break Pomodoro sessions.

    A single InputHandler spans all sessions so that raw-mode terminal
    state is set up and torn down exactly once.
    """
    with InputHandler() as kbd:
        session = 1
        try:
            while True:
                Terminal.clear()
                interrupted = _countdown_session(
                    work_minutes * 60,
                    f"Session {session} — Work",
                    Colors.RED,
                    config,
                    watcher,
                    kbd,
                )
                if interrupted:
                    break
                if config.bell_enabled:
                    Terminal.ring_bell()
                time.sleep(2)

                Terminal.clear()
                interrupted = _countdown_session(
                    break_minutes * 60,
                    f"Session {session} — Break",
                    Colors.GREEN,
                    config,
                    watcher,
                    kbd,
                )
                if interrupted:
                    break
                if config.bell_enabled:
                    Terminal.ring_bell()
                time.sleep(2)

                session += 1

        except KeyboardInterrupt:
            pass


# ---------------------------------------------------------------------------
# Argument parser — built once, reused across all call sites.
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clock.py",
        description="Terminal digital clock with Pomodoro, stopwatch, and countdown timer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                  Show current time and date
  %(prog)s -b               Bold numbers
  %(prog)s -f               Focus mode (minimal display)
  %(prog)s -s               Stopwatch
  %(prog)s -t 10:30         10 min 30 sec countdown
  %(prog)s -p 25,5          Pomodoro (25 min work, 5 min break)
  %(prog)s -fb -s           Focus + bold stopwatch
  %(prog)s --white -t 5:00  White text 5-minute timer

timer formats:
  90        90 seconds
  10:30     10 minutes 30 seconds
  1:30:00   1 hour 30 minutes

controls:
  q         Pause / resume
  r         Reset (stopwatch only)
  Ctrl-C    Exit
        """,
    )

    style = parser.add_argument_group("display style")
    style.add_argument("-f", "--focus", action="store_true",
                       help="minimal display without labels")
    style.add_argument("-b", "--bold",  action="store_true",
                       help="use bold/thick number style")

    # argparse enforces mutual exclusivity at parse time — no manual check needed.
    color_grp = style.add_mutually_exclusive_group()
    color_grp.add_argument("--white", action="store_true", help="force all text white")
    color_grp.add_argument("--black", action="store_true", help="force all text black")

    parser.add_argument(
        "--bell", action="store_true",
        help="enable terminal bell on completion (off by default)",
    )

    # Mode flags are also mutually exclusive.
    mode_grp = parser.add_mutually_exclusive_group()
    mode_grp.add_argument("-p", "--pomodoro", metavar="W,B",
                          help="Pomodoro: work,break minutes (e.g. 25,5)")
    mode_grp.add_argument("-s", "--stopwatch", action="store_true",
                          help="count-up stopwatch")
    mode_grp.add_argument("-t", "--timer", metavar="TIME",
                          help="countdown timer (MM:SS, HH:MM:SS, or seconds)")
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    # Platform check lives here, not at import time, so this module can be
    # imported freely on any OS (e.g., for unit testing).
    if not _UNIX_SYSTEM:
        sys.exit("Error: a POSIX/Unix system (Linux or macOS) is required")

    parser  = _build_parser()
    args    = parser.parse_args()
    config  = ClockConfig(
        focus        = args.focus,
        bold         = args.bold,
        white        = args.white,
        black        = args.black,
        bell_enabled = args.bell,
    )
    watcher = ResizeWatcher()

    try:
        if args.pomodoro:
            # Validate eagerly here so the user sees a tidy argparse-style error
            # before we touch the terminal.
            parts = args.pomodoro.split(",")
            if len(parts) != 2:
                parser.error("--pomodoro expects exactly two integers: W,B (e.g. 25,5)")
            try:
                work_min, break_min = int(parts[0]), int(parts[1])
            except ValueError:
                parser.error("--pomodoro: both values must be integers")
            if work_min <= 0 or break_min <= 0:
                parser.error("--pomodoro: both values must be positive")
            pomodoro_mode(work_min, break_min, config, watcher)

        elif args.stopwatch:
            stopwatch_mode(config, watcher)

        elif args.timer:
            try:
                total = parse_duration(args.timer)
            except ValueError as exc:
                parser.error(f"--timer: {exc}")
            if total <= 0:
                parser.error("--timer: duration must be greater than zero")
            timer_mode(total, config, watcher)

        else:
            clock_mode(config, watcher)

    except KeyboardInterrupt:
        pass
    finally:
        # Unconditionally restore cursor visibility.  This fires even on
        # unexpected exceptions so the user is never left with a hidden cursor.
        Terminal.show_cursor()
        print()  # Move past the last clock line


if __name__ == "__main__":
    main()