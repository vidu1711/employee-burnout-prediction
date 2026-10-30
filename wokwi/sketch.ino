/*
  PulseCheck body check-in device: WOKWI SIMULATION VERSION
  Same conversation with the server as the real ESP32 firmware, but:
    - the MAX30102 is replaced by the "Heart rate" knob (35-180 bpm)
    - the GSR sensor is replaced by the "Skin sensor" knob (0-4095)
    - "finger on sensor" is the green button (hold it down while measuring)
  Readings sent from here are real network calls to your website, but the numbers
  come from knobs, so they are SIMULATED. Say so in your demo.

  How to use: paste your website's public address into SERVER_URL, press Play,
  then start a check-in on the website's Check-in page.
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===================== EDIT THIS =====================
const char* SERVER_URL = "https://YOUR-TUNNEL-ADDRESS.trycloudflare.com";   // no slash at the end
const char* DEVICE_ID  = "ESP32-DEMO";
const char* DEVICE_KEY = "demo-device-key";
// =====================================================

const char* WIFI_SSID = "Wokwi-GUEST";   // Wokwi's built-in open Wi-Fi
const int HR_PIN = 35, GSR_PIN = 34, FINGER_PIN = 4, LED_PIN = 2;
const unsigned long WAIT_FINGER_MS = 25000, MEASURE_MS = 8000;   // 8 s here instead of 30 s

int httpCall(const char* method, const String& path, const String& payload, String& body) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  WiFiClientSecure secure; secure.setInsecure();      // demo only: skips certificate checks
  WiFiClient plain;
  HTTPClient http;
  String url = String(SERVER_URL) + path;
  if (url.startsWith("https")) http.begin(secure, url); else http.begin(plain, url);
  http.setTimeout(8000);
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.addHeader("Content-Type", "application/json");
  int code = (String(method) == "POST") ? http.POST(payload) : http.GET();
  if (code > 0) body = http.getString();
  http.end();
  return code;
}

void report(int id, bool valid, const char* reason, float hr, float gsr, int n) {
  JsonDocument doc;
  doc["session_id"] = id; doc["valid"] = valid;
  if (!valid) doc["reason"] = reason; else { doc["hr"] = hr; doc["gsr"] = gsr; doc["n_samples"] = n; doc["quality"] = 1.0; }
  String out, resp; serializeJson(doc, out);
  int code = -1;
  for (int attempt = 1; attempt <= 5 && code != 200 && code != 409; attempt++) {   // retry: the internet link can blip
    code = httpCall("POST", "/api/device/readings", out, resp);
    Serial.printf("Sent result (try %d) -> HTTP %d %s\n", attempt, code, resp.c_str());
    if (code != 200 && code != 409) delay(1500);
  }
}

void measure(int id) {
  Serial.println("Check-in requested. Hold the green button (finger on sensor).");
  digitalWrite(LED_PIN, HIGH);
  unsigned long t0 = millis();
  while (digitalRead(FINGER_PIN) == HIGH) {                 // button pressed = LOW
    if (millis() - t0 > WAIT_FINGER_MS) { digitalWrite(LED_PIN, LOW); report(id, false, "no_finger", 0, 0, 0); return; }
    delay(50);
  }
  Serial.println("Measuring. Set the knobs now, keep holding the button.");
  double hrSum = 0, gsrSum = 0; int n = 0; unsigned long start = millis();
  while (millis() - start < MEASURE_MS) {
    if (digitalRead(FINGER_PIN) == HIGH) { digitalWrite(LED_PIN, LOW); Serial.println("Button released too early. Hold it for the whole measurement."); report(id, false, "no_finger", 0, 0, 0); return; }
    hrSum += 35.0 + analogRead(HR_PIN) * (145.0 / 4095.0);
    gsrSum += analogRead(GSR_PIN);
    n++; delay(20);
  }
  digitalWrite(LED_PIN, LOW);
  float hr = hrSum / n, gsr = gsrSum / n;
  Serial.printf("Result: heart rate %.1f, GSR %.0f\n", hr, gsr);
  report(id, true, "", hr, gsr, n);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT); pinMode(FINGER_PIN, INPUT_PULLUP);
  analogReadResolution(12);
  Serial.print("Connecting to Wi-Fi");
  WiFi.begin(WIFI_SSID, "", 6);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.println(" connected.");
}

void loop() {
  String body;
  int code = httpCall("GET", "/api/device/poll", "", body);
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, body) && !doc["session"].isNull()) { measure((int)doc["session"]["id"]); return; }
  } else if (code == 401) Serial.println("Wrong DEVICE_ID or DEVICE_KEY.");
  else { static int fails = 0; if (++fails % 3 == 1) Serial.printf("Server not reachable right now (code %d). Retrying. If this repeats, check the tunnel and SERVER_URL.\n", code); }
  delay(2000);
}
