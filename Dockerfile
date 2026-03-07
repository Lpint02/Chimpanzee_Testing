FROM arm64v8/python:3.10-slim-bookworm

# Evita interruzioni interattive
ARG DEBIAN_FRONTEND=noninteractive

# 1. Install System Dependencies required for OpenCV and Networking
# libgl1-mesa-glx, libglib2.0-0: Critical for cv2
# libsm6, libxext6: Additional graphical libs often needed
# iputils-ping, net-tools: Essential for network debugging with ROS container
# mosquitto-clients: Useful for testing MQTT connectivity from shell
RUN apt-get update && apt-get install -y --no-install-recommends \
  libgl1 \               
  libglx-mesa0 \        
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender-dev \
  iputils-ping \
  net-tools \
  mosquitto-clients \
  && rm -rf /var/lib/apt/lists/*

# 2. Install Python Dependencies
# opencv-python: For Image Processing
# paho-mqtt: For Communication with ROS Bridge
# py_trees: For Behavior Tree logic
# bottle: (Optional) If web interface is needed later
RUN pip install --no-cache-dir \
  numpy \
  opencv-python \
  paho-mqtt \
  py_trees \
  requests \
  bottle

# 3. Security: Create a non-root user
# Using ID 1000 is standard to avoid permission issues with mounted volumes on Linux
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g ${GROUP_ID} robot && \
  useradd -m -u ${USER_ID} -g robot -s /bin/bash robot

WORKDIR /src

# Switch to non-root user
USER robot

CMD ["tail", "-f", "/dev/null"]
