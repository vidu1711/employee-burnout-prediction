# PulseCheck (web app)

Role-based burnout early-warning site: messages, schedules, weekly check-ins and a chatbot.

## Run it
Double-click `run.bat` in the project folder. The first start installs packages and builds demo data (about 20 seconds). Your browser opens at http://127.0.0.1:8000.

## Demo logins
| Role | Username | Password |
|---|---|---|
| Employee | emp001 ... emp150 | emp123 |
| Team lead | lead (Platform Engineering), lead2 (Customer Success) | lead123 |
| Admin | admin | admin123 |

You can also create a new employee account on the sign-up tab.

## PulseBot (chatbot)
- Without a key it uses the built-in assistant (calendar, booking, mood, messaging and wellbeing questions, with real actions).
- For free-form AI answers, create `webapp/.env` containing `ANTHROPIC_API_KEY=your-key`, then restart. The badge on the chat page changes from "Built-in" to "Claude AI". Optional: `PULSEBOT_MODEL=claude-haiku-4-5-20251001`.
- In both modes the bot acts only through server-side tools that check your role.

## Privacy rules built in
- Employees never see a risk label. They see only the tone of their own messages and their own meeting load.
- Leads and admins see levels and reasons, never message text. Leads see only their own team.
- Message analysis only runs for people who have it switched on (Settings).

## Notes
- All demo data is synthetic. Reset it by deleting `data/pulsecheck.db`.
- Message tone uses VADER plus a workplace-stress word list and TF-IDF similarity (no model download needed).

## Body check-ins (ESP32 + MAX30102 + GSR)
Three short finger checks a day (morning, afternoon, evening). The device only measures; the website compares the numbers with each person's **own** normal range and shows normal / elevated / high. That level joins message tone, schedule load, weekly mood and PulseBot chats in the risk score.

- **Try it without hardware:** open *Check-in*, turn the switch on, press *Fill a sample normal range*, then *Simulate an elevated reading*. Simulated readings are labelled `simulated`.
- **Test the network without hardware:** `python tools/fake_device.py`, then press *Start check-in* on the website.
- **With the real device:** read `HARDWARE.md` (parts, wiring, Arduino setup, Wi-Fi), start the site with `run_lan.bat`, flash `firmware/pulsecheck_esp32/pulsecheck_esp32.ino`.
- **Privacy:** body check-ins have their own switch (off by default for new accounts). Employees see their numbers; leads and admins see only a level and whether it repeated, never raw numbers. Not a medical device.
- **Normal range:** needs about 6 readings that are more than 3 days old (about 2 to 3 days of use). Readings from the last 3 days are compared with them.
