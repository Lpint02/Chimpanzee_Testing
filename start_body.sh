#!/bin/bash
set -e

# ==========================================
# ROS2 Body Startup Script
# ==========================================

# 1. Source System ROS2 Environment
# Note: The Dockerfile sets ENTRYPOINT to /ros_entrypoint.sh which helps,
# but since mistakes happen, let's ensure we have the environment.
# 1. Source System ROS2 Environment
# We source the setup file directly instead of the entrypoint script
# to avoid re-executing the 'exec "$@"' command at the end of entrypoint.
if [ -f "/opt/ros/foxy/install/setup.bash" ]; then
    source "/opt/ros/foxy/install/setup.bash"
elif [ -f "/opt/ros/foxy/setup.bash" ]; then
    source "/opt/ros/foxy/setup.bash"
fi

# 2. Source Local Workspace
if [ -f "/workspace/install/setup.bash" ]; then
    source "/workspace/install/setup.bash"
fi

# 3. Export Critical Variables (Just in case they weren't set)
export ROS_DOMAIN_ID=0
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/fastdds.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

echo "🚀 Starting Body Container..."
echo "   - ROS2 Domain: $ROS_DOMAIN_ID"
echo "   - RMW: $RMW_IMPLEMENTATION"

# 4. Start Camera Node (Background)
echo "📷 Starting Camera Node..."
python3 /workspace/src/camera_gst/camera_node.py &

# Wait for camera to initialize
sleep 3

# 5. Start MQTT Bridge (Foreground)
echo "🌉 Starting MQTT Bridge..."
exec ros2 run mqtt_bridge bridge_node
