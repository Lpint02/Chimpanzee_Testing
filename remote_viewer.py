#!/usr/bin/env python3
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import base64
import sys

# CONFIGURAZIONE
MQTT_HOST = '192.168.1.100' # <--- METTI QUI L'IP DEL ROBOT (o 'localhost' se usi tutto in locale)
MQTT_PORT = 1883
TOPIC = "robot/camera/debug" # O "robot/camera" per vedere l'originale

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        # Decode Base64 -> Image
        img_data = base64.b64decode(msg.payload)
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if frame is not None:
            cv2.imshow("Robot Eye (Debug)", frame)
            
            # Premi 'q' per uscire
            if cv2.waitKey(1) & 0xFF == ord('q'):
                sys.exit(0)
                
    except Exception as e:
        print(f"Error: {e}")

client = mqtt.Client(client_id="remote_viewer")
client.on_connect = on_connect
client.on_message = on_message

print(f"Connecting to {MQTT_HOST}...")
try:
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("Exiting...")
except Exception as e:
    print(f"Connection Failed: {e}")
