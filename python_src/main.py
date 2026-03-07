#!/usr/bin/env python3
"""
main.py - Cervello principale del robot (Brain Node).

Gestisce il behavior tree completo con questa struttura:

Root (Sequence, memory=False)
 ├─ ToBlackboard
 ├─ CheckAndUndock
 └─ Brain_Selector (Selector, memory=False)
     ├─ Battery_Sequence (Sequence, memory=False)
     │    ├─ IsBatteryLow (threshold=20.0)
     │    └─ ReturnToBase
     ├─ Recovery_Sequence (Sequence, memory=False)
     │    ├─ IsRecoveringOrBumperDetected
     │    └─ BackUpAndRotate
     ├─ RealTracking_Sequence (Sequence, memory=False)
     │    ├─ BallDetectedCondition
     │    └─ FollowBall
     ├─ GhostTracking_Sequence (Sequence, memory=False)
     │    ├─ IsTargetGhost
     │    └─ TrackGhost
     └─ SearchBall

Il loop principale gira a 10Hz. Ad ogni tick legge cmd_vel dalla
blackboard e lo pubblica su MQTT per il bridge ROS2.
"""
import py_trees
import time
import os
import paho.mqtt.client as mqtt
import json

from behaviors.toblackboard import ToBlackboard
from behaviors.undock_action import CheckAndUndock
from behaviors.actions import (
    FollowBall, SearchBall, BackUpAndRotate,
    TrackGhost, ReturnToBase
)
from behaviors.conditions import (
    BallDetectedCondition, IsTargetGhost,
    IsBatteryLow, IsRecoveringOrBumperDetected
)


class MainBrain:
    """
    Classe principale del cervello del robot.

    Inizializza la connessione MQTT, la blackboard con valori di default,
    costruisce il behavior tree e avvia il loop di esecuzione a 10Hz.
    """

    def __init__(self):
        # MQTT Setup
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))

        self.client = mqtt.Client(client_id="brain_main")
        self.client.on_connect = self.on_connect

        # Blackboard - Valori di default
        self.blackboard = py_trees.blackboard.Client(name="MainBrain")
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='battery_level', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='is_undocked', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='is_recovering', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='is_bumped', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.READ
        )

        # Inizializza valori di default
        self.blackboard.set('ball_data', {
            "cx": -1, "cy": -1, "area": 0,
            "vx": 0.0, "vy": 0.0, "mode": "lost"
        })
        self.blackboard.set('battery_level', 100.0)
        self.blackboard.set('is_undocked', False)
        self.blackboard.set('is_recovering', False)
        self.blackboard.set('is_bumped', False)

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
        """Callback connessione MQTT."""
        print(f"Brain Connected Code: {rc}")

    def create_behavior_tree(self):
        """
        Costruisce il behavior tree con la struttura specificata.
        """
        # Root (Sequence, memory=False)
        root = py_trees.composites.Sequence(name="Root", memory=False)

        # 1. ToBlackboard - ponte MQTT -> blackboard
        to_blackboard = ToBlackboard(
            name="ToBlackboard", mqtt_client=self.client
        )

        # 2. CheckAndUndock
        undock = CheckAndUndock(name="CheckAndUndock")

        # 3. Brain_Selector (Selector, memory=False)
        brain_selector = py_trees.composites.Selector(
            name="Brain_Selector", memory=False
        )

        # 3.1 Battery_Sequence (Sequence, memory=False)
        battery_seq = py_trees.composites.Sequence(
            name="Battery_Sequence", memory=False
        )
        is_battery_low = IsBatteryLow(
            name="IsBatteryLow", threshold=20.0
        )
        return_to_base = ReturnToBase(name="ReturnToBase")
        battery_seq.add_children([is_battery_low, return_to_base])

        # 3.2 Recovery_Sequence (Sequence, memory=False)
        recovery_seq = py_trees.composites.Sequence(
            name="Recovery_Sequence", memory=False
        )
        is_bumped = IsRecoveringOrBumperDetected(
            name="IsRecoveringOrBumperDetected"
        )
        do_recovery = BackUpAndRotate(name="BackUpAndRotate")
        recovery_seq.add_children([is_bumped, do_recovery])

        # 3.3 RealTracking_Sequence (Sequence, memory=False)
        real_tracking_seq = py_trees.composites.Sequence(
            name="RealTracking_Sequence", memory=False
        )
        ball_detected = BallDetectedCondition(name="BallDetectedCondition")
        follow_ball = FollowBall(name="FollowBall")
        real_tracking_seq.add_children([ball_detected, follow_ball])

        # 3.4 GhostTracking_Sequence (Sequence, memory=False)
        ghost_tracking_seq = py_trees.composites.Sequence(
            name="GhostTracking_Sequence", memory=False
        )
        is_ghost = IsTargetGhost(name="IsTargetGhost")
        track_ghost = TrackGhost(name="TrackGhost")
        ghost_tracking_seq.add_children([is_ghost, track_ghost])

        # 3.5 SearchBall (fallback)
        search_ball = SearchBall(name="SearchBall")

        # Assembla Brain Selector
        brain_selector.add_children([
            battery_seq,
            recovery_seq,
            real_tracking_seq,
            ghost_tracking_seq,
            search_ball
        ])

        # Assembla Root
        root.add_children([to_blackboard, undock, brain_selector])

        return root

    def run(self):
        """Loop principale del brain a 10Hz."""
        print("Brain Running...")
        try:
            while True:
                # 1. Tick Tree
                self.tree.tick()

                # 2. Read Output from Blackboard ('cmd_vel')
                try:
                    cmd = self.blackboard.get('cmd_vel')
                    if cmd:
                        # 3. Publish to MQTT -> ROS Bridge
                        payload = json.dumps(cmd)
                        self.client.publish("robot/cmd_vel", payload)
                except KeyError:
                    pass

                time.sleep(0.1)  # 10Hz

        except KeyboardInterrupt:
            self.client.publish(
                "robot/cmd_vel",
                json.dumps({'linear': 0.0, 'angular': 0.0})
            )
            self.client.loop_stop()
            print("Brain Stopped.")


if __name__ == '__main__':
    brain = MainBrain()
    brain.run()
