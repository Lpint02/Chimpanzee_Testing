#!/usr/bin/env python3
"""
detector_kalman.py - Rilevatore di pallina rossa con filtro di Kalman.

Sostituisce detector.py. Utilizza lo stesso pipeline HSV (GaussianBlur,
doppio inRange per il rosso, morfologia, findContours) con l'aggiunta
di un filtro di Kalman a velocità costante per stimare e predire la
posizione della pallina anche quando non è visibile (modalità "ghost").

Pubblica su MQTT:
- "robot/vision/ball": dati di tracking JSON {cx, cy, area, vx, vy, mode}
- "robot/camera/debug": frame di debug JPEG base64 (1 ogni 3, 320x240, q30)

Modalità:
- "real":  OpenCV ha trovato la palla questo frame
- "ghost": OpenCV non trova la palla ma < 4s dall'ultima detection (Kalman)
- "lost":  OpenCV non trova la palla da > 4 secondi
"""
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import base64
import json
import os
import time


class KalmanFilter2D:
    """
    Filtro di Kalman 2D a velocità costante.

    Stato: [cx, cy, vx, vy]^T
    Modello: Constant Velocity (dt = 1 frame)
    """

    def __init__(self):
        # Stato iniziale [cx, cy, vx, vy]
        self.x = np.zeros((4, 1), dtype=np.float64)

        # Matrice di transizione (Constant Velocity, dt=1)
        self.F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float64)

        # Matrice di osservazione (misuriamo solo cx, cy)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=np.float64)

        # Covarianza dello stato (iniziale alta = incertezza)
        self.P = np.eye(4, dtype=np.float64) * 1000.0

        # Rumore di processo
        self.Q = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float64) * 0.5

        # Rumore di misura
        self.R = np.array([
            [5, 0],
            [0, 5]
        ], dtype=np.float64)

    def predict(self):
        """Predizione dello stato al passo successivo."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.x.copy()

    def update(self, cx, cy):
        """Aggiornamento con misura osservata (cx, cy)."""
        z = np.array([[cx], [cy]], dtype=np.float64)
        y = z - self.H @ self.x                      # Innovazione
        S = self.H @ self.P @ self.H.T + self.R      # Covarianza innovazione
        K = self.P @ self.H.T @ np.linalg.inv(S)     # Guadagno di Kalman
        self.x = self.x + K @ y
        I = np.eye(4, dtype=np.float64)
        self.P = (I - K @ self.H) @ self.P
        return self.x.copy()

    def get_state(self):
        """Ritorna lo stato corrente [cx, cy, vx, vy] come lista."""
        return self.x.flatten().tolist()

    def get_velocity(self):
        """Ritorna la velocità stimata (vx, vy)."""
        return float(self.x[2, 0]), float(self.x[3, 0])


class BallDetectorKalman:
    """
    Rilevatore di pallina rossa con filtro di Kalman integrato.

    Pipeline di visione identico al detector.py originale:
    GaussianBlur 11x11, doppio range HSV per il rosso, morfologia 5x5.

    Aggiunge tracking predittivo tramite Kalman filter per mantenere
    la stima della posizione anche durante occlusioni temporanee.
    """

    def __init__(self):
        # Config MQTT
        self.mqtt_host = os.environ.get('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.environ.get('MQTT_PORT', 1883))

        self.client = mqtt.Client(client_id="ball_detector")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # Parametri Visione (IDENTICI al detector.py originale)
        # Range 1: 0-10 (Rosso-Arancio)
        self.lower_red1 = np.array([0, 130, 70])
        self.upper_red1 = np.array([10, 255, 255])

        # Range 2: 170-180 (Rosso-Viola)
        self.lower_red2 = np.array([170, 130, 70])
        self.upper_red2 = np.array([180, 255, 255])

        self.min_area = 500

        # Kalman Filter
        self.kf = KalmanFilter2D()
        self.last_detection_time = 0.0
        self.ghost_timeout = 4.0  # secondi prima di dichiarare "lost"
        self.kf_initialized = False

        # Frame counter per debug stream
        self.frame_count = 0

        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            print(f"Detector Kalman Connected to MQTT at {self.mqtt_host}")
        except Exception as e:
            print(f"Detector Kalman Connection Failed: {e}")

    def on_connect(self, client, userdata, flags, rc):
        """Callback connessione MQTT."""
        print(f"Detector Kalman Connected with result code {rc}")
        client.subscribe("robot/camera")

    def on_message(self, client, userdata, msg):
        """Callback ricezione messaggi MQTT."""
        if msg.topic == "robot/camera":
            try:
                self.process_image(msg.payload)
            except Exception as e:
                print(f"Detector on_message Error: {e}")

    def process_image(self, payload):
        """Elabora frame camera: HSV detection + Kalman tracking."""
        try:
            # Decode Base64 -> Bytes -> Numpy -> Image
            img_data = base64.b64decode(payload)
            np_arr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                print("Frame decode FAILED")
                return

            # ======== PIPELINE HSV IDENTICO ========
            # Gaussian Blur per ridurre il rumore
            blurred = cv2.GaussianBlur(frame, (11, 11), 0)

            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

            # Thresholding combinato (Range 1 + Range 2)
            mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
            mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
            mask = cv2.bitwise_or(mask1, mask2)

            # Morfologia
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            # Contorni
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            # ======== FINE PIPELINE HSV ========

            # Variabili di rilevamento OpenCV
            detected = False
            raw_cx = -1
            raw_cy = -1
            area = 0.0
            largest_contour = None

            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest_contour)

                if area > self.min_area:
                    M = cv2.moments(largest_contour)
                    if M['m00'] > 0:
                        raw_cx = int(M['m10'] / M['m00'])
                        raw_cy = int(M['m01'] / M['m00'])
                        detected = True

            # ======== KALMAN FILTER ========
            now = time.time()

            if detected:
                # Aggiorna Kalman con misura reale
                if not self.kf_initialized:
                    self.kf.x = np.array(
                        [[raw_cx], [raw_cy], [0], [0]], dtype=np.float64
                    )
                    self.kf.P = np.eye(4, dtype=np.float64) * 100.0
                    self.kf_initialized = True
                else:
                    self.kf.predict()
                    self.kf.update(raw_cx, raw_cy)

                self.last_detection_time = now
                mode = "real"
            else:
                # Nessuna detection OpenCV
                if (self.kf_initialized
                        and (now - self.last_detection_time) < self.ghost_timeout):
                    self.kf.predict()
                    mode = "ghost"
                else:
                    mode = "lost"

            # Estrai stato Kalman
            state = self.kf.get_state()
            vx, vy = self.kf.get_velocity()
            est_cx = int(state[0]) if self.kf_initialized else -1
            est_cy = int(state[1]) if self.kf_initialized else -1

            # Area: -1.0 se ghost/lost
            publish_area = float(area) if mode == "real" else -1.0

            # ======== PUBBLICA RISULTATO ========
            result_payload = json.dumps({
                "cx": est_cx,
                "cy": est_cy,
                "area": publish_area,
                "vx": round(vx, 4),
                "vy": round(vy, 4),
                "mode": mode
            })
            self.client.publish("robot/vision/ball", result_payload)

            # ======== DEBUG VISUALIZATION ========
            debug_frame = frame.copy()

            if mode == "real" and largest_contour is not None:
                # Bounding rect verde + centro blu + testo area
                x, y, w, h = cv2.boundingRect(largest_contour)
                cv2.rectangle(debug_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(debug_frame, (est_cx, est_cy), 5, (255, 0, 0), -1)
                cv2.putText(
                    debug_frame, f"A:{int(area)} X:{est_cx}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
                )

            elif mode == "ghost":
                # Cerchio giallo tratteggiato sulla posizione predetta
                self._draw_dashed_circle(
                    debug_frame, (est_cx, est_cy), 30, (0, 255, 255), 2
                )
                cv2.putText(
                    debug_frame, f"GHOST X:{est_cx}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
                )

            elif mode == "lost":
                # Testo rosso "TARGET LOST"
                cv2.putText(
                    debug_frame, "TARGET LOST",
                    (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3
                )

            # Invia debug stream (1 frame ogni 3, ridimensionato, compresso)
            self.frame_count += 1
            if self.frame_count % 3 == 0:
                small_debug = cv2.resize(debug_frame, (320, 240))
                _, buffer = cv2.imencode(
                    '.jpg', small_debug, [int(cv2.IMWRITE_JPEG_QUALITY), 30]
                )
                debug_b64 = base64.b64encode(buffer)
                self.client.publish("robot/camera/debug", debug_b64)

            time.sleep(0.05)

        except Exception as e:
            print(f"Vision Kalman Error: {e}")

    def _draw_dashed_circle(self, img, center, radius, color, thickness,
                            dash_length=10):
        """Disegna un cerchio tratteggiato su img."""
        circumference = int(2 * np.pi * radius)
        num_dashes = max(1, circumference // (dash_length * 2))
        angle_step = 360.0 / (num_dashes * 2)
        for i in range(num_dashes):
            start_angle = int(i * angle_step * 2)
            end_angle = int(start_angle + angle_step)
            cv2.ellipse(
                img, center, (radius, radius), 0,
                start_angle, end_angle, color, thickness
            )


if __name__ == '__main__':
    detector = BallDetectorKalman()
    while True:
        time.sleep(1)
