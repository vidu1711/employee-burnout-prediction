"""
Pretends to be the ESP32, so you can test the website and the network before the hardware arrives.
Needs only Python (no extra packages).

    python tools/fake_device.py                       # talks to http://127.0.0.1:8000
    python tools/fake_device.py http://192.168.1.50:8000
    python tools/fake_device.py http://127.0.0.1:8000 --level elevated

Start a check-in on the website (Check-in page > Start check-in); this script answers it after a few seconds.
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("server", nargs="?", default="http://127.0.0.1:8000")
ap.add_argument("--id", default="ESP32-DEMO")
ap.add_argument("--key", default="demo-device-key")
ap.add_argument("--level", choices=["normal", "elevated"], default="normal")
ap.add_argument("--seconds", type=int, default=6, help="pretend measuring time")
a = ap.parse_args()
H = {"X-Device-Id": a.id, "X-Device-Key": a.key, "Content-Type": "application/json"}


def call(path, data=None):
    req = urllib.request.Request(a.server.rstrip("/") + path, headers=H, data=None if data is None else json.dumps(data).encode(),
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


print(f"Fake device {a.id} polling {a.server} ... (Ctrl+C to stop)")
while True:
    try:
        s = call("/api/device/poll")["session"]
        if s:
            print(f"Check-in requested ({s['slot']}). Measuring {a.seconds}s ...")
            time.sleep(a.seconds)
            hr = random.gauss(92 if a.level == "elevated" else 72, 2)
            gsr = random.gauss(620 if a.level == "elevated" else 420, 20)
            print(call("/api/device/readings", {"session_id": s["id"], "valid": True, "hr": round(hr, 1), "gsr": round(gsr, 1),
                                                "quality": 1.0, "n_samples": 900}))
    except urllib.error.HTTPError as e:
        print("Server said:", e.code, e.read().decode()[:200])
    except Exception as e:
        print("Cannot reach server:", e)
    time.sleep(2)
