# CLI Digital Clock ⏰

A feature-rich command-line digital clock with Pomodoro timer, stopwatch, and countdown timer functionality. Displays time using large ASCII art digits with customizable styles and colors.

## Features

- **Digital Clock** - Real-time display of current time and date
- **Pomodoro Timer** - Work/break session management
- **Stopwatch** - Count up timer with pause, resume, and reset
- **Countdown Timer** - Flexible countdown with multiple time formats
- **Focus Mode** - Minimal display without labels
- **Progress Bars** - Visual progress indication for timers
- **Pause/Resume** - All timers support pause and resume functionality
- **Customizable Display** - Bold numbers and color options

## Image
[[cli-clock.png]]

## Requirements

- Python 3.6+
- Unix-like system (Linux, macOS)
- Terminal with ANSI color support

## Installation

1. Clone or download the repository:
```bash
git clone https://github.com/erinrrr/cli-clock.git
cd cli-clock
```

2. Make the script executable:
```bash
chmod +x clock.py
```

3. (Optional) Create a symlink for easy access:
```bash
sudo ln -s $(pwd)/clock.py /usr/local/bin/clock
```

## Usage

### Basic Clock
Display current time with date:
```bash
./clock.py
```

### Stopwatch Mode
```bash
./clock.py -s
```
**Controls:**
- `q` - Pause/Resume
- `r` - Reset
- `Ctrl+C` - Exit

### Countdown Timer
Supports multiple time formats:
```bash
./clock.py -t 10:30      # 10 minutes 30 seconds
./clock.py -t 90         # 90 seconds
./clock.py -t 1:30:00    # 1 hour 30 minutes
```
**Controls:**
- `q` - Pause/Resume
- `Ctrl+C` - Exit

### Pomodoro Timer
Work and break sessions (format: WORK,BREAK in minutes):
```bash
./clock.py -p 25,5       # 25 min work, 5 min break
./clock.py -p 50,10      # 50 min work, 10 min break
```
**Controls:**
- `q` - Pause/Resume during any session
- `Ctrl+C` - Exit

### Display Options

**Bold Numbers:**
```bash
./clock.py -b
./clock.py --bold
```

**Focus Mode** (minimal display):
```bash
./clock.py -f
./clock.py --focus
```

**Color Options:**
```bash
./clock.py --white       # All white text
./clock.py --black       # All black text
```

**Disable Bell Sound:**
```bash
./clock.py --no-bell
```

### Combined Options
Options can be combined for custom displays:
```bash
./clock.py -fb -s              # Focus mode + bold stopwatch
./clock.py -f -p 25,5          # Focus mode Pomodoro
./clock.py -b --white -t 5:00  # Bold white timer
```

## Examples

### Standard Pomodoro Session
```bash
./clock.py -p 25,5
```
Runs continuous Pomodoro sessions with 25-minute work periods and 5-minute breaks.

### Quick Timer with Focus Mode
```bash
./clock.py -f -t 10:00
```
10-minute countdown timer with minimal display.

### Bold Stopwatch
```bash
./clock.py -b -s
```
Stopwatch with thick, bold numbers.

### Minimal Clock
```bash
./clock.py -f
```
Current time only, no date label.

## Command Reference

```
usage: clock.py [-h] [-f] [-b] [--white] [--black] [--no-bell]
                [-p WORK,BREAK] [-s] [-t TIME]

CLI Digital Clock with Timer Features

options:
  -h, --help            show this help message and exit
  -f, --focus           Focus mode (minimal display)
  -b, --bold            Use bold/thick numbers
  --white               Display all text in white
  --black               Display all text in black
  --no-bell             Disable bell sound for timers
  -p WORK,BREAK, --pomodoro WORK,BREAK
                        Pomodoro timer (work,break minutes, e.g., 25,5)
  -s, --stopwatch       Stopwatch mode
  -t TIME, --timer TIME
                        Countdown timer (MM:SS, HH:MM:SS, or seconds)
```

## Timer Formats

The countdown timer (`-t`) accepts three formats:

| Format | Example | Description |
|--------|---------|-------------|
| Seconds | `90` | 90 seconds (1 minute 30 seconds) |
| MM:SS | `10:30` | 10 minutes 30 seconds |
| HH:MM:SS | `1:30:00` | 1 hour 30 minutes |

## Keyboard Controls

During stopwatch or timer modes:

| Key | Action |
|-----|--------|
| `q` | Pause/Resume |
| `r` | Reset (stopwatch only) |
| `Ctrl+C` | Exit program |

## Tips

1. **Use focus mode for distraction-free timing:**
   ```bash
   ./clock.py -f -p 25,5
   ```

2. **Combine with system commands:**
   ```bash
   ./clock.py -t 10:00 && notify-send "Timer Complete!"
   ```

3. **Create aliases in your `.bashrc` or `.zshrc`:**
   ```bash
   alias pomodoro='~/path/to/clock.py -f -p 25,5'
   alias timer='~/path/to/clock.py -f -t'
   alias stopwatch='~/path/to/clock.py -s'
   ```

## Troubleshooting

**Script doesn't run:**
- Ensure it's executable: `chmod +x clock.py`
- Check Python version: `python3 --version` (requires 3.6+)

**Colors don't display correctly:**
- Verify your terminal supports ANSI colors
- Try different terminal emulators (iTerm2, GNOME Terminal, etc.)

**Input not responding:**
- Script requires Unix-like system (Linux, macOS)
- Windows users can use WSL (Windows Subsystem for Linux)

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
