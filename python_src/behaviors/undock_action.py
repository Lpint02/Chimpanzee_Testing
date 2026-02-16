#!/usr/bin/env python3
import py_trees
import paho.mqtt.client as mqtt
import time
import os
import threading

class CheckAndUndock(py_trees.behaviour.Behaviour):
    def __init__(self, name="CheckAndUndock"):
        super().__init__(name)
        # Config MQTT
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
        
        self.client = mqtt.Client(client_id="brain_undock")
        self.is_undocked = False
        self.trigger_sent = False
        self.undock_start_time = 0
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[Undock] MQTT Error: {e}")

        # Subscribe to Result
        self.client.subscribe("robot/undock/result")
        self.client.on_message = self.on_undock_message # Override per questo client specifico

    def on_undock_message(self, client, userdata, msg):
        if msg.topic == "robot/undock/result":
            payload = msg.payload.decode()
            print(f"[Undock] Received Result: {payload}")
            if payload == "success":
                self.is_undocked = True
            elif payload == "failure":
                print("[Undock] Failed! Assuming free for now to not block...") 
                self.is_undocked = True # Fallback: se fallisce (es. già staccato), proseguiamo

    def update(self):
        # 1. Se abbiamo già finito, ritorna SUCCESS
        if self.is_undocked:
            return py_trees.common.Status.SUCCESS

        # 2. Se non abbiamo ancora mandato il trigger, mandalo
        if not self.trigger_sent:
            print("[Undock] Triggering Undock Action via MQTT...")
            self.client.publish("robot/cmd/undock", "trigger")
            self.trigger_sent = True
            self.undock_start_time = time.time()
            return py_trees.common.Status.RUNNING

        # 3. Aspetta feedback (o timeout di sicurezza 30s)
        if (time.time() - self.undock_start_time) > 30.0:
            print("[Undock] Timeout! Force Success.")
            self.is_undocked = True
            return py_trees.common.Status.SUCCESS
        else:
            return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        pass
