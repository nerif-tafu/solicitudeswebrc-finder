# Appointment finder for SRCEI

This script checks for available appointments at the SRCEI (Servicio de Registro Civil de Chile) and will notify you on telegram if an earlier appointment is found.

## Setup and run

1. Download chromium snap with 
```
sudo snap install chromium
```

2. Download chromedriver from https://googlechromelabs.github.io/chrome-for-testing/#stable and put it in the root of the project

3. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create a telegram bot for notifications:
- Go to https://t.me/BotFather and create a new bot
- Get the token and chat id

6. Create a .env file in the root of the project with your credentials:
```
RUN=your_run
PASSWORD=your_password
REGION=13
OFFICES=PROVIDENCIA,ÑUÑOA,LAS CONDES
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DAYS_TO_SEARCH=30
WAIT_TIME=60
```

Note: 
- REGION should be the region ID (e.g., 13 for Región Metropolitana)
- OFFICES should be a comma-separated list of office names exactly as they appear on the website
- DAYS_TO_SEARCH is the number of days to look ahead for appointments (default: 30)
- WAIT_TIME is the number of seconds to wait between runs (default: 60)

7. Make chromedriver executable:
```bash
chmod +x chromedriver
```

8. Run the script:
```bash
python3 appointment_checker.py
```

## Running as a systemd service

To run the script as a background service that starts automatically on boot:

1. Create a systemd service file named `appointment-checker.service`:
```ini
[Unit]
Description=SRCEI Appointment Checker Service
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/your/project
Environment="PATH=/path/to/your/project/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/path/to/your/project/venv/bin/python3 appointment_checker.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

2. Replace in the service file:
   - `YOUR_USERNAME` with your Linux username
   - `/path/to/your/project` with the absolute path to your project directory

3. Install and start the service:
```bash
# Copy service file to systemd
sudo cp appointment-checker.service /etc/systemd/system/

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable appointment-checker --now

# Check service status
sudo systemctl status appointment-checker
```

4. View the logs:
```bash
# View last 100 lines
sudo journalctl -u appointment-checker -n 100
```
