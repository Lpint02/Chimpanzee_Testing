#!/usr/bin/env python3
"""
Camera node per CSI camera su Jetson Nano.
Usa GStreamer + nvarguscamerasrc invece di v4l2.
Pubblica frames su MQTT topic robot/camera.
"""
import cv2
import paho.mqtt.client as mqtt
import base64
import time
import os

def main():
    mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
    mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
    
    client = mqtt.Client(client_id="camera_node")
    client.connect(mqtt_host, mqtt_port)
    print(f"Camera node connected to MQTT at {mqtt_host}:{mqtt_port}")
    
    # GStreamer pipeline per CSI camera Jetson
    gst_pipeline = (
        "nvarguscamerasrc ! "
        "video/x-raw(memory:NVMM),width=640,height=480,framerate=10/1 ! "
        "nvvidconv ! "
        "video/x-raw,format=BGRx ! "
        "videoconvert ! "
        "video/x-raw,format=BGR ! "
        "appsink drop=1"
    )
    
    cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
    
    if not cap.isOpened():
        print("ERROR: Cannot open CSI camera with GStreamer")
        print("Make sure nvarguscamerasrc is available and camera is connected")
        return
    
    print("CSI Camera opened successfully with GStreamer")
    
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if ret:
            # Comprimi in JPEG e invia via MQTT
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
            client.publish("robot/camera", base64.b64encode(buffer))
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"Published {frame_count} frames")
        else:
            print("Failed to grab frame")
        
        time.sleep(0.1)  # ~10 fps

if __name__ == '__main__':
    main()
