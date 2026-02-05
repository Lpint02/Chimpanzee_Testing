#!/usr/bin/env python3
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import base64
import json
import os
import time

class BallDetector:
    def __init__(self):
        # Config MQTT
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
        
        self.client = mqtt.Client(client_id="ball_detector")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Parametri Visione (Identici a prima)
        self.lower_red = np.array([0, 120, 70])
        self.upper_red = np.array([10, 255, 255])
        self.min_area = 500
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            print(f"Detector Connected to MQTT at {self.mqtt_host}")
        except Exception as e:
            print(f"Detector Connection Failed: {e}")

    def on_connect(self, client, userdata, flags, rc):
        print(f"Detector Connected with result code {rc}")
        client.subscribe("robot/camera")

    def on_message(self, client, userdata, msg):
        if msg.topic == "robot/camera":
            self.process_image(msg.payload)

    def process_image(self, payload):
        try:
            # Decode Base64 -> Bytes -> Numpy -> Image
            img_data = base64.b64decode(payload)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # Thresholding
            mask = cv2.inRange(hsv, self.lower_red, self.upper_red)
            
            # Morfologia
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Contorni
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            cx = -1
            area = 0
            
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest_contour)
                
                if area > self.min_area:
                    M = cv2.moments(largest_contour)
                    if M['m00'] > 0:
                        cx = int(M['m10'] / M['m00'])
            
            # Publish Result [cx, area] to MQTT (Topic per Vision Data)
            # Questo topic viene ascoltato dal Main Loop del Brain per aggiornare la blackboard
            result_payload = json.dumps([cx, int(area)])
            self.client.publish("robot/vision/ball", result_payload)
            
            # print(f"Vision Processed: cx={cx} area={area}")
            
        except Exception as e:
            print(f"Vision Error: {e}")

if __name__ == '__main__':
    detector = BallDetector()
    while True:
        time.sleep(1)
