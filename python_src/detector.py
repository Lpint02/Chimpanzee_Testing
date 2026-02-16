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
        
        # Parametri Visione (Migliorati per Rosso completo)
        # Range 1: 0-10 (Rosso-Arancio)
        # Aumentiamo la saturazione (S) min da 100 a 130 per evitare grigi/marroni
        # Aumentiamo il valore (V) min da 50 a 70 per evitare ombre scure
        self.lower_red1 = np.array([0, 130, 70])
        self.upper_red1 = np.array([10, 255, 255])
        
        # Range 2: 170-180 (Rosso-Viola)
        self.lower_red2 = np.array([170, 130, 70])
        self.upper_red2 = np.array([180, 255, 255])
        
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
        start_time = time.time()
        try:
            # Decode Base64 -> Bytes -> Numpy -> Image
            img_data = base64.b64decode(payload)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                print("Frame decode FAILED")
                return
            
            # --- MODIFICA 1: Gaussian Blur per ridurre il rumore ---
            # Applichiamo una sfuocatura 11x11 per rimuovere i puntini e lisciare i bordi
            blurred = cv2.GaussianBlur(frame, (11, 11), 0)

            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
            
            # Thresholding combinato (Range 1 + Range 2) - GIA IMPLEMENTATO DA TE
            mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
            mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
            mask = cv2.bitwise_or(mask1, mask2)
            
            # Morfologia
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Contorni
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            cx = -1
            area = 0
            
            # --- MODIFICA 2: Debug Visualization ---
            # Disegniamo i contorni sull'immagine originale per il debug
            debug_frame = frame.copy()
            cv2.drawContours(debug_frame, contours, -1, (0, 255, 0), 2)

            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest_contour)
                
                if area > self.min_area:
                    M = cv2.moments(largest_contour)
                    if M['m00'] > 0:
                        cx = int(M['m10'] / M['m00'])
                        cy = int(M['m01'] / M['m00'])
                        # Disegna centro e informazioni
                        cv2.circle(debug_frame, (cx, cy), 5, (255, 0, 0), -1)
                        cv2.putText(debug_frame, f"A:{int(area)} X:{cx}", (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Publish Result [cx, area] to MQTT (Topic per Vision Data)
            result_payload = json.dumps([cx, int(area)])
            self.client.publish("robot/vision/ball", result_payload)
            
            # --- DEBUG STREAM OPTIMIZATION ---
            # Invia l'immagine con i disegni su un topic separato per il remote_viewer
            # Ridimensiona e comprimi pesantemente per non intasare la rete
            self.frame_count = getattr(self, 'frame_count', 0) + 1
            if self.frame_count % 3 == 0: # 1 frame ogni 3
                 small_debug = cv2.resize(debug_frame, (320, 240))
                 _, buffer = cv2.imencode('.jpg', small_debug, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                 debug_b64 = base64.b64encode(buffer)
                 self.client.publish("robot/camera/debug", debug_b64)
            
        except Exception as e:
            print(f"Vision Error: {e}")

if __name__ == '__main__':
    detector = BallDetector()
    while True:
        time.sleep(1)
