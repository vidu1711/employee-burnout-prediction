# Employee Burnout Prediction Using Multi-Signal Fusion

An early-warning system for employee burnout. It combines five signals into one **Low / Medium / High** risk level, with reasons:

| Signal | How it is scored | Weight |
|---|---|---|
| Message tone | VADER sentiment + stress word list + TF-IDF similarity | 30% |
| Schedule load | hours, back-to-back meetings, lunch, late meetings | 25% |
| Body check-in | heart rate (MAX30102) and skin response (GSR) on an ESP32, compared with the person's own normal | 20% |
| Weekly mood | one-tap check-in | 15% |
| Chatbot talk | tone of messages to the assistant | 10% |

A **Random Forest** (scikit-learn, 200 trees, depth 6) takes the signals and gives the final risk level.

> Prototype tested on **synthetic data** (150 employees). It is not a medical device and has not been deployed in a company.

## Project layout
| Folder | What it is |
|---|---|
| `src/` | signal scoring, fusion, dataset generation and model training |
| `models/` | trained Random Forest |
| `webapp/` | FastAPI website (employee, team lead and admin views) |
| `firmware/pulsecheck_esp32/` | ESP32 code for the body check-in device |
| `tools/` | helper scripts (sample data, fake device) |
| `HARDWARE.md`, `WOKWI.md` | device wiring and simulator notes |

## Run the website
```
pip install -r webapp/requirements.txt
python -m webapp.run
```
On Windows you can double-click `run.bat`. Then open http://127.0.0.1:8000.

Demo logins (synthetic data): `admin / admin123`, `lead / lead123`, `emp001 / emp123`.

To let the ESP32 reach the website over Wi-Fi, use `run_lan.bat` and set `SERVER_URL` in the firmware to your computer's address.

## Device (ESP32)
Open `firmware/pulsecheck_esp32/pulsecheck_esp32.ino` in the Arduino IDE, set your Wi-Fi name, password and `SERVER_URL`, and upload. Wiring and parts are in `HARDWARE.md`.

## Privacy
All signals are opt-in. Employees see their own data. Managers see risk levels and reasons only, never message text or raw body readings.

## Author
Vidula Sanjana S (7376231EC317), Bannari Amman Institute of Technology. Guide: Ms. Priyanga M A.
