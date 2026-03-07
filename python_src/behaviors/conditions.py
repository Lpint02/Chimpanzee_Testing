#!/usr/bin/env python3
"""
conditions.py - Nodi condizione per il behavior tree del robot.

Definisce le condizioni che guidano la logica decisionale:
- BallDetectedCondition: palla reale rilevata con area sufficiente
- IsTargetGhost: palla in modalità ghost (predizione Kalman)
- IsBatteryLow: livello batteria sotto soglia configurabile
- IsRecoveringOrBumperDetected: bumper attivo o stato di recovery
"""
import py_trees


class BallDetectedCondition(py_trees.behaviour.Behaviour):
    """
    Condition: SUCCESS se la palla è rilevata in modalità 'real'
    con area > 500. Legge ball_data dalla blackboard.
    """

    def __init__(self, name="BallDetectedCondition"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.READ
        )

    def update(self):
        try:
            ball_data = self.blackboard.get('ball_data')
        except KeyError:
            return py_trees.common.Status.FAILURE

        if ball_data is None:
            return py_trees.common.Status.FAILURE

        mode = ball_data.get('mode', 'lost')
        area = ball_data.get('area', 0)

        if mode == "real" and area > 500:
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.FAILURE


class IsTargetGhost(py_trees.behaviour.Behaviour):
    """
    Condition: SUCCESS se la palla è in modalità 'ghost'
    (predizione Kalman attiva, nessun rilevamento diretto).
    Legge ball_data dalla blackboard.
    """

    def __init__(self, name="IsTargetGhost"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='ball_data', access=py_trees.common.Access.READ
        )

    def update(self):
        try:
            ball_data = self.blackboard.get('ball_data')
        except KeyError:
            return py_trees.common.Status.FAILURE

        if ball_data is None:
            return py_trees.common.Status.FAILURE

        mode = ball_data.get('mode', 'lost')

        if mode == "ghost":
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.FAILURE


class IsBatteryLow(py_trees.behaviour.Behaviour):
    """
    Condition: SUCCESS se battery_level < soglia (default 20.0).
    Legge battery_level dalla blackboard.
    La soglia è configurabile nel costruttore.
    """

    def __init__(self, name="IsBatteryLow", threshold=20.0):
        super().__init__(name)
        self.threshold = threshold
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='battery_level', access=py_trees.common.Access.READ
        )

    def update(self):
        try:
            battery_level = self.blackboard.get('battery_level')
        except KeyError:
            return py_trees.common.Status.FAILURE

        if battery_level is None:
            return py_trees.common.Status.FAILURE

        if float(battery_level) < self.threshold:
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.FAILURE


class IsRecoveringOrBumperDetected(py_trees.behaviour.Behaviour):
    """
    Condition: SUCCESS se il bumper è attivo oppure il robot
    è già in stato di recovery. Legge is_recovering e is_bumped
    dalla blackboard.
    """

    def __init__(self, name="IsRecoveringOrBumperDetected"):
        super().__init__(name)
        self.blackboard = self.attach_blackboard_client(
            name=self.__class__.__name__
        )
        self.blackboard.register_key(
            key='is_recovering', access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key='is_bumped', access=py_trees.common.Access.READ
        )

    def update(self):
        # Check se stiamo già recuperando
        try:
            is_recovering = self.blackboard.get('is_recovering')
            if is_recovering:
                return py_trees.common.Status.SUCCESS
        except KeyError:
            pass

        # Check bumper attivo
        try:
            is_bumped = self.blackboard.get('is_bumped')
            if is_bumped:
                return py_trees.common.Status.SUCCESS
        except KeyError:
            pass

        return py_trees.common.Status.FAILURE
