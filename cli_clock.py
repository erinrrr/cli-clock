#!/usr/bin/env python3
"""
CLI Digital Clock - A terminal-based clock with timer features.

Displays time using ASCII art digits with support for Pomodoro technique,
stopwatch, countdown timers, and customizable display modes.
"""

import sys
import time
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

try:
    import os
    import termios
    import tty
    import select
    UNIX_SYSTEM = True
except ImportError:
    UNIX_SYSTEM = False
    print("Error: Unix-like system (Linux, macOS) required")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    BLACK = '\033[30m'


@dataclass
class ClockConfig:
    """Configuration for clock display and behavior.
    
    Attributes:
        focus: Minimal display without labels
        bold: Use thick/bold number segments
        white: Override all colors to white
        black: Override all colors to black
        bell_enabled: Enable terminal bell on timer completion
    """
    focus: bool = False
    bold: bool = False
    white: bool = False
    black: bool = False
    bell_enabled: bool = True
    
    def get_color(self, default_color: str) -> str:
        """Return color based on override settings or default."""
        if self.white:
            return Colors.WHITE
        if self.black:
            return Colors.BLACK
        return default_color


# ASCII art segments for regular numbers
SEGMENTS = {
    '0': ["┌───┐", "│   │", "│   │", "└───┘"],
    '1': ["    ┐", "    │", "    │", "    ┴"],
    '2': ["┌───┐", "    │", "┌───┘", "└───┘"],
    '3': ["┌───┐", "    │", "  ──┤", "└───┘"],
    '4': ["┐   ┐", "└───┤", "    │", "    ┘"],
    '5': ["┌───┐", "└───┐", "┌   │", "└───┘"],
    '6': ["┌───┐", "├───┐", "│   │", "└───┘"],
    '7': ["┌───┐", "    │", "    │", "    ┘"],
    '8': ["┌───┐", "├───┤", "│   │", "└───┘"],
    '9': ["┌───┐", "└───┤", "    │", "    ┘"],
    ':': [" ", "●", "●", " "],
    ' ': ["     ", "     ", "     ", "     "]
}

# ASCII art segments for bold numbers
SEGMENTS_BOLD = {
    '0': ["╔═════╗", "║     ║", "║     ║", "╚═════╝"],
    '1': ["      ║", "      ║", "      ║", "      ║"],
    '2': ["╔═════╗", "      ║", "╔═════╝", "╚═════╝"],
    '3': ["╔═════╗", "      ║", " ═════╣", "╚═════╝"],
    '4': ["╗     ║", "║     ║", "╚═════╣", "      ║"],
    '5': ["╔═════╗", "║      ", "╚═════╗", "╚═════╝"],
    '6': ["╔═════╗", "║      ", "╠═════╗", "╚═════╝"],
    '7': ["╔═════╗", "      ║", "      ║", "      ║"],
    '8': ["╔═════╗", "║     ║", "╠═════╣", "╚═════╝"],
    '9': ["╔═════╗", "║     ║", "╚═════╣", "╚═════╝"],
    ':': [" ", "●", "●", " "],
    ' ': ["       ", "       ", "       ", "       "]
}

# Display height constants for cursor positioning
DISPLAY_LINES_TIME_ONLY = 5
DISPLAY_LINES_WITH_LABEL = 7
DISPLAY_LINES_FOCUS_WITH_BAR = 8
DISPLAY_LINES_WITH_BAR = 9
MIN_BAR_LENGTH = 20
MAX_BAR_LENGTH = 100
BAR_MARGIN = 20


class TerminalUtils:
    """Terminal manipulation utilities."""
    
    @staticmethod
    def move_up(lines: int) -> None:
        """Move cursor up n lines for display updates."""
        sys.stdout.write(f'\033[{lines}A')
    
    @staticmethod
    def clear_screen() -> None:
        """Clear entire terminal screen."""
        os.system('clear')
    
    @staticmethod
    def get_width() -> int:
        """Get current terminal width in columns."""
        try:
            return os.get_terminal_size().columns
        except Exception:
            return 80
    
    @staticmethod
    def center_padding(text_length: int) -> int:
        """Calculate padding needed to center text."""
        return max(0, (TerminalUtils.get_width() - text_length) // 2)
    
    @staticmethod
    def ring_bell() -> None:
        """Ring terminal bell (ASCII BEL character)."""
        print("\a", end='', flush=True)


class Display:
    """Handles rendering of clock displays and UI elements."""
    
    def __init__(self, config: ClockConfig):
        self.config = config
    
    def print_time(self, time_str: str, color: str = Colors.CYAN, move_back: bool = False) -> None:
        """Print time using large ASCII art digits.
        
        Args:
            time_str: Time string to display (HH:MM:SS format)
            color: ANSI color code for display
            move_back: Skip initial newline for display updates
        """
        segments = SEGMENTS_BOLD if self.config.bold else SEGMENTS
        lines = [''] * 4
        
        for char in time_str:
            if char in segments:
                for i in range(4):
                    lines[i] += segments[char][i] + ' '
        
        if not move_back:
            print()
        
        col = self.config.get_color(color)
        terminal_width = TerminalUtils.get_width()
        
        for line in lines:
            padding = max(0, (terminal_width - len(line)) // 2)
            print(f"{' ' * padding}{col}{line}{Colors.RESET}")
        print()
    
    def print_label(self, label: str, color: str = Colors.MAGENTA) -> None:
        """Print centered label text below time display."""
        terminal_width = TerminalUtils.get_width()
        col = self.config.get_color(color)
        padding = TerminalUtils.center_padding(len(label))
        print(f"\r{' ' * terminal_width}\r{' ' * padding}{col}{label}{Colors.RESET}\n")
    
    def print_progress_bar(self, progress: float, color: str = Colors.GRAY) -> None:
        """Print horizontal progress bar.
        
        Args:
            progress: Value between 0.0 and 1.0
            color: ANSI color code for filled portion
        """
        terminal_width = TerminalUtils.get_width()
        bar_length = max(MIN_BAR_LENGTH, min(MAX_BAR_LENGTH, terminal_width - BAR_MARGIN))
        bar_padding = max(0, (terminal_width - bar_length - 10) // 2)
        
        filled = int(bar_length * progress)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        bar_color = self.config.get_color(color)
        print(f"{' ' * bar_padding}[{bar_color}{bar}{Colors.RESET}] {progress * 100:.1f}%")
        print()


class InputHandler:
    """Non-blocking keyboard input handler for timer controls."""
    
    def __init__(self):
        if not UNIX_SYSTEM:
            raise RuntimeError("InputHandler requires Unix-like system")
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
    
    def __enter__(self):
        """Set terminal to cbreak mode with no echo."""
        tty.setcbreak(self.fd)
        attr = termios.tcgetattr(self.fd)
        attr[3] = attr[3] & ~termios.ECHO
        termios.tcsetattr(self.fd, termios.TCSADRAIN, attr)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original terminal settings."""
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
    
    def get_key(self) -> Optional[str]:
        """Check for key press without blocking.
        
        Returns:
            Character if key pressed, None otherwise
        """
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None


def format_time(seconds: int) -> str:
    """Convert seconds to HH:MM:SS or MM:SS display format."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def parse_duration(duration_str: str) -> int:
    """Parse time string to seconds.
    
    Args:
        duration_str: Time in format MM:SS, HH:MM:SS, or plain seconds
        
    Returns:
        Total seconds
        
    Raises:
        ValueError: If format is invalid
    """
    parts = duration_str.split(':')
    
    try:
        if len(parts) == 1:
            return int(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            raise ValueError("Invalid format")
    except (ValueError, IndexError):
        raise ValueError("Duration must be in format: MM:SS, HH:MM:SS, or seconds")


def clock_mode(config: ClockConfig) -> None:
    """Display current time, updating every second."""
    TerminalUtils.clear_screen()
    display = Display(config)
    
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %B %d, %Y")
    
    display.print_time(time_str, Colors.CYAN)
    if not config.focus:
        display.print_label(date_str)
    
    lines_to_move = DISPLAY_LINES_WITH_LABEL if not config.focus else DISPLAY_LINES_TIME_ONLY
    
    try:
        while True:
            time.sleep(1)
            now = datetime.now()
            time_str = now.strftime("%H:%M:%S")
            date_str = now.strftime("%A, %B %d, %Y")
            
            TerminalUtils.move_up(lines_to_move)
            display.print_time(time_str, Colors.CYAN, move_back=True)
            if not config.focus:
                display.print_label(date_str)
    except KeyboardInterrupt:
        print()


def stopwatch_mode(config: ClockConfig) -> None:
    """Count-up timer with pause/resume/reset controls."""
    TerminalUtils.clear_screen()
    display = Display(config)
    
    with InputHandler() as input_handler:
        start_time = time.time()
        elapsed = 0
        paused = False
        pause_start = 0
        first_iteration = True
        
        lines_to_move = DISPLAY_LINES_WITH_LABEL
        
        try:
            while True:
                key = input_handler.get_key()
                
                if key == 'q':
                    paused = not paused
                    if paused:
                        pause_start = time.time()
                    else:
                        start_time += (time.time() - pause_start)
                
                elif key == 'r':
                    start_time = time.time()
                    elapsed = 0
                    paused = False
                
                if not paused:
                    elapsed = int(time.time() - start_time)
                
                if not first_iteration:
                    TerminalUtils.move_up(lines_to_move)
                first_iteration = False
                
                display.print_time(format_time(elapsed), Colors.BLUE, move_back=True)
                
                if not config.focus:
                    label = "⏸ Paused (q: resume, r: reset)" if paused else "▶ Running (q: pause, r: reset)"
                    display.print_label(label)
                else:
                    terminal_width = TerminalUtils.get_width()
                    if paused:
                        pause_text = "⏸ Paused"
                        col = config.get_color(Colors.GRAY)
                        padding = TerminalUtils.center_padding(len(pause_text))
                        print(f"{' ' * padding}{col}{pause_text}{Colors.RESET}\n")
                    else:
                        print()
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print()


def countdown_timer(total_seconds: int, label: str, color: str, config: ClockConfig, 
                   input_handler: InputHandler) -> bool:
    """Run countdown timer with pause support.
    
    Args:
        total_seconds: Duration to count down from
        label: Description text for timer
        color: ANSI color code for display
        config: Clock configuration
        input_handler: Keyboard input handler
        
    Returns:
        True if interrupted by Ctrl+C, False if completed
    """
    display = Display(config)
    remaining = total_seconds
    paused = False
    first_iteration = True
    
    lines_to_move = DISPLAY_LINES_FOCUS_WITH_BAR if config.focus else DISPLAY_LINES_WITH_BAR
    
    try:
        while remaining >= 0:
            key = input_handler.get_key()
            if key == 'q':
                paused = not paused
            
            if not first_iteration:
                time.sleep(1)
                TerminalUtils.move_up(lines_to_move)
            first_iteration = False
            
            display.print_time(format_time(remaining), color, move_back=True)
            
            if not config.focus:
                label_text = f"⏸ Paused - {label}" if paused else f"▶ {label}"
                display.print_label(label_text)
            else:
                terminal_width = TerminalUtils.get_width()
                if paused:
                    pause_text = "⏸ Paused"
                    col = config.get_color(Colors.GRAY)
                    padding = TerminalUtils.center_padding(len(pause_text))
                    print(f"\r{' ' * terminal_width}\r{' ' * padding}{col}{pause_text}{Colors.RESET}")
                else:
                    print(f"\r{' ' * terminal_width}\r")
            
            progress = (total_seconds - remaining) / total_seconds if total_seconds > 0 else 1.0
            bar_color = color if not config.focus else Colors.GRAY
            display.print_progress_bar(progress, bar_color)
            
            if not paused:
                remaining -= 1
        
        return False
    except KeyboardInterrupt:
        print()
        return True


def pomodoro_mode(work_minutes: int, break_minutes: int, config: ClockConfig) -> None:
    """Run alternating work/break Pomodoro sessions."""
    session = 1
    
    with InputHandler() as input_handler:
        try:
            while True:
                TerminalUtils.clear_screen()
                interrupted = countdown_timer(
                    work_minutes * 60,
                    f"Session {session} - Work",
                    Colors.RED,
                    config,
                    input_handler
                )
                
                if interrupted:
                    break
                
                if config.bell_enabled:
                    TerminalUtils.ring_bell()
                time.sleep(2)
                
                TerminalUtils.clear_screen()
                interrupted = countdown_timer(
                    break_minutes * 60,
                    f"Session {session} - Break",
                    Colors.GREEN,
                    config,
                    input_handler
                )
                
                if interrupted:
                    break
                
                if config.bell_enabled:
                    TerminalUtils.ring_bell()
                time.sleep(2)
                
                session += 1
                
        except KeyboardInterrupt:
            print()


def timer_mode(duration_str: str, config: ClockConfig) -> None:
    """Run single countdown timer."""
    try:
        total_seconds = parse_duration(duration_str)
    except ValueError as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        return
    
    if total_seconds <= 0:
        print(f"{Colors.RED}Error: Duration must be positive{Colors.RESET}")
        return
    
    TerminalUtils.clear_screen()
    
    with InputHandler() as input_handler:
        countdown_timer(total_seconds, "Countdown Timer", Colors.YELLOW, config, input_handler)
    
    if config.bell_enabled:
        TerminalUtils.ring_bell()


def main():
    """Parse arguments and launch appropriate clock mode."""
    parser = argparse.ArgumentParser(
        prog='clock.py',
        description='Terminal-based digital clock with timer features',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                 Show current time and date
  %(prog)s -b              Bold numbers
  %(prog)s -f              Focus mode (minimal display)
  %(prog)s -s              Stopwatch
  %(prog)s -t 10:30        10 minute 30 second timer
  %(prog)s -p 25,5         Pomodoro (25min work, 5min break)
  %(prog)s -fb -s          Focus + bold stopwatch
  %(prog)s --white -t 5:00 White text 5 minute timer

timer formats:
  90        90 seconds
  10:30     10 minutes 30 seconds
  1:30:00   1 hour 30 minutes

controls:
  q         Pause/resume
  r         Reset (stopwatch only)
  Ctrl+C    Exit
        """
    )
    
    parser.add_argument('-f', '--focus', action='store_true',
                       help='minimal display without labels')
    parser.add_argument('-b', '--bold', action='store_true',
                       help='use bold/thick number style')
    parser.add_argument('--white', action='store_true',
                       help='override colors to white')
    parser.add_argument('--black', action='store_true',
                       help='override colors to black')
    parser.add_argument('--no-bell', action='store_true',
                       help='disable completion bell sound')
    parser.add_argument('-p', '--pomodoro', metavar='W,B',
                       help='work,break minutes (e.g., 25,5)')
    parser.add_argument('-s', '--stopwatch', action='store_true',
                       help='count-up timer mode')
    parser.add_argument('-t', '--timer', metavar='TIME',
                       help='countdown timer (MM:SS, HH:MM:SS, or seconds)')
    
    args = parser.parse_args()
    
    if args.white and args.black:
        print(f"{Colors.RED}Error: --white and --black are mutually exclusive{Colors.RESET}")
        sys.exit(1)
    
    config = ClockConfig(
        focus=args.focus,
        bold=args.bold,
        white=args.white,
        black=args.black,
        bell_enabled=not args.no_bell
    )
    
    try:
        if args.pomodoro:
            try:
                work_min, break_min = map(int, args.pomodoro.split(','))
                if work_min <= 0 or break_min <= 0:
                    raise ValueError("Times must be positive")
                pomodoro_mode(work_min, break_min, config)
            except ValueError:
                print(f"{Colors.RED}Error: Pomodoro format is W,B (e.g., 25,5){Colors.RESET}")
                sys.exit(1)
        
        elif args.stopwatch:
            stopwatch_mode(config)
        
        elif args.timer:
            timer_mode(args.timer, config)
        
        else:
            clock_mode(config)
    
    except Exception as e:
        print(f"{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        sys.exit(1)


if __name__ == '__main__':
    main()
