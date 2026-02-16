# Robot Split Architecture - Jetson Nano

## Architettura

```
┌─────────────────┐     MQTT      ┌─────────────────┐
│   ROS2 (Body)   │◄────────────►│  Python (Brain) │
│  mqtt_bridge    │   robot/*    │  detector.py    │
│                 │              │  main.py        │
└────────┬────────┘              └─────────────────┘
         │
    Hardware (Camera, Motors)
```

---

## File Importanti

| File                 | Scopo                                              |
| -------------------- | -------------------------------------------------- |
| `Dockerfile`         | Immagine Python (Brain)                            |
| `Dockerfile.ros2`    | Immagine ROS2 (Body) - estende dustynv + paho-mqtt |
| `start.sh`           | Entrypoint ROS2: carica ambiente e lancia comandi  |
| `docker-compose.yml` | Orchestrazione container                           |

---

## 🔧 SVILUPPO (Manuale)

### 1. Build Immagini

```bash
cd ~/ros2_x_robot
docker-compose down --remove-orphans
docker-compose build
```

### 2. Avvia Container

```bash
docker-compose up -d
docker ps  # Verifica: ros2, py310, mosquitto
```

### 3. Compila ROS2 (Prima volta)

```bash
docker exec -it ros2 bash

# Dentro il container:
cd /workspace
colcon build --symlink-install
source install/setup.bash

# Test bridge
ros2 run mqtt_bridge bridge_node
```

### 4. Avvia Brain (Terminali separati)

```bash
# Terminale 1 - Detector
docker exec -it py310 bash
python3 detector.py

# Terminale 2 - Behavior Tree
docker exec -it py310 bash
python3 main.py
```

---

## 🚀 PRODUZIONE (Automatico)

Modifica `docker-compose.yml`:

```yaml
# Servizio ros2_img:
command: ros2 run mqtt_bridge bridge_node

# Servizio python310:
command: python3 main.py
```

Poi:

```bash
docker-compose up -d
# Il robot parte da solo
```

---

## ❌ Errori Comuni

| Errore                  | Causa                    | Soluzione                                 |
| ----------------------- | ------------------------ | ----------------------------------------- |
| `ament_cmake not found` | ROS2 non caricato        | `source /opt/ros/foxy/install/setup.bash` |
| `paho.mqtt not found`   | Immagine vecchia         | `docker-compose build --no-cache`         |
| `Connection Refused`    | Mosquitto non attivo     | `docker ps`, verifica mosquitto           |
| `ImportError: libGL`    | Dockerfile Python errato | Rebuild Python image                      |

---

## 🔍 Debug

```bash
# Vedi traffico MQTT
docker exec -it mosquitto mosquitto_sub -t "robot/#" -v

# Logs container
docker logs ros2
docker logs py310
```
