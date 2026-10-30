"""Start PulseCheck:  python -m webapp.run"""

import os
import socket
import threading
import webbrowser

import uvicorn


def free_port(start=8000, tries=20):
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def lan_ip():
    """This computer's address on the Wi-Fi/LAN (what the ESP32 should call)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main():
    host = os.environ.get("PULSECHECK_HOST", "127.0.0.1")        # 0.0.0.0 lets the ESP32 reach this computer
    port = int(os.environ.get("PULSECHECK_PORT", 0)) or free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"\n  PulseCheck is starting at {url}\n  (first start builds the demo data, give it a few seconds)")
    if host != "127.0.0.1":
        print(f"\n  For the ESP32 device use:  SERVER_URL = \"http://{lan_ip()}:{port}\"\n  (the device and this computer must be on the same Wi-Fi)")
    print()
    threading.Timer(3.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("webapp.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
