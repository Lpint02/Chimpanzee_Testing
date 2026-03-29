# Modifiche effettuate

### Target Lost: Spin verso la direzione in cui perde la palla

**toblackboard.py** — the memory source
Added a last_ball_cx key and, inside \_on_mqtt_message, whenever a ball message arrives with a valid cx (≥ 0, meaning mode is real or ghost with a Kalman estimate), it gets written to the blackboard. This key is never reset to -1 — it permanently holds the last reliable position so SearchBall can read it even after the ball has been lost for a long time.

**main.py** — blackboard registration
Registered last_ball_cx as a writable key and initialized it to -1 (sentinel for "never seen").

**actions.py** — the actual behavior change
SearchBall now has an initialise() method (called once each time the node becomes active) that reads last_ball_cx and picks a spin direction.

### Implementazione Bumper

Only **actions.py** needed to change. Here's a precise summary of the three bugs and their fixes:

**Bug 1 — Infinite recovery loop (the blocker)**
Root cause: is_bumped was never cleared by anyone. The Create 3 bridge typically sends a one-shot True on contact and then goes silent. So once set, is_bumped stayed True on the blackboard forever. After recovery completed and is_recovering was reset to False, IsRecoveringOrBumperDetected still saw is_bumped = True → SUCCESS → BackUpAndRotate.initialise() was called again → endless loop.
**Fix: initialise()** now immediately calls self.blackboard.set('is_bumped', False) — the act of starting recovery atomically acknowledges the bump event. terminate() does the same as a safety net for external interruptions. Added is_bumped WRITE key registration which was also missing.

**Bug 2 — Rotation toward a random direction**
Root cause: BackUpAndRotate used random.random() and didn't even register last_ball_cx as a readable key, making it impossible to use it.
**Fix: initialise()** now reads last_ball_cx and applies the exact same directional logic as SearchBall: right-side loss → negative angular_z (turn right), left-side loss → positive (turn left), never seen → alternates.

**Bug 3 — Rotation duration was 2.0 s instead of ~90°**
Root cause: rotate_duration = 2.0 at 1.0 rad/s = 2.0 rad ≈ 114°, not 90°.
Fix: ROTATE_DURATION = π/2 ÷ 1.0 rad/s ≈ 1.57 s, which gives exactly 90°.

### Batteia in Web Dashboord e BT

The fix needs to happen in on_message in web_viewer.py, normalizing the raw payload into the format the rest of the code expects before storing it in state:

```
elif topic == "robot/battery/status":
raw = json.loads(msg.payload) # Normalize: ROS2 bridge publishes 'percentage' (0.0-1.0), # but the dashboard expects 'level' (0-100).
percentage = raw.get('percentage', raw.get('level', 0))
state["battery"] = {
"level": round(percentage \* 100, 1), # convert to 0-100
"voltage": raw.get('voltage', 0.0)
}
```

And the same fix applies to toblackboard.py:

```
elif msg.topic == "robot/battery/status":
    data = json.loads(msg.payload.decode())
    percentage = data.get('percentage', data.get('level', 1.0))
    level = float(percentage) * 100.0  # convert to 0-100
    self.blackboard.set('battery_level', level)
```

### Modifiche filtro di Kalman

Il **detector_kalman.py** è stato modificato per cercare di farlo funzionare. Ho modificato molto nel codice.

# Cose da testare

1. Far perdere la palla sia a destra che a sinistra per vedere se quando perde il target gira nella direzione in cui perde la palla
2. Tramite la web dashboard vedere se entra on "Ghost Mode" ovvero va ad usare il filtro di Kalman, come faceva in simulazione
3. Vedere se si vede la batteria sulla web dashboard
4. Testare il bumper: se il robot sbatte dovrebbe innescarsi la manovra evasiva che consiste nell'indietreggiare e girarsi verso il lato dove è la palla
