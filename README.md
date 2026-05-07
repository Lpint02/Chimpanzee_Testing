# Chimpanzee Testing — Autonomous Robot Control System
 
> A team-developed autonomous robotics project built on **NVIDIA Jetson Nano** and **iRobot Create 3**, featuring a containerised Python/ROS2 split architecture orchestrated via Docker and driven by a Behavior Tree decision engine.
>
> 
![Python](https://img.shields.io/badge/Python-3.10-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![ROS2](https://img.shields.io/badge/ROS2-Foxy-22314E?style=flat-square&logo=ros&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?style=flat-square&logo=eclipsemosquitto&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-CV%2FAI-5C3EE8?style=flat-square&logo=opencv&logoColor=white)
![NVIDIA](https://img.shields.io/badge/NVIDIA-Jetson%20Nano-76B900?style=flat-square&logo=nvidia&logoColor=white)
![py_trees](https://img.shields.io/badge/py__trees-Behavior%20Tree-FF6B35?style=flat-square&logoColor=white)
![GStreamer](https://img.shields.io/badge/GStreamer-Pipeline-CF0000?style=flat-square&logoColor=white)
---
 
## Table of Contents
 
- [Project Overview](#project-overview)
- [System Architecture & Logic](#system-architecture--logic)
- [Tech Stack](#tech-stack)
- [How to Run / Installation](#how-to-run--installation)
---
 
## Project Overview
 
This project implements the full control stack for an autonomous mobile robot. The robot is capable of operating independently in an unstructured environment, executing a prioritised set of behaviours:
 
- **Undocking** from its charging station at startup
- **Searching** for a visual target (a coloured ball) using computer vision
- **Tracking** the target in real time, with predictive "ghost tracking" when the target is temporarily lost
- **Collision recovery** — automatically backing up and rotating when the bumper is triggered
- **Autonomous docking** — returning to the charging base when battery drops below a critical threshold (20%)
The system is designed around a **clean separation between hardware control and high-level cognition**, making individual components independently testable, replaceable, and deployable. All inter-module communication is handled asynchronously via an MQTT message broker, with no direct coupling between the ROS2 hardware layer and the Python logic layer.
 
---
 
## System Architecture & Logic
 
The system follows a **bidirectional Split Architecture** that decouples low-level hardware management from high-level decision-making. The two worlds — ROS2 and Python — never communicate directly; they exchange structured JSON and Base64-encoded payloads exclusively through a central MQTT broker (Mosquitto).
 
```
┌──────────────────────────────────────────────────────────────────────┐
│                     DOCKER HOST — network_mode: host                 │
│                         (Jetson Nano, localhost)                     │
│                                                                      │
│  ┌─────────────────────┐  MQTT :1883  ┌──────────────────────────┐   │
│  │  container: ros2    │◄────────────►│  container: py310        │   │
│  │  image: ros2_custom │              │  image: py310_img        │   │
│  │                     │              │                          │   │
│  │  - start_body.sh    │              │  - start_brain.sh        │   │
│  │  - mqtt_bridge node │              │  - detector.py  (CV/AI)  │   │
│  │  - CSI camera       │              │  - main.py      (BT)     │   │
│  │  - cmd_vel / dock   │              │                          │   │
│  │  runtime: nvidia    │              │  cpus: 2.0 / mem: 1g     │   │
│  │  privileged: true   │              │                          │   │
│  └─────────────────────┘              └──────────────────────────┘   │
│                    ▲                                                 │
│                    │ localhost:1883                                  │
│          ┌ ─────────┴──────────┐                                     │
│          │ container: mosquitto│                                     │
│          │ eclipse-mosquitto:2 │                                     │
│          └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────┘
```
 
> **Network design note:** all three containers use `network_mode: host`. This is a deliberate trade-off on the Jetson Nano — it avoids the complexity of bridge-to-host routing for MQTT, and it allows the `ros2` container to communicate directly with the iRobot Create 3 hardware driver over the host network. Both containers reach Mosquitto simply via `localhost:1883`.
 
### Body — The ROS2 Hardware Layer (`ros2` container)
 
Built from `Dockerfile.ros2` as image `ros2_custom`, this container manages all hardware-level concerns. It runs with `runtime: nvidia`, `privileged: true`, and direct device mounts (`/dev/video0`, NVHOST GPU devices, the Argus socket) to access the CSI camera and GPU hardware acceleration. A custom ROS2 node, `mqtt_bridge`, acts as the translation layer between the robot's hardware interface and the MQTT bus:
 
- Subscribes to ROS2 topics (CSI camera feed, battery state, bumper events) and republishes them as MQTT messages
- Listens for incoming MQTT commands from the Brain and translates them into ROS2 actions (`cmd_vel` for velocity, `irobot_create_msgs` actions for dock/undock)
Startup is managed by `start_body.sh`, mounted read-only into the container.
 
### Brain — The Python Cognitive Layer (`py310` container)
 
Built from the root `Dockerfile` as image `py310_img`, this container holds the entire cognitive stack. It has **zero ROS2 dependencies**, making it portable and independently testable. The `python_src` directory is mounted at `/src` and startup is managed by `start_brain.sh`:
 
- `detector.py` — consumes Base64-encoded camera frames from MQTT and runs the computer vision pipeline (HSV masking + Kalman filter) to detect and track the target ball
- `main.py` — implements the **Behavior Tree** decision engine, reading sensor state from the shared Blackboard and publishing velocity commands and directives back to the broker
### Behavior Tree — Decision Logic (`py_trees`)
 
The robot's decision logic in `main.py` is modelled as a **Behavior Tree** using the `py_trees` Python library, ticked at **10 Hz**. A shared **Blackboard** object holds the global robot state (target position, battery level, docking status, collision flags).
 
The tree structure:
 
```
Root [Sequence]
├── ToBlackboard          ← updates shared state from MQTT data
├── CheckAndUndock        ← handles initial undock at startup
└── Brain_Selector [Selector]
    ├── Battery_Sequence  ← if battery < 20% → ReturnToBase      (highest priority)
    ├── Recovery_Sequence ← if bumper hit    → BackUpAndRotate
    ├── RealTracking_Sequence ← if ball detected → FollowBall
    ├── GhostTracking_Sequence ← if target recently lost → TrackGhost
    └── SearchBall        ← fallback: rotate and search           (lowest priority)
```
 
The `Selector` node guarantees strict **priority-based execution**: each sub-sequence is attempted in order, and the first one that succeeds claims control. This makes the system's behaviour deterministic and easy to reason about.
 
---
 
## Tech Stack
 
| Layer | Technology | Role |
|---|---|---|
| **Language** | Python 3.10 | Entire cognitive stack — detector, behavior tree, MQTT client |
| **Containerisation** | Docker & Docker Compose | Service isolation, orchestration, ARM/Jetson-native deployment |
| **Decision Logic** | `py_trees` | Behavior Tree modelling and execution |
| **Middleware** | ROS2 Foxy (FastDDS) | Hardware abstraction and sensor/actuator interfacing |
| **Messaging** | MQTT (Paho + Mosquitto) | Asynchronous inter-container communication |
| **Computer Vision** | OpenCV + GStreamer | HSV-based ball detection, Kalman filter tracking, hardware-accelerated camera capture (`nvarguscamerasrc`, NVMM memory) |
| **Hardware** | NVIDIA Jetson Nano + iRobot Create 3 | Embedded compute platform and mobile robot base |
| **Process Management** | `systemd` | Auto-start and graceful shutdown of the full Docker stack on the Jetson |
 
**Key architectural choices:**
 
- **Python** drives all high-level logic — the behavior tree, the vision pipeline, and the MQTT communication layer are written entirely in Python 3.10, keeping the cognitive stack clean, readable, and dependency-free from ROS2.
- **Docker Compose** provides hermetic service isolation: each concern (hardware bridge, cognition, message broker) runs in its own container, with explicit network boundaries. This also makes the system straightforward to reproduce on any ARM-compatible machine.
- **MQTT as the inter-process bus** decouples the hardware and software worlds entirely — the Brain can be developed and tested offline by replaying MQTT messages, without any physical robot present.
---
 
## How to Run / Installation
 
### Prerequisites
 
- NVIDIA Jetson Nano with JetPack installed
- Docker and Docker Compose installed
- iRobot Create 3 paired and accessible via the host network
### 1. Clone the repository
 
```bash
git clone https://github.com/Lpint02/Chimpanzee_Testing.git
cd Chimpanzee_Testing
```
 
### 2. Tear down any previous instances
 
```bash
docker-compose down --remove-orphans
```
 
### 3. Build the Docker images
 
```bash
docker-compose build
```
 
### 4. Start all services in detached mode
 
```bash
docker-compose up -d
```
 
This brings up three containers: `ros2` (hardware bridge), `py310` (Python brain), and `mosquitto` (MQTT broker).
 
### 5. Build the ROS2 workspace (first run only)
 
```bash
docker exec -it ros2 bash
 
# Inside the container:
colcon build --symlink-install
source install/setup.bash
```
 
### 6. Launch the modules
 
The containers start automatically via their respective startup scripts (`start_body.sh` for `ros2`, `start_brain.sh` for `py310`). For **manual debug mode**, open separate terminals for each module:
 
**Terminal 1 — ROS2 MQTT Bridge (hardware layer):**
```bash
docker exec -it ros2 bash
source install/setup.bash
ros2 run mqtt_bridge bridge_node
```
 
**Terminal 2 — Vision Detector (Python brain):**
```bash
docker exec -it py310 bash
python3 detector.py
```
 
**Terminal 3 — Behavior Tree / Main Logic (Python brain):**
```bash
docker exec -it py310 bash
python3 main.py
```
 
### Automatic startup via systemd (Jetson Nano)
 
The repository includes a `systemd` service unit (`ros2_robot.service`) that automatically starts and gracefully stops the full Docker Compose stack on boot:
 
```bash
sudo systemctl enable ros2_robot.service
sudo systemctl start ros2_robot.service
```
 
---
 
## Team
 
This system was designed and developed collaboratively as a university project within the Computer Engineering programme at **Università degli Studi dell'Aquila**.
 
---
 
## License
 
This project is released for academic and educational purposes.
