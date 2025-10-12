#!/bin/bash

# Log the stop attempt
echo "$(date): Attempting to stop scalping process..." >> /var/log/adx.log

# Method 1: Find and kill by script name
pkill -f "main.py run"

# Method 2: Alternative - kill by python process running the specific script
# ps aux | grep "main.py run" | grep -v grep | awk '{print $2}' | xargs kill -15

# Wait a moment for graceful shutdown
sleep 5

# Force kill if still running
pkill -9 -f "main.py run"

# Log completion
echo "$(date): Stop script completed" >> /var/log/adx.log

# Optional: Check if process is still running
if pgrep -f "main.py run" > /dev/null; then
    echo "$(date): WARNING - Process still running!" >> /var/log/adx.log
else
    echo "$(date): Process successfully stopped" >> /var/log/adx.log
fi