#!/bin/bash
set -e

# ==========================================
# 1. Source ROS2 System
# ==========================================
# Gestiamo entrambi i path (Standard vs Jetson/User custom)
if [ -f /opt/ros/foxy/install/setup.bash ]; then
  source /opt/ros/foxy/install/setup.bash
elif [ -f /opt/ros/foxy/setup.bash ]; then
  source /opt/ros/foxy/setup.bash
fi

# ==========================================
# 2. Source Workspace (Il codice che buildi)
# ==========================================
# Fondamentale per vedere il pacchetto 'mqtt_bridge'
if [ -f /workspace/install/setup.bash ]; then
  source /workspace/install/setup.bash
fi

# ==========================================
# 3. Export Environment Variables
# ==========================================
export ROS_DOMAIN_ID=0
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/fastdds.xml
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

echo "✅ Environment ROS2 caricato correttamente."

# ==========================================
# 4. Execute Command
# ==========================================
# Questo permette al container di lanciare il comando definito nel docker-compose
# mantenendo le variabili d'ambiente settate.
exec "$@"