#!/usr/bin/env bash
#
# CLI Digital Clock Wrapper Script
# Provides convenient shortcuts and error handling for clock.py
#

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOCK_SCRIPT="${SCRIPT_DIR}/cli_clock.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if clock.py exists
if [[ ! -f "$CLOCK_SCRIPT" ]]; then
    echo -e "${RED}Error: clock.py not found at ${CLOCK_SCRIPT}${NC}"
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed${NC}"
    exit 1
fi

# Make sure clock.py is executable
if [[ ! -x "$CLOCK_SCRIPT" ]]; then
    chmod +x "$CLOCK_SCRIPT"
fi

# Function to display help
show_help() {
    cat << EOF
${GREEN}CLI Digital Clock${NC}

Usage: clock [COMMAND] [OPTIONS]

${YELLOW}Commands:${NC}
  (no command)          Display current time with date
  pomodoro [W,B]        Start Pomodoro timer (default: 25,5)
  timer <TIME>          Start countdown timer
  stopwatch             Start stopwatch
  help                  Show this help message

${YELLOW}Options:${NC}
  -f, --focus           Minimal display (no labels)
  -b, --bold            Use bold/thick numbers
  --white               All white text
  --black               All black text
  --no-bell             Disable bell sound

${YELLOW}Examples:${NC}
  clock                         # Show current time
  clock pomodoro                # Default 25/5 Pomodoro
  clock pomodoro 50,10          # Custom Pomodoro
  clock timer 10:00             # 10 minute timer
  clock stopwatch               # Stopwatch
  clock -f timer 5:00           # 5 min timer, focus mode
  clock -b --white stopwatch    # Bold white stopwatch

${YELLOW}Timer Formats:${NC}
  90          90 seconds
  10:30       10 minutes 30 seconds
  1:30:00     1 hour 30 minutes

${YELLOW}Controls (during timer/stopwatch):${NC}
  q           Pause/Resume
  r           Reset (stopwatch only)
  Ctrl+C      Exit

For detailed help: clock.py --help
EOF
}

# Parse command
COMMAND=""
if [[ $# -gt 0 ]] && [[ ! "$1" =~ ^- ]]; then
    COMMAND="$1"
    shift
fi

# Execute based on command
case "$COMMAND" in
    "")
        # No command - show clock
        exec python3 "$CLOCK_SCRIPT" "$@"
        ;;

    pomodoro)
        # Pomodoro mode
        if [[ $# -gt 0 ]] && [[ ! "$1" =~ ^- ]]; then
            TIMES="$1"
            shift
            exec python3 "$CLOCK_SCRIPT" -p "$TIMES" "$@"
        else
            exec python3 "$CLOCK_SCRIPT" -p 25,5 "$@"
        fi
        ;;

    timer)
        # Timer mode
        if [[ $# -eq 0 ]] || [[ "$1" =~ ^- ]]; then
            echo -e "${RED}Error: timer requires a time argument${NC}"
            echo "Example: clock timer 10:00"
            exit 1
        fi
        TIME="$1"
        shift
        exec python3 "$CLOCK_SCRIPT" -t "$TIME" "$@"
        ;;

    stopwatch)
        # Stopwatch mode
        exec python3 "$CLOCK_SCRIPT" -s "$@"
        ;;

    help|--help|-h)
        show_help
        exit 0
        ;;

    *)
        echo -e "${RED}Error: Unknown command '$COMMAND'${NC}"
        echo "Use 'clock help' for usage information"
        exit 1
        ;;
esac
