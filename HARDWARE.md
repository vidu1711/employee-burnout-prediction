# PulseCheck body check-in device: setup guide

**Not a medical device.** Readings are wellbeing hints only.

## 1. Parts
| Part | Notes |
|---|---|
| ESP32 dev board (30 or 38 pin, "ESP32 DevKit V1") | with USB cable (data cable, not charge-only) |
| MAX30102 heart-rate module | the small purple/red breakout board |
| GSR (galvanic skin response) sensor module | two finger pads/electrodes (Grove GSR or similar) |
| Jumper wires, breadboard | |

## 2. Wiring
| From | To ESP32 |
|---|---|
| MAX30102 VIN | 3V3 |
| MAX30102 GND | GND |
| MAX30102 SDA | GPIO 21 |
| MAX30102 SCL | GPIO 22 |
| GSR VCC | 3V3 |
| GSR GND | GND |
| GSR SIG (signal) | GPIO 34 |

- GPIO 34 is on ADC1, which keeps working while Wi-Fi is on. (ADC2 pins do not.)
- Power the GSR module from **3.3 V**. Many GSR modules are 5 V parts; if yours is 5 V, its output can reach 5 V, which can damage the ESP32 input (max 3.3 V). Use 3.3 V power, or put a voltage divider (for example 10 kΩ + 20 kΩ) on SIG.
- The MAX30102 board is also 3.3 V. Do not power it from 5 V unless the board has a regulator (check the seller's page).
- Put one finger on the MAX30102 window (light pressure, not hard) and a different finger (or two fingers) on the GSR pads, same hand or other hand.

## 3. Arduino IDE
1. Install Arduino IDE 2.x.
2. File > Preferences > Additional boards manager URLs: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Tools > Board > Boards Manager > install **esp32 by Espressif Systems**.
4. Tools > Manage Libraries > install **SparkFun MAX3010x Pulse and Proximity Sensor Library** and **ArduinoJson** (version 7).
5. Tools > Board > **ESP32 Dev Module**; pick the right Port.

## 4. Wi-Fi and the server address
1. Close `run.bat` if it is running. Double-click **`run_lan.bat`** instead. Allow it through the Windows firewall (private networks) when asked.
2. It prints a line like `SERVER_URL = "http://192.168.1.50:8000"`. Use that exact address in the firmware.
3. The laptop and the ESP32 must be on the **same Wi-Fi**. Many college networks block devices from talking to each other. If the device cannot connect, switch both to your **phone's hotspot**.
4. The ESP32 only works with **2.4 GHz** Wi-Fi.

## 5. Flash
1. Open `firmware/pulsecheck_esp32/pulsecheck_esp32.ino`.
2. Edit `WIFI_SSID`, `WIFI_PASS`, `SERVER_URL`. Keep `DEVICE_ID = "ESP32-DEMO"` and `DEVICE_KEY = "demo-device-key"` to use the shared demo device, or create your own on the website (Check-in > Add my own device) and paste the ID and key.
3. Upload. Open Serial Monitor at 115200 baud. You should see `Connected. Device IP ...`.
4. If upload hangs on "Connecting...", hold the **BOOT** button on the ESP32 until it starts.

## 6. Test in this order
1. **Network first (no sensors):** run `python tools/fake_device.py`, sign in, Check-in > Start check-in. If a result appears, the website side works.
2. **Real device:** sign in, turn on body check-ins, press *Start check-in*. The LED blinks three times. Place your fingers. After about 30 seconds the result appears on the website.
3. **GSR direction:** measure once with dry fingers, once with slightly damp fingers (Serial Monitor shows the GSR value). Damp skin conducts better, so the number should go **up**. If it goes down, set `GSR_INVERT = true` and re-upload.
4. **Normal range:** do the three daily check-ins for about 3 days. Before that, use *Fill a sample normal range* on the website for the demo.

## 7. Troubleshooting
| Symptom | Fix |
|---|---|
| `MAX30102 not found` | check SDA/SCL (21/22), 3V3, GND; try another jumper wire |
| `Cannot reach the server` | same Wi-Fi? address from `run_lan.bat`? firewall allowed? try a phone hotspot |
| `unknown device or wrong key` | DEVICE_ID / DEVICE_KEY must match exactly |
| "No finger detected" | press slightly harder on the MAX30102; keep the finger still |
| "A clear pulse could not be found" | stay still, warm hands, avoid strong room light on the sensor |
| Heart rate looks wrong | compare with a smartwatch; cold fingers and movement give bad readings |
