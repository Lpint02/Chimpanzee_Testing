#!/bin/bash
set -e

# ==========================================
# ROS2 Entrypoint per dustynv/ros Jetson
# ==========================================

# Source ROS2 - Il path su dustynv è /opt/ros/${ROS_DISTRO}/install/setup.bash
# Ma la variabile ROS_DISTRO potrebbe non essere settata, quindi proviamo tutto
for setup_file in \
    "/opt/ros/${ROS_DISTRO:-foxy}/install/setup.bash" \
    "/opt/ros/foxy/install/setup.bash" \
    "/opt/ros/foxy/setup.bash" \
    "/ros_entrypoint.sh"; do
    if [ -f "$setup_file" ]; then
        echo "Sourcing: $setup_file"
        source "$setup_file"
        break
    fi
done

# Source workspace locale (se compilato)
if [ -f /workspace/install/setup.bash ]; then
    source /workspace/install/setup.bash
fi

# Variabili ambiente ROS2
export ROS_DOMAIN_ID=0
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/fastdds.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

echo "✅ ROS2 Environment Ready"

# Esegui comando passato
exec "$@"