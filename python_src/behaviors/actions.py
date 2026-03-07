#!/usr/bin/env python3
"""
actions.py - Nodi azione per il behavior tree del robot.

Definisce le azioni eseguibili dal robot:
- CheckAndUndock: distacco dalla stazione di ricarica via MQTT
- BackUpAndRotate: manovra di recovery dopo collisione
- FollowBall: inseguimento palla reale con PID
- SearchBall: rotazione in cerca della palla
- TrackGhost: inseguimento predittivo con feedforward Kalman
- ReturnToBase: ritorno alla base di ricarica via dock
"""
import py_trees
import paho.mqtt.client as mqtt
import json
import time
import random
import os


class BackUpAndRotate(py_trees.behaviour.Behaviour):
    """
    Azione di recovery: indietreggia e ruota in direzione casuale.
    Scrive is_recovering e cmd_vel sulla blackboard.
    """

    def __init__(self, name="BackUpAndRotate"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='is_recovering', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.WRITE
        )

        self.start_time = None
        self.backup_duration = 1.0
        self.rotate_duration = 1.5
        self.random_turn_speed = 0.0

    def initialise(self):
        self.start_time = time.time()
        self.blackboard.set('is_recovering', True)
        direction = 1 if random.random() > 0.5 else -1
        self.random_turn_speed = direction * 1.0
        print("STARTING RECOVERY: BackUp")

    def update(self):
        elapsed = time.time() - self.start_time

        linear_x = 0.0
        angular_z = 0.0

        if elapsed < self.backup_duration:
            linear_x = -0.15
        elif elapsed < (self.backup_duration + self.rotate_duration):
            linear_x = -0.15
            angular_z = self.random_turn_speed
        else:
            self.blackboard.set('is_recovering', False)
            print("RECOVERY COMPLETED")
            return py_trees.common.Status.SUCCESS

        # Scrivi comando sulla blackboard per il main loop
        self.blackboard.set('cmd_vel', {'linear': linear_x, 'angular': angular_z})
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


class FollowBall(py_trees.behaviour.Behaviour):
    """
    Inseguimento palla reale con controllo PID.
    Legge ball_data dalla blackboard (cx, area).
    Scrive cmd_vel sulla blackboard.
    """

    def __init__(self, name="FollowBall"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.WRITE
        )

    def update(self):
        try:
            ball_data = self.blackboard.get('ball_data')
        except KeyError:
            return py_trees.common.Status.FAILURE

        if ball_data is None:
            return py_trees.common.Status.FAILURE

        cx = ball_data.get('cx', -1)
        area = ball_data.get('area', 0)

        if cx < 0:
            return py_trees.common.Status.FAILURE

        # Logica PID
        image_center = 320
        error = cx - image_center
        Kp = 0.002
        angular_z = -Kp * float(error)

        target_area = 20000
        linear_x = 0.2 if area < target_area else 0.0

        # Invia comando via Blackboard
        self.blackboard.set('cmd_vel', {'linear': linear_x, 'angular': angular_z})

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


class SearchBall(py_trees.behaviour.Behaviour):
    """
    Rotazione in cerca della palla.
    Scrive cmd_vel sulla blackboard con velocità angolare costante.
    """

    def __init__(self, name="SearchBall"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.WRITE
        )

    def update(self):
        # Ruota in cerca della palla
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.5})
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


class TrackGhost(py_trees.behaviour.Behaviour):
    """
    Inseguimento predittivo della palla in modalità ghost.

    Usa lo stesso PID di FollowBall per l'errore angolare, con
    correzione feedforward sulla velocità angolare usando vx dal Kalman:
      angular_z = -Kp * error + Kv * vx

    Kp = 0.002, Kv = 0.001
    """

    def __init__(self, name="TrackGhost"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.WRITE
        )

        self.Kp = 0.002
        self.Kv = 0.001

    def update(self):
        try:
            ball_data = self.blackboard.get('ball_data')
        except KeyError:
            return py_trees.common.Status.FAILURE

        if ball_data is None:
            return py_trees.common.Status.FAILURE

        cx = ball_data.get('cx', -1)
        vx = ball_data.get('vx', 0.0)

        if cx < 0:
            return py_trees.common.Status.FAILURE

        # PID + Feedforward
        image_center = 320
        error = cx - image_center
        angular_z = -self.Kp * float(error) + self.Kv * float(vx)

        # Avanzamento ridotto in modalità ghost
        linear_x = 0.1

        self.blackboard.set('cmd_vel', {'linear': linear_x, 'angular': angular_z})

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


class ReturnToBase(py_trees.behaviour.Behaviour):
    """
    Azione di ritorno alla base di ricarica.

    1. Pubblica su MQTT 'robot/cmd/dock' il messaggio 'trigger'
    2. Attende conferma su 'robot/undock/result' == 'success' (timeout 30s)
    3. Scrive is_undocked=False sulla blackboard e ritorna SUCCESS
    """

    def __init__(self, name="ReturnToBase"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='is_undocked', access=py_trees.common.Access.WRITE
        )
        self.blackboard.register_key(
            key='cmd_vel', access=py_trees.common.Access.WRITE
        )

        # Config MQTT
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))

        self.dock_client = mqtt.Client(client_id="brain_dock")
        self.dock_confirmed = False
        self.trigger_sent = False
        self.dock_start_time = 0

        try:
            self.dock_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.dock_client.subscribe("robot/dock/result")
            self.dock_client.on_message = self._on_dock_message
            self.dock_client.loop_start()
        except Exception as e:
            print(f"[ReturnToBase] MQTT Error: {e}")

    def _on_dock_message(self, client, userdata, msg):
        """Callback per il risultato del docking."""
        try:
            if msg.topic == "robot/dock/result":
                payload = msg.payload.decode()
                print(f"[ReturnToBase] Dock Result: {payload}")
                if payload == "success":
                    self.dock_confirmed = True
        except Exception as e:
            print(f"[ReturnToBase] Message Error: {e}")

    def initialise(self):
        """Reset stato ad ogni nuova esecuzione."""
        self.dock_confirmed = False
        self.trigger_sent = False
        self.dock_start_time = 0
        # Ferma il robot
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})

    def update(self):
        # Se dock confermato
        if self.dock_confirmed:
            self.blackboard.set('is_undocked', False)
            print("[ReturnToBase] Docking completed!")
            return py_trees.common.Status.SUCCESS

        # Invia trigger se non ancora inviato
        if not self.trigger_sent:
            print("[ReturnToBase] Triggering Dock Action via MQTT...")
            self.dock_client.publish("robot/cmd/dock", json.dumps("trigger"))
            self.trigger_sent = True
            self.dock_start_time = time.time()
            return py_trees.common.Status.RUNNING

        # Timeout 30 secondi
        if (time.time() - self.dock_start_time) > 30.0:
            print("[ReturnToBase] Dock Timeout! Force success.")
            self.blackboard.set('is_undocked', False)
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


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
