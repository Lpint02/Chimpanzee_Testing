#!/bin/bash
set -e

echo "🧠 Starting Brain Container..."

# 1. Start Detector (Background)
echo "👁️ Starting Detector..."
python3 detector_kalman.py &

# Wait for detector to initialize
sleep 2

# 2. Start Main Logic (Foreground)
echo "🧠 Starting Main Logic..."
python3 main.py
