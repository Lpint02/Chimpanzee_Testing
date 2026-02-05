#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
from cv_bridge import CvBridge
import cv2
import paho.mqtt.client as mqtt
import json
import base64
import os

class MqttBridge(Node):
    def __init__(self):
        super().__init__('mqtt_bridge')
        
        # Configuration
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
        
        self.get_logger().info(f"Connecting to MQTT Broker at {self.mqtt_host}:{self.mqtt_port}")
        
        # ROS -> MQTT (Camera)
        self.bridge = CvBridge()
        self.subscription = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            10)
            
        # MQTT -> ROS (Cmd Vel)
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        
        # MQTT Client Setup
        self.client = mqtt.Client(client_id="ros2_bridge")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            self.get_logger().error(f"Failed to connect to MQTT: {e}")

    def on_connect(self, client, userdata, flags, rc):
        self.get_logger().info(f"Connected to MQTT with result code {rc}")
        client.subscribe("robot/cmd_vel")

    def on_message(self, client, userdata, msg):
        """Handle incoming messages from MQTT"""
        if msg.topic == "robot/cmd_vel":
            try:
                data = json.loads(msg.payload.decode())
                twist = Twist()
                twist.linear.x = float(data.get('linear', 0.0))
                twist.angular.z = float(data.get('angular', 0.0))
                self.publisher.publish(twist)
                # self.get_logger().info(f"Published cmd_vel: lin={twist.linear.x}, ang={twist.angular.z}") 
            except Exception as e:
                self.get_logger().error(f"Error parsing cmd_vel: {e}")

    def image_callback(self, msg):
        """Convert ROS Image -> JPEG -> Base64 -> MQTT"""
        try:
            # Convert ROS Image to OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
            # Encode as JPEG
            # Quality 50 to reduce bandwidth
            _, buffer = cv2.imencode('.jpg', cv_image, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            
            # Convert to Base64 specifically for easier debugging/JSON inclusion if needed,
            # though raw bytes are more efficient. Let's use Base64 to be safe with text protocols.
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            # Publish to MQTT
            self.client.publish("robot/camera", jpg_as_text)
            
        except Exception as e:
            self.get_logger().error(f"Error processing image: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = MqttBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
