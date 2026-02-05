#!/usr/bin/env python3
import py_trees
import time
import random

# Helper per inviare comandi via MQTT (verrà iniettato o usato via callback)
# Per semplicità, scriviamo sulla blackboard un "cmd_request" che il main loop legge e invia.

class BackUpAndRotate(py_trees.behaviour.Behaviour):
    def __init__(self, name):
        super(BackUpAndRotate, self).__init__(name)
        self.blackboard = self.attach_blackboard_client(name=self.__class__.__name__)
        self.blackboard.register_key(key='is_recovering', access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key='cmd_vel', access=py_trees.common.Access.WRITE)
        
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
    def __init__(self, name):
        super(FollowBall, self).__init__(name)
        self.blackboard = self.attach_blackboard_client(name=self.__class__.__name__)
        self.blackboard.register_key(key='ball_position', access=py_trees.common.Access.READ)
        self.blackboard.register_key(key='cmd_vel', access=py_trees.common.Access.WRITE)
    
    def update(self):
        try:
            ball_pos = self.blackboard.get('ball_position')
        except KeyError:
            return py_trees.common.Status.FAILURE
        
        if ball_pos is None:
            return py_trees.common.Status.FAILURE
        
        cx = ball_pos['x']
        area = ball_pos['area']
        
        # Logica PID Identica a prima
        image_center = 320
        error = cx - image_center
        Kp = 0.002
        angular_z = -Kp * float(error)
        
        target_area = 20000
        linear_x = 0.2 if area < target_area else 0.0
        
        # Invia comando al Main Loop via Blackboard
        self.blackboard.set('cmd_vel', {'linear': linear_x, 'angular': angular_z})
        
        # print(f"follow: err={error} area={area}")
        return py_trees.common.Status.RUNNING
    
    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})


class SearchBall(py_trees.behaviour.Behaviour):
    def __init__(self, name):
        super(SearchBall, self).__init__(name)
        self.blackboard = self.attach_blackboard_client(name=self.__class__.__name__)
        self.blackboard.register_key(key='cmd_vel', access=py_trees.common.Access.WRITE)
    
    def update(self):
        # Ruota in cerca della palla
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.5})
        return py_trees.common.Status.RUNNING
    
    def terminate(self, new_status):
        self.blackboard.set('cmd_vel', {'linear': 0.0, 'angular': 0.0})
