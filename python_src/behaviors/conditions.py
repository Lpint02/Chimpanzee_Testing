#!/usr/bin/env python3
import py_trees

class BallDetectedCondition(py_trees.behaviour.Behaviour):
    """
    Condition: Ritorna SUCCESS se la palla è rilevata e abbastanza vicina.
    Legge dalla blackboard popolata via MQTT.
    """
    def __init__(self, name):
        super(BallDetectedCondition, self).__init__(name)
        self.blackboard = self.attach_blackboard_client(name=self.__class__.__name__)
        self.blackboard.register_key(key='ball_data', access=py_trees.common.Access.READ)
        self.blackboard.register_key(key='ball_position', access=py_trees.common.Access.WRITE)
    
    def update(self):
        try:
            # ball_data viene scritto dal main loop MQTT
            # Formato atteso: [cx, area]
            ball_data = self.blackboard.get('ball_data')
        except KeyError:
            return py_trees.common.Status.FAILURE
        
        if ball_data is None or len(ball_data) < 2:
            return py_trees.common.Status.FAILURE
        
        cx, area = ball_data[0], ball_data[1]
        
        # Soglia minima area per considerare rilevamento valido
        if area > 500:
            # print(f"Ball detected: x={cx}, area={area}")
            # Salva posizione processata per action FollowBall
            self.blackboard.set('ball_position', {'x': cx, 'area': area})
            return py_trees.common.Status.SUCCESS
        
        return py_trees.common.Status.FAILURE

# IsRecoveringOrBumperDetected REMOVED as requested by simplified logic, 
# or can be added if Hazard data is bridged. 
# For now, let's keep it simple as user only showed ball detector logic explicitly.
# UPDATE: User mentioned "behaviors/conditions.py" was existing. Let's port it if hazard is bridged.
# Our bridge currently only bridges Image and CmdVel. 
# Hazard bridging was not explicitly added to bridge_node.py yet (my bad). 
# I will comment it out or implement a stub until bridge supports it.

class IsRecoveringOrBumperDetected(py_trees.behaviour.Behaviour):
    """
    Condition: Ritorna SUCCESS se:
    1. Il bumper è attivo (hazard type 1) -> REQUIRES HAZARD BRIDGE
    2. OPPURE siamo già in stato di recovery
    """
    def __init__(self, name):
        super(IsRecoveringOrBumperDetected, self).__init__(name)
        self.blackboard = self.attach_blackboard_client(name=self.__class__.__name__)
        self.blackboard.register_key(key='hazard_data', access=py_trees.common.Access.READ)
        self.blackboard.register_key(key='is_recovering', access=py_trees.common.Access.READ)

    def update(self):
        # 1. Check se stiamo già recuperando
        try:
            is_recovering = self.blackboard.get('is_recovering')
            if is_recovering:
                return py_trees.common.Status.SUCCESS
        except KeyError:
            pass
        
        # 2. Check nuovi bump - TODO: Bridge hazard data
        # For now, always False since we don't have hazard data bridged yet
        return py_trees.common.Status.FAILURE
