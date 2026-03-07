#!/usr/bin/env python3
"""
toblackboard.py - Nodo BHT ponte tra MQTT e Blackboard py_trees.

Si iscrive ai topic MQTT rilevanti e aggiorna la blackboard
ad ogni messaggio ricevuto. Il nodo update() ritorna sempre SUCCESS
poiché il suo unico scopo è mantenere la blackboard sincronizzata.

Topic MQTT sottoscritti:
- "robot/vision/ball"     → ball_data (dict completo)
- "robot/battery/status"  → battery_level (float)
- "robot/bumper"          → is_bumped (bool)
"""
import py_trees
import json


class ToBlackboard(py_trees.behaviour.Behaviour):
    """
    Nodo BHT che funge da ponte tra i messaggi MQTT e la blackboard py_trees.

    Il client MQTT viene passato come parametro nel costruttore.
    Le callback MQTT aggiornano la blackboard in modo asincrono
    (il loop MQTT gira in un thread separato).
    update() ritorna sempre SUCCESS.
    """

    def __init__(self, name="ToBlackboard", mqtt_client=None):
        """
        Inizializza il nodo e registra le chiavi sulla blackboard.

        Args:
            name: Nome del nodo nel behavior tree.
            mqtt_client: Istanza paho.mqtt.client.Client già connessa.
        """
        super().__init__(name)
        self.mqtt_client = mqtt_client

        # Blackboard access
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='battery_level', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='is_bumped', access=py_trees.common.Access.WRITE
        )

    def setup(self, **kwargs):
        """Sottoscrivi ai topic MQTT rilevanti."""
        if self.mqtt_client is not None:
            self.mqtt_client.subscribe("robot/vision/ball")
            self.mqtt_client.subscribe("robot/battery/status")
            self.mqtt_client.subscribe("robot/bumper")
            self.mqtt_client.on_message = self._on_mqtt_message

    def _on_mqtt_message(self, client, userdata, msg):
        """Callback MQTT: aggiorna la blackboard con i dati ricevuti."""
        try:
            if msg.topic == "robot/vision/ball":
                data = json.loads(msg.payload.decode())
                self.blackboard.set('ball_data', data)

            elif msg.topic == "robot/battery/status":
                data = json.loads(msg.payload.decode())
                level = float(data.get('level', 100.0))
                self.blackboard.set('battery_level', level)

            elif msg.topic == "robot/bumper":
                data = json.loads(msg.payload.decode())
                is_bumped = bool(data.get('is_bumped', False))
                self.blackboard.set('is_bumped', is_bumped)

        except Exception as e:
            print(f"[ToBlackboard] MQTT message error: {e}")

    def update(self):
        """Ritorna sempre SUCCESS: la sincronizzazione avviene nelle callback."""
        return py_trees.common.Status.SUCCESS
