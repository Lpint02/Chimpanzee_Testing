# Guida Deploy: Robot Split Architecture (Jetson Nano)

Questa guida spiega passo-passo come avviare il sistema **Brain (Python) & Body (ROS2)** sul Jetson Nano.

**Prerequisiti**:

- Jetson Nano con Ubuntu 18.04.
- Repository clonata in `~/ros2_x_robot` (o percorso analogo).
- Docker e Docker Compose installati.

---

## 1. Pulizia e Costruzione

Prima di iniziare, assicuriamoci che le immagini siano aggiornate e pulite.

```bash
cd ~/ros2_x_robot

# 1. Ferma eventuali container attivi
docker-compose down

# 2. Ricostruisci le immagini (IMPORTANTE per OpenCV e dipendenze)
# Nota: Su Jetson Nano la build di OpenCV può impiegare 15-20 minuti la prima volta.
docker-compose build
```

---

## 2. Avvio del Sistema (Modalità Sviluppo)

In questa modalità, avviamo i container in background e poi entriamo manualmente nei terminali per lanciare i programmi. È il metodo consigliato per testare e debuggare.

### Passo A: Accendi i Container

```bash
docker-compose up -d
```

Attendi qualche secondo. Verifica che siano tutti "Up":

```bash
docker ps
# Dovresti vedere: ros2, py310, mosquitto
```

### Passo B: Avvia il Body (ROS2 Bridge)

Il container ROS2 usa ora `start.sh` come entrypoint, quindi l'ambiente è già caricato!

1. Entra nel container:
   ```bash
   docker exec -it ros2 bash
   ```
2. Lancia il bridge (ponti ROS <-> MQTT):

   ```bash
   # Abbiamo creato un alias comodo per te:
   run_bridge

   # O se preferisci il comando lungo:
   # ros2 run mqtt_bridge bridge_node
   ```

   _Output atteso:_ `[INFO]: Connecting to MQTT Broker at localhost:1883... Connected`

### Passo C: Avvia il Brain (Visione)

Questo script processa le immagini dalla telecamera.

1. Apri un **nuovo terminale** (su Jetson o SSH):
2. Entra nel container Python:
   ```bash
   docker exec -it py310 bash
   ```
3. Lancia il detector:
   ```bash
   python3 detector.py
   ```
   _Output atteso:_ `Detector Connected to MQTT...`

### Passo D: Avvia il Brain (Decisioni)

Questo script esegue il Behavior Tree (Logica).

1. Apri un **terzo terminale**:
2. Entra di nuovo nel container Python:
   ```bash
   docker exec -it py310 bash
   ```
3. Lancia il cervello principale:
   ```bash
   python3 main.py
   ```
   _Output atteso:_ `Brain Running...`

---

## 3. Modalità Produzione (Avvio Automatico)

Se vuoi che il robot parta automaticamente all'accensione (senza aprire terminali):

1. Modifica `ros2_x_robot/docker-compose.yml`.
2. Cerca la sezione `ros2_img`.
3. Cambia l'ultima riga `command`:

   ```yaml
   # PRIMA:
   command: tail -f /dev/null

   # DOPO:
   command: ros2 run mqtt_bridge bridge_node
   ```

4. Fai lo stesso per `python310` (opzionale, richiederebbe uno script per lanciare entrambi i python).
5. Riavvia: `docker-compose up -d`. Il robot partirà e inizierà a lavorare da solo.

---

## 4. Risoluzione Problemi

**Il robot non si muove o non vede nulla?**
Controlla se i messaggi MQTT stanno passando.

1. Apri un terminale e ascolta tutto il traffico:
   ```bash
   docker exec -it mosquitto mosquitto_sub -t "robot/#" -v
   ```
2. Se vedi scorrere dati incomprensibili (Base64), la telecamera funziona.
3. Se vedi JSON tipo `{"linear": 0.5...}`, il comandi di movimento funzionano.

**Errore "Connection Refused"?**
Assicurati che `mosquitto` sia il primo container a partire (check `docker ps`).
