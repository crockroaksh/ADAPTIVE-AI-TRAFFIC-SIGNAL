# 🚦 ESP32 DOIT DEVKIT V1 Traffic Signal Controller

Firmware and hardware documentation for integrating the physical 12-LED traffic signal intersection model with the Adaptive AI Traffic Control system.

---

## 📌 GPIO Pin Mapping

| Intersection Approach | Signal Color | ESP32 GPIO Pin | Resistor | Breadboard Wire Color |
| :--- | :--- | :--- | :--- | :--- |
| **NORTH** | **RED** | **GPIO 13** | 220Ω – 330Ω | Red |
| **NORTH** | **YELLOW** | **GPIO 12** | 220Ω – 330Ω | Yellow |
| **NORTH** | **GREEN** | **GPIO 14** | 220Ω – 330Ω | Green |
| **SOUTH** | **RED** | **GPIO 27** | 220Ω – 330Ω | Red |
| **SOUTH** | **YELLOW** | **GPIO 26** | 220Ω – 330Ω | Yellow |
| **SOUTH** | **GREEN** | **GPIO 25** | 220Ω – 330Ω | Green |
| **EAST** | **RED** | **GPIO 33** | 220Ω – 330Ω | Red |
| **EAST** | **YELLOW** | **GPIO 32** | 220Ω – 330Ω | Yellow |
| **EAST** | **GREEN** | **GPIO 23** | 220Ω – 330Ω | Green |
| **WEST** | **RED** | **GPIO 22** | 220Ω – 330Ω | Red |
| **WEST** | **YELLOW** | **GPIO 21** | 220Ω – 330Ω | Yellow |
| **WEST** | **GREEN** | **GPIO 19** | 220Ω – 330Ω | Green |
| **COMMON** | **GND** | **ESP32 GND Pin** | — | Black / Common Ground Rail |

---

## 🔌 Hardware Circuit Diagram

```
[ ESP32 GPIO Pin ] ───► [ 220Ω / 330Ω Resistor ] ───► [ LED Anode (+) ]
                                                          │
[ ESP32 GND Pin  ] ◄────────────────────────────────── [ LED Cathode (-) ]
```

*All 12 LED cathodes connect to the common Ground (GND) rail on the breadboard, which is connected to any `GND` pin on the ESP32.*

---

## 🛠️ Arduino IDE Setup Guide

1. **Install Arduino IDE** (v2.x recommended from [arduino.cc](https://www.arduino.cc/en/software)).
2. **Add ESP32 Board Package**:
   - Go to **Arduino IDE** → **Settings / Preferences**.
   - In **Additional boards manager URLs**, add:
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to **Tools** → **Board** → **Boards Manager...**
   - Search for `esp32` by **Espressif Systems** and click **Install**.
3. **Select Board**:
   - Go to **Tools** → **Board** → **esp32** → **DOIT ESP32 DEVKIT V1**.
4. **Select Port**:
   - Connect your ESP32 to your computer via USB (Micro-USB or Type-C depending on board revision).
   - Go to **Tools** → **Port** and select the port (e.g. `/dev/cu.usbserial-xxx` on Mac or `COMx` on Windows).
5. **Open Project**:
   - Open `esp32/traffic_signal_controller/traffic_signal_controller.ino`.
6. **Configure Wi-Fi**:
   - Edit lines 28–29:
     ```cpp
     const char* ssid     = "YOUR_WIFI_NAME";     // 2.4 GHz Wi-Fi
     const char* password = "YOUR_WIFI_PASSWORD";
     ```
7. **Upload**:
   - Click the **Upload** button (arrow icon).
   - If the terminal says `Connecting........_____.....`, press and hold the **BOOT** button on the ESP32 until uploading begins.

---

## 🌐 HTTP REST API Endpoints

Once connected, open the Serial Monitor at **115200 baud** to see the assigned IP address (e.g. `192.168.1.105`).

### 1. Root Dashboard
```http
GET http://<ESP32_IP>/
```
*Returns an interactive HTML status page showing the current state of all 4 lane traffic lights.*

### 2. JSON Status
```http
GET http://<ESP32_IP>/status
```
*Response:*
```json
{
  "status": "online",
  "ip": "192.168.1.105",
  "signals": {
    "North": "RED",
    "South": "GREEN",
    "East": "RED",
    "West": "RED"
  },
  "gpio": {
    "North": { "red": 13, "yellow": 12, "green": 14 },
    "South": { "red": 27, "yellow": 26, "green": 25 },
    "East":  { "red": 33, "yellow": 32, "green": 23 },
    "West":  { "red": 22, "yellow": 21, "green": 19 }
  }
}
```

### 3. Update Multi-Lane Signals (Atomic Update)
```http
GET http://<ESP32_IP>/traffic?north=RED&south=GREEN&east=RED&west=RED
```

### 4. Update Single Lane
```http
GET http://<ESP32_IP>/signal?lane=North&signal=GREEN
```

### 5. Safe Reset (All RED)
```http
GET http://<ESP32_IP>/reset
```

### 6. Turn All Off
```http
GET http://<ESP32_IP>/all_off
```
