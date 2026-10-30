# Simulate the ESP32 online (no hardware needed)

Wokwi (wokwi.com) is a free online ESP32 simulator. Here it stands in for the ESP32; knobs stand in for the MAX30102 and GSR sensors. Readings are **simulated**; the network connection to your website is real.

Wokwi runs on the internet, so it cannot see `127.0.0.1` on your laptop. Give your website a temporary public address first.

## A. Give the website a public address (temporary)
1. Start the site normally with `run.bat` (it opens at http://127.0.0.1:8000).
2. Install Cloudflare's free tunnel once: in Command Prompt run `winget install --id Cloudflare.cloudflared`
   (or download cloudflared from developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
3. In a second window run: `cloudflared tunnel --url http://127.0.0.1:8000`
4. It prints an address like `https://something-random.trycloudflare.com`. Copy it.
5. **Close that window when you finish.** While it runs, anyone with the address can open your site (demo passwords like admin123!). Do not share the address.

## B. Build the simulated device
1. Go to wokwi.com > New Project > **ESP32**. Choose Arduino.
2. Replace `sketch.ino` with the file in the `wokwi/` folder. Click the `diagram.json` tab and replace it with `wokwi/diagram.json`. Add `ArduinoJson` in `libraries.txt` (file in `wokwi/`).
3. In `sketch.ino` set `SERVER_URL` to your tunnel address (no slash at the end).
4. Press the green Play button. The Serial Monitor should say "connected."

## C. Run a check-in
1. On the website, sign in, open **Check-in**, turn the switch on, press **Fill a sample normal range** (builds a baseline).
2. Press **Start check-in** on a slot.
3. In Wokwi: **hold the green button** and set the knobs. For a normal reading, heart rate knob near the middle-low (about 70 bpm), skin knob about 10% (value around 420). For "elevated", turn heart rate to about 92 and the skin knob up.
4. After about 8 seconds the website shows the result.
