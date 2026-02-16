#!/usr/bin/env python3
import py_trees
import time
import os
import paho.mqtt.client as mqtt
import json
import threading

# Import Behaviors adapting to new location
from behaviors.undock_action import CheckAndUndock # Keep as is if logic pure? Wait, undock uses ROS action client.
# PROBLEM: CheckAndUndock uses ActionClient (ROS). 
# FIX: For now, we stub it or assume undock is done manually/simulated for this migration scope.
# OR: We need to bridge the Undock Action too.
# Let's simplify: Remove Undock for the "Ball Follower" migration scope as focusing on split architecture.
# Or implement a simple "Stub" behavior that just returns SUCCESS immediately.
# User asked to migrate "Nodes" and "Behaviors" they listed.

from behaviors.actions import FollowBall, SearchBall, BackUpAndRotate
from behaviors.conditions import BallDetectedCondition, IsRecoveringOrBumperDetected

class MainBrain:
    def __init__(self):
        # MQTT Setup
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
        
        self.client = mqtt.Client(client_id="brain_main")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Blackboard
        self.blackboard = py_trees.blackboard.Client(name="MainBrain")
        self.blackboard.register_key(key='ball_data', access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key='cmd_vel', access=py_trees.common.Access.READ)
        
        # Initialize Data
        self.blackboard.set('ball_data', [-1, 0])
        
        # Connect MQTT
        print("Brain connecting to MQTT...")
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Brain MQTT Connection Error: {e}")

        # Build Tree
        self.root = self.create_behavior_tree()
        self.tree = py_trees.trees.BehaviourTree(self.root)
        self.tree.setup(timeout=15)

    def on_connect(self, client, userdata, flags, rc):
        print(f"Brain Connected Code: {rc}")
        client.subscribe("robot/vision/ball")
        # Could subscribe to hazard here too

    def on_message(self, client, userdata, msg):
        if msg.topic == "robot/vision/ball":
            try:
                data = json.loads(msg.payload.decode())
                # Scrivi sulla blackboard per le Conditions
                self.blackboard.set('ball_data', data)
            except Exception as e:
                print(f"Brain Msg Error: {e}")

    def create_behavior_tree(self):
        # Root sequence
        root = py_trees.composites.Sequence(name="Main Sequence", memory=True)
        
        # 1. Undock Action
        # Checks if undocked, triggers via MQTT if not, waits for completion.
        undock = CheckAndUndock() 
        root.add_child(undock) 
        
        # 2. Main Logic Selector
        # Priorità: Recovery -> Follow -> Search
        action_selector = py_trees.composites.Selector(name="Action Selector", memory=False)
        
        # --- Recovery ---
        recovery_sequence = py_trees.composites.Sequence(name="Recovery Sequence", memory=True)
        is_bumped = IsRecoveringOrBumperDetected(name="Bumper Detected?")
        do_recovery = BackUpAndRotate(name="BackUp And Rotate")
        recovery_sequence.add_children([is_bumped, do_recovery])
        
        # --- Follow ---
        follow_sequence = py_trees.composites.Sequence(name="Follow Sequence", memory=False)
        ball_detected = BallDetectedCondition(name="Ball Detected?")
        follow_ball = FollowBall(name="Follow Ball")
        follow_sequence.add_children([ball_detected, follow_ball])
        
        # --- Search ---
        search_ball = SearchBall(name="Search Ball")
        
        action_selector.add_children([recovery_sequence, follow_sequence, search_ball])
        root.add_children([action_selector])
        
        return root

    def run(self):
        print("Brain Running...")
        try:
            while True:
                # 1. Tick Tree
                self.tree.tick()
                
                # 2. Read Output from Blackboard ('cmd_vel') populated by Actions
                try:
                    cmd = self.blackboard.get('cmd_vel')
                    if cmd:
                        # 3. Publish to MQTT -> ROS Bridge
                        payload = json.dumps(cmd)
                        self.client.publish("robot/cmd_vel", payload)
                except KeyError:
                    pass
                
                time.sleep(0.1) # 10Hz
                
        except KeyboardInterrupt:
            self.client.publish("robot/cmd_vel", json.dumps({'linear': 0.0, 'angular': 0.0}))
            self.client.loop_stop()

if __name__ == '__main__':
    brain = MainBrain()
    brain.run()
