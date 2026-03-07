#!/usr/bin/env python3
"""bridge_node.py - Ponte bidirezionale tra ROS2 e MQTT.

Gestisce la comunicazione tra il mondo ROS2 (body del robot) e il
broker MQTT (sistema nervoso). Converte messaggi ROS2 in payload MQTT
e viceversa per camera, cmd_vel, battery, dock e undock.
"""
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from sensor_msgs.msg import Image, BatteryState
from geometry_msgs.msg import Twist
from cv_bridge import CvBridge
from irobot_create_msgs.action import Undock, Dock
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

        # MQTT -> ROS (Undock Action)
        self._undock_client = ActionClient(self, Undock, 'undock')

        # MQTT -> ROS (Dock Action)
        self._dock_client = ActionClient(self, Dock, 'dock')

        # ROS -> MQTT (Battery State)
        self.battery_subscription = self.create_subscription(
            BatteryState,
            '/battery_state',
            self.battery_callback,
            10)

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
        client.subscribe("robot/cmd/undock")
        client.subscribe("robot/cmd/dock")

    def on_message(self, client, userdata, msg):
        """Handle incoming messages from MQTT"""
        if msg.topic == "robot/cmd_vel":
            try:
                data = json.loads(msg.payload.decode())
                twist = Twist()
                twist.linear.x = float(data.get('linear', 0.0))
                twist.angular.z = float(data.get('angular', 0.0))
                self.publisher.publish(twist)
            except Exception as e:
                self.get_logger().error(f"Error parsing cmd_vel: {e}")
        
        elif msg.topic == "robot/cmd/undock":
            self.get_logger().info("Received Undock Command from MQTT")
            self.send_undock_goal()

        elif msg.topic == "robot/cmd/dock":
            self.get_logger().info("Received Dock Command from MQTT")
            self.send_dock_goal()

    def send_undock_goal(self):
        if not self._undock_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("Undock action server not available!")
            return

        goal_msg = Undock.Goal()
        self._undock_client.wait_for_server()
        self._send_goal_future = self._undock_client.send_goal_async(goal_msg)
        self._send_goal_future.add_done_callback(self.goal_response_callback)
        self.get_logger().info("Undock goal sent!")

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Undock Goal Rejected :(')
            self.client.publish("robot/undock/result", "failure")
            return

        self.get_logger().info('Undock Goal Accepted :)')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Undock Action Completed!')
        self.client.publish("robot/undock/result", "success")

    # ======== DOCK ACTION ========

    def send_dock_goal(self):
        """Invia goal Dock all'action server iRobot Create."""
        if not self._dock_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("Dock action server not available!")
            self.client.publish("robot/undock/result", "failure")
            return

        goal_msg = Dock.Goal()
        self._send_dock_future = self._dock_client.send_goal_async(goal_msg)
        self._send_dock_future.add_done_callback(self.dock_goal_response_callback)
        self.get_logger().info("Dock goal sent!")

    def dock_goal_response_callback(self, future):
        """Callback per la risposta al goal Dock."""
        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().info('Dock Goal Rejected :(')
                self.client.publish("robot/dock/result", "failure")
                return

            self.get_logger().info('Dock Goal Accepted :)')
            self._get_dock_result_future = goal_handle.get_result_async()
            self._get_dock_result_future.add_done_callback(
                self.dock_result_callback
            )
        except Exception as e:
            self.get_logger().error(f"Dock goal response error: {e}")
            self.client.publish("robot/dock/result", "failure")

    def dock_result_callback(self, future):
        """Callback per il risultato dell'azione Dock."""
        try:
            result = future.result().result
            if result.is_docked:
                self.get_logger().info('Dock Action Completed! Robot is docked.')
                self.client.publish("robot/dock/result", "success")
            else:
                self.get_logger().info('Dock Action Completed but NOT docked.')
                self.client.publish("robot/dock/result", "failure")
        except Exception as e:
            self.get_logger().error(f"Dock result error: {e}")
            self.client.publish("robot/dock/result", "failure")

    # ======== BATTERY ========

    def battery_callback(self, msg):
        """Converte BatteryState ROS2 in payload MQTT JSON."""
        try:
            payload = json.dumps({
                "level": msg.percentage * 100.0,
                "voltage": msg.voltage
            })
            self.client.publish("robot/battery/status", payload)
        except Exception as e:
            self.get_logger().error(f"Error publishing battery status: {e}")

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
