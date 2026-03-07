#!/usr/bin/env python3
"""
undock_action.py - Nodo BHT per l'azione di undock del robot.

Gestisce il distacco dalla stazione di ricarica tramite MQTT.
Utilizza la blackboard per persistere lo stato is_undocked tra i tick:
- Se is_undocked è True sulla blackboard: ritorna SUCCESS (skip)
- Se is_undocked è False: esegue la logica undock via MQTT
- Al completamento: scrive is_undocked=True sulla blackboard
"""
import py_trees
import paho.mqtt.client as mqtt
import time
import os


class CheckAndUndock(py_trees.behaviour.Behaviour):
    """
    Controlla se il robot è undocked. Se no, invia comando undock via MQTT
    e attende il risultato. Usa la blackboard per persistere lo stato.
    """

    def __init__(self, name="CheckAndUndock"):
        super().__init__(name)

        # Blackboard per persistenza stato
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='is_undocked', access=py_trees.common.Access.WRITE
        )

        # Config MQTT
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))

        self.client = mqtt.Client(client_id="brain_undock")
        self.undock_result_received = False
        self.trigger_sent = False
        self.undock_start_time = 0

        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.subscribe("robot/undock/result")
            self.client.on_message = self._on_undock_message
            self.client.loop_start()
        except Exception as e:
            print(f"[Undock] MQTT Error: {e}")

    def _on_undock_message(self, client, userdata, msg):
        """Callback per il risultato dell'undock."""
        try:
            if msg.topic == "robot/undock/result":
                payload = msg.payload.decode()
                print(f"[Undock] Received Result: {payload}")
                if payload == "success":
                    self.undock_result_received = True
                elif payload == "failure":
                    print("[Undock] Failed! Assuming free to not block...")
                    self.undock_result_received = True
        except Exception as e:
            print(f"[Undock] Message Error: {e}")

    def update(self):
        # 1. Controlla blackboard: se già undocked, skip immediato
        try:
            is_undocked = self.blackboard.get('is_undocked')
            if is_undocked:
                return py_trees.common.Status.SUCCESS
        except KeyError:
            pass

        # 2. Se abbiamo ricevuto risultato undock, salva e ritorna SUCCESS
        if self.undock_result_received:
            self.blackboard.set('is_undocked', True)
            return py_trees.common.Status.SUCCESS

        # 3. Se non abbiamo ancora mandato il trigger, mandalo
        if not self.trigger_sent:
            print("[Undock] Triggering Undock Action via MQTT...")
            self.client.publish("robot/cmd/undock", "trigger")
            self.trigger_sent = True
            self.undock_start_time = time.time()
            return py_trees.common.Status.RUNNING

        # 4. Aspetta feedback (o timeout di sicurezza 30s)
        if (time.time() - self.undock_start_time) > 30.0:
            print("[Undock] Timeout! Force Success.")
            self.blackboard.set('is_undocked', True)
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        pass
