#!/usr/bin/env bash
# PRIMA lab runner: executes jobs queued by a remote Claude session (Cowork).
# Ctrl-C (or the file work/runner/STOP) stops it.
cd "$HOME/git/prima"
python3 tools/labrunner.py
echo
echo "labrunner stopped. Press Enter to close this window."
read -r _
