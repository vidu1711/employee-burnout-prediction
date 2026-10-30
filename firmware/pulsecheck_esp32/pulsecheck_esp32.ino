/*
  PulseCheck body check-in device  (ESP32 + MAX30102 + GSR sensor)

  What it does
    1. Every 2 seconds it asks the PulseCheck server: "does anyone want a check-in on me?"
    2. If yes, it blinks the LED, waits for a finger on the heart-rate sensor,
       then measures for 30 seconds (heart rate from the MAX30102, skin conductance from the GSR sensor).
    3. It sends ONE result (average heart rate + average GSR) to the server.
  The device never decides if someone is stressed and never knows who is measuring.
  The website compares the numbers with each person's own normal range.

  Wiring (see WIRING.md)
    MAX30102  VIN->3V3  GND->GND  SDA->GPIO21  SCL->GPIO22
    GSR       VCC->3V3  GND->GND  SIG->GPIO34   (GPIO34 is an ADC1 pin, safe to use with Wi-Fi)

  Libraries (Arduino IDE > Library Manager)
    "SparkFun MAX3010x Pulse and Proximity Sensor Library"
    "ArduinoJson" (version 7)
  Board: "ESP32 Dev Module"  (install "esp32 by Espressif Systems" in Boards Manager)

  NOT a medical device. Readings are only wellbeing hints.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include "MAX30105.h"
#include "heartRate.h"

// ===================== EDIT THESE =====================
const char* WIFI_SSID   = "YOUR_WIFI_NAME";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";
// The laptop running PulseCheck. Use run_lan.bat, then type the address it prints (keep the :8000).
const char* SERVER_URL  = "http://192.168.1.50:8000";
// Shared demo device that comes with the website. For your own device, make one on the Check-in page.
const char* DEVICE_ID   = "ESP32-DEMO";
const char* DEVICE_KEY  = "demo-device-key";
// If the GSR number goes DOWN when you wet your fingers, set this to true.
const bool  GSR_INVERT  = false;
// ======================================================

const int   GSR_PIN          = 34;
const int   LED_PIN          = 2;        // built-in LED on most ESP32 boards
const long  FINGER_IR_MIN    = 50000;    // IR level that means "a finger is on the sensor"
const unsigned long WAIT_FINGER_MS = 25000;
const unsigned long MEASURE_MS     = 30000;
const unsigned long GSR_SETTLE_MS  = 5000;   // ignore the first seconds, skin contact is still settling
const unsigned long LOST_FINGER_MS = 4000;

MAX30105 sensor;
bool sensorOk = false;

// ---------- small helpers ----------
void blink(int times, int ms = 120) {
  for (int i = 0; i < times; i++) { digitalWrite(LED_PIN, HIGH); delay(ms); digitalWrite(LED_PIN, LOW); delay(ms); }
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Connecting to Wi-Fi \"%s\" ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) { delay(400); Serial.print("."); }
  if (WiFi.status() == WL_CONNECTED) Serial.printf("\nConnected. Device IP %s\n", WiFi.localIP().toString().c_str());
  else Serial.println("\nCould not connect. Check the name and password. Will retry.");
}

// returns HTTP status (or -1). body gets the response text.
int httpCall(const char* method, const String& path, const String& payload, String& body) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  HTTPClient http;
  http.setTimeout(6000);
  http.begin(String(SERVER_URL) + path);
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.addHeader("Content-Type", "application/json");
  int code = (String(method) == "POST") ? http.POST(payload) : http.GET();
  if (code > 0) body = http.getString();
  http.end();
  return code;
}

void report(int sessionId, bool valid, const char* reason, float hr, float gsr, int nSamples) {
  JsonDocument doc;
  doc["session_id"] = sessionId;
  doc["valid"] = valid;
  if (!valid) doc["reason"] = reason;
  else { doc["hr"] = hr; doc["gsr"] = gsr; doc["n_samples"] = nSamples; doc["quality"] = 1.0; }
  String out, resp;
  serializeJson(doc, out);
  int code = httpCall("POST", "/api/device/readings", out, resp);
  Serial.printf("Sent result -> HTTP %d %s\n", code, resp.c_str());
}

// tells the website the 30 second countdown has started (best effort; the check-in still works if it fails)
void sendProgress(int sessionId, const char* phase) {
  String out, resp;
  out = String("{\"session_id\":") + sessionId + ",\"phase\":\"" + phase + "\"}";
  int code = httpCall("POST", "/api/device/progress", out, resp);
  Serial.printf("Progress -> HTTP %d\n", code);
}

// ---------- the measurement ----------
void measure(int sessionId) {
  Serial.println("Check-in requested. Place a finger on the heart-rate sensor and another on the GSR pads.");
  blink(3);
  digitalWrite(LED_PIN, HIGH);

  // 1) wait for a finger
  unsigned long t0 = millis();
  while (sensor.getIR() < FINGER_IR_MIN) {
    if (millis() - t0 > WAIT_FINGER_MS) {
      digitalWrite(LED_PIN, LOW);
      Serial.println("No finger detected.");
      report(sessionId, false, "no_finger", 0, 0, 0);
      return;
    }
    delay(50);
  }
  Serial.println("Finger found. Measuring for 30 seconds. Keep still.");
  sendProgress(sessionId, "measuring");

  // 2) measure
  const int MAXB = 80;
  float beats[MAXB]; int nb = 0;
  long lastBeat = 0;
  double gsrSum = 0; int gsrN = 0;
  unsigned long start = millis(), lastGsr = 0, lastSeen = millis();

  while (millis() - start < MEASURE_MS) {
    long ir = sensor.getIR();
    if (ir >= FINGER_IR_MIN) lastSeen = millis();
    else if (millis() - lastSeen > LOST_FINGER_MS) {
      digitalWrite(LED_PIN, LOW);
      Serial.println("Finger lifted.");
      report(sessionId, false, "no_finger", 0, 0, 0);
      return;
    }
    if (checkForBeat(ir)) {
      long now = millis(), delta = now - lastBeat;
      lastBeat = now;
      float bpm = 60000.0f / delta;
      if (delta > 0 && bpm > 40 && bpm < 180 && nb < MAXB && millis() - start > 3000) beats[nb++] = bpm;
    }
    if (millis() - lastGsr >= 20) {                       // GSR at 50 Hz
      lastGsr = millis();
      if (millis() - start > GSR_SETTLE_MS) {
        int raw = analogRead(GSR_PIN);
        gsrSum += GSR_INVERT ? (4095 - raw) : raw;
        gsrN++;
      }
    }
  }
  digitalWrite(LED_PIN, LOW);

  // 3) summarise: median of beat rates is robust against a missed or double-counted beat
  if (nb < 5 || gsrN < 100) {
    Serial.printf("Not enough clean data (beats=%d, gsr samples=%d)\n", nb, gsrN);
    report(sessionId, false, "no_pulse", 0, 0, 0);
    return;
  }
  for (int i = 1; i < nb; i++) { float v = beats[i]; int j = i - 1; while (j >= 0 && beats[j] > v) { beats[j + 1] = beats[j]; j--; } beats[j + 1] = v; }
  float hr = beats[nb / 2];
  float gsr = (float)(gsrSum / gsrN);
  Serial.printf("Result: heart rate %.1f bpm (%d beats), GSR %.0f (%d samples)\n", hr, nb, gsr, gsrN);
  report(sessionId, true, "", hr, gsr, gsrN);
  blink(2, 300);
}

// ---------- Arduino ----------
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(GSR_PIN, ADC_11db);
  Wire.begin(21, 22);
  sensorOk = sensor.begin(Wire, I2C_SPEED_FAST);
  if (sensorOk) {
    sensor.setup();                         // default: LED 0x1F, avg 4, red+IR, 400 sps
    sensor.setPulseAmplitudeRed(0x1F);
    sensor.setPulseAmplitudeGreen(0);
  } else {
    Serial.println("MAX30102 not found. Check SDA->GPIO21, SCL->GPIO22, VIN->3V3, GND.");
  }
  connectWifi();
}

void loop() {
  connectWifi();
  if (!sensorOk) { blink(5, 80); delay(2000); return; }

  String body;
  int code = httpCall("GET", "/api/device/poll", "", body);
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, body) && !doc["session"].isNull()) {
      measure((int)doc["session"]["id"]);
      return;
    }
  } else if (code == 401) {
    Serial.println("Server says: unknown device or wrong key. Check DEVICE_ID and DEVICE_KEY.");
  } else if (code < 0) {
    Serial.println("Cannot reach the server. Check SERVER_URL, same Wi-Fi, and the Windows firewall.");
  }
  delay(2000);
}
