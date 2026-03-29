#!/usr/bin/env python3
"""
web_viewer.py - Browser-based debug viewer per il robot.
Mostra video debug (robot/camera/debug) + dati MQTT in tempo reale.
Avviare sulla Jetson, aprire dal PC: http://192.168.222.37:5000
"""
import base64
import json
import threading
import time
from flask import Flask, Response, render_template_string
import paho.mqtt.client as mqtt
import os

app = Flask(__name__)

# Stato condiviso
state = {
    "frame_b64": None,
    "vision": {},
    "cmd_vel": {},
    "battery": {},
    "bumper": {},
    "last_update": 0
}
state_lock = threading.Lock()

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

HTML = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Robot Debug Viewer</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700&display=swap');

  :root {
    --bg: #0a0c0f;
    --panel: #0f1318;
    --border: #1e2d40;
    --accent: #00d4ff;
    --accent2: #ff4444;
    --accent3: #00ff88;
    --warn: #ffaa00;
    --text: #c8d8e8;
    --dim: #4a6070;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    min-height: 100vh;
    padding: 16px;
  }

  header {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 12px;
  }

  header h1 {
    font-family: 'Orbitron', monospace;
    font-size: 1.1rem;
    color: var(--accent);
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }

  .status-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--accent3);
    box-shadow: 0 0 8px var(--accent3);
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 16px;
    height: calc(100vh - 80px);
  }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    overflow: hidden;
  }

  .panel-header {
    background: var(--border);
    padding: 6px 12px;
    font-family: 'Orbitron', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    color: var(--accent);
    text-transform: uppercase;
  }

  /* Video */
  #video-panel {
    display: flex;
    flex-direction: column;
  }

  #video-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #050608;
    position: relative;
  }

  #frame {
    max-width: 100%;
    max-height: 100%;
    image-rendering: pixelated;
  }

  #no-signal {
    color: var(--dim);
    font-size: 0.8rem;
    letter-spacing: 0.2em;
  }

  /* Sidebar */
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
  }

  /* Data cards */
  .data-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
  }

  .data-card .panel-header { margin-bottom: 0; }

  .data-rows { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }

  .data-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.78rem;
  }

  .data-label { color: var(--dim); }

  .data-value {
    color: var(--accent);
    font-weight: bold;
  }

  .data-value.real  { color: var(--accent3); }
  .data-value.ghost { color: var(--warn); }
  .data-value.lost  { color: var(--accent2); }
  .data-value.warn  { color: var(--warn); }
  .data-value.danger { color: var(--accent2); }

  /* Battery bar */
  .battery-bar-bg {
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    margin-top: 4px;
    overflow: hidden;
  }

  .battery-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
  }

  /* Mode badge */
  .mode-badge {
    padding: 2px 8px;
    border-radius: 2px;
    font-size: 0.75rem;
    font-weight: bold;
    letter-spacing: 0.1em;
  }

  .mode-real  { background: rgba(0,255,136,0.15); color: var(--accent3); border: 1px solid var(--accent3); }
  .mode-ghost { background: rgba(255,170,0,0.15);  color: var(--warn);    border: 1px solid var(--warn); }
  .mode-lost  { background: rgba(255,68,68,0.15);  color: var(--accent2); border: 1px solid var(--accent2); }

  /* Log */
  #log {
    padding: 8px 12px;
    font-size: 0.7rem;
    color: var(--dim);
    height: 140px;
    overflow-y: auto;
    display: flex;
    flex-direction: column-reverse;
  }

  #log .log-line { margin-bottom: 2px; }
  #log .log-line span { color: var(--accent); margin-right: 6px; }

  /* Crosshair overlay */
  #crosshair {
    position: absolute;
    pointer-events: none;
    width: 100%; height: 100%;
    top: 0; left: 0;
  }
</style>
</head>
<body>

<header>
  <div class="status-dot" id="dot"></div>
  <h1>Robot Debug Viewer</h1>
  <span style="color:var(--dim);font-size:0.7rem;margin-left:auto">10Hz</span>
</header>

<div class="grid">

  <!-- VIDEO -->
  <div class="panel" id="video-panel">
    <div class="panel-header">CAMERA FEED — robot/camera/debug</div>
    <div id="video-container">
      <img id="frame" style="display:none"/>
      <div id="no-signal">⬛ NO SIGNAL</div>
      <svg id="crosshair" viewBox="0 0 320 240" preserveAspectRatio="none">
        <line x1="160" y1="0" x2="160" y2="240" stroke="#00d4ff22" stroke-width="0.5"/>
        <line x1="0" y1="120" x2="320" y2="120" stroke="#00d4ff22" stroke-width="0.5"/>
        <circle cx="160" cy="120" r="20" fill="none" stroke="#00d4ff22" stroke-width="0.5"/>
        <circle id="ball-dot" cx="-99" cy="-99" r="6" fill="none" stroke="#00ff88" stroke-width="1.5"/>
      </svg>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">

    <!-- VISION -->
    <div class="data-card">
      <div class="panel-header">VISION — robot/vision/ball</div>
      <div class="data-rows">
        <div class="data-row">
          <span class="data-label">MODE</span>
          <span id="v-mode" class="mode-badge mode-lost">LOST</span>
        </div>
        <div class="data-row">
          <span class="data-label">CX / CY</span>
          <span class="data-value" id="v-pos">—</span>
        </div>
        <div class="data-row">
          <span class="data-label">AREA</span>
          <span class="data-value" id="v-area">—</span>
        </div>
        <div class="data-row">
          <span class="data-label">VX / VY</span>
          <span class="data-value" id="v-vel">—</span>
        </div>
      </div>
    </div>

    <!-- CMD_VEL -->
    <div class="data-card">
      <div class="panel-header">CMD VEL — robot/cmd_vel</div>
      <div class="data-rows">
        <div class="data-row">
          <span class="data-label">LINEAR</span>
          <span class="data-value" id="c-lin">—</span>
        </div>
        <div class="data-row">
          <span class="data-label">ANGULAR</span>
          <span class="data-value" id="c-ang">—</span>
        </div>
      </div>
    </div>

    <!-- BATTERY -->
    <div class="data-card">
      <div class="panel-header">BATTERY — robot/battery/status</div>
      <div class="data-rows">
        <div class="data-row">
          <span class="data-label">LEVEL</span>
          <span class="data-value" id="b-level">—</span>
        </div>
        <div class="battery-bar-bg">
          <div class="battery-bar-fill" id="b-bar" style="width:0%;background:var(--accent3)"></div>
        </div>
        <div class="data-row">
          <span class="data-label">VOLTAGE</span>
          <span class="data-value" id="b-volt">—</span>
        </div>
      </div>
    </div>

    <!-- BUMPER -->
    <div class="data-card">
      <div class="panel-header">BUMPER — robot/bumper</div>
      <div class="data-rows">
        <div class="data-row">
          <span class="data-label">STATUS</span>
          <span class="data-value" id="bump-status">—</span>
        </div>
      </div>
    </div>

    <!-- LOG -->
    <div class="data-card" style="flex:1">
      <div class="panel-header">EVENT LOG</div>
      <div id="log"></div>
    </div>

  </div>
</div>

<script>
  const log = document.getElementById('log');
  let logLines = [];

  function addLog(msg, color) {
    const now = new Date().toTimeString().slice(0,8);
    logLines.unshift({time: now, msg, color});
    if (logLines.length > 50) logLines.pop();
    log.innerHTML = logLines.map(l =>
      `<div class="log-line"><span>${l.time}</span><span style="color:${l.color||'var(--text)'}">${l.msg}</span></div>`
    ).join('');
  }

  function poll() {
    fetch('/state')
      .then(r => r.json())
      .then(data => {
        updateUI(data);
        setTimeout(poll, 100);
      })
      .catch(() => setTimeout(poll, 500));
  }

  let lastMode = null;
  let lastBumped = null;

  function updateUI(data) {
    // Frame
    if (data.frame) {
      const img = document.getElementById('frame');
      img.src = 'data:image/jpeg;base64,' + data.frame;
      img.style.display = 'block';
      document.getElementById('no-signal').style.display = 'none';
    }

    // Vision
    const v = data.vision || {};
    if (v.mode !== undefined) {
      const modeEl = document.getElementById('v-mode');
      modeEl.textContent = (v.mode || 'lost').toUpperCase();
      modeEl.className = 'mode-badge mode-' + (v.mode || 'lost');

      if (v.mode !== lastMode) {
        const colors = {real: 'var(--accent3)', ghost: 'var(--warn)', lost: 'var(--accent2)'};
        addLog('MODE → ' + v.mode.toUpperCase(), colors[v.mode]);
        lastMode = v.mode;
      }

      // Ball dot on crosshair
      if (v.cx > 0 && v.mode !== 'lost') {
        const dot = document.getElementById('ball-dot');
        dot.setAttribute('cx', v.cx * 320 / 640);
        dot.setAttribute('cy', v.cy * 240 / 480);
        dot.setAttribute('stroke', v.mode === 'real' ? '#00ff88' : '#ffaa00');
      }
    }

    document.getElementById('v-pos').textContent =
      v.cx !== undefined ? `${v.cx} / ${v.cy}` : '—';
    document.getElementById('v-area').textContent =
      v.area !== undefined ? (v.area < 0 ? '—' : v.area.toFixed(0)) : '—';
    document.getElementById('v-vel').textContent =
      v.vx !== undefined ? `${v.vx.toFixed(1)} / ${v.vy.toFixed(1)}` : '—';

    // CMD_VEL
    const c = data.cmd_vel || {};
    const linEl = document.getElementById('c-lin');
    const angEl = document.getElementById('c-ang');
    if (c.linear !== undefined) {
      linEl.textContent = c.linear.toFixed(3);
      linEl.className = 'data-value' + (c.linear !== 0 ? ' real' : '');
    }
    if (c.angular !== undefined) {
      angEl.textContent = c.angular.toFixed(3);
      angEl.className = 'data-value' + (Math.abs(c.angular) > 0.1 ? ' warn' : '');
    }

    // Battery
    const b = data.battery || {};
    if (b.level !== undefined) {
      const pct = Math.round(b.level);
      document.getElementById('b-level').textContent = pct + '%';
      const bar = document.getElementById('b-bar');
      bar.style.width = pct + '%';
      bar.style.background = pct < 20 ? 'var(--accent2)' : pct < 40 ? 'var(--warn)' : 'var(--accent3)';
      document.getElementById('b-level').className =
        'data-value' + (pct < 20 ? ' danger' : pct < 40 ? ' warn' : '');
    }
    if (b.voltage !== undefined) {
      document.getElementById('b-volt').textContent = b.voltage.toFixed(2) + ' V';
    }

    // Bumper
    const bump = data.bumper || {};
    if (bump.is_bumped !== undefined) {
      const el = document.getElementById('bump-status');
      el.textContent = bump.is_bumped ? '⚠ BUMPED' : 'CLEAR';
      el.className = 'data-value' + (bump.is_bumped ? ' danger' : ' real');
      if (bump.is_bumped !== lastBumped) {
        if (bump.is_bumped) addLog('⚠ BUMPER HIT!', 'var(--accent2)');
        lastBumped = bump.is_bumped;
      }
    }
  }

  poll();
  addLog('Viewer started', 'var(--accent)');
</script>
</body>
</html>
"""

# ── MQTT ──────────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    print(f"MQTT connected: {rc}")
    client.subscribe("robot/camera/debug")
    client.subscribe("robot/vision/ball")
    client.subscribe("robot/cmd_vel")
    client.subscribe("robot/battery/status")
    client.subscribe("robot/bumper")

def on_message(client, userdata, msg):
    topic = msg.topic
    with state_lock:
        state["last_update"] = time.time()
        if topic == "robot/camera/debug":
            state["frame_b64"] = msg.payload.decode()
        elif topic == "robot/vision/ball":
            state["vision"] = json.loads(msg.payload)
        elif topic == "robot/cmd_vel":
            state["cmd_vel"] = json.loads(msg.payload)
        elif topic == "robot/battery/status":
            raw = json.loads(msg.payload)
            # Normalize: ROS2 bridge publishes 'percentage' (0.0-1.0),
            # but the dashboard expects 'level' (0-100).
            percentage = raw.get('percentage', raw.get('level', 0))
            state["battery"] = {"level": round(percentage * 100, 1)}
        elif topic == "robot/bumper":
            state["bumper"] = json.loads(msg.payload)

def mqtt_thread():
    client = mqtt.Client(client_id="web_viewer")
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print(f"MQTT error: {e}, retry in 3s")
            time.sleep(3)

# ── Flask routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/state')
def get_state():
    with state_lock:
        return {
            "frame": state["frame_b64"],
            "vision": state["vision"],
            "cmd_vel": state["cmd_vel"],
            "battery": state["battery"],
            "bumper": state["bumper"],
        }

if __name__ == '__main__':
    t = threading.Thread(target=mqtt_thread, daemon=True)
    t.start()
    print("Web viewer at http://0.0.0.0:5000")
    print(f"MQTT broker: {MQTT_HOST}:{MQTT_PORT}")
    app.run(host='0.0.0.0', port=5000, debug=False)
