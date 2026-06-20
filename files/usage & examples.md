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

**Bell Sound on Completion:**

Bell is off by default. Enable it with:
```bash
./clock.py --bell
```
Note: many terminal apps (Terminal.app, iTerm2, GNOME Terminal, VS Code's integrated terminal, etc.) ship with the audible bell disabled by default and show a silent visual flash instead. If `--bell` doesn't make a sound, check your terminal's preferences for a "Bell" / "Audible bell" setting.

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