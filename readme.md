# Appointment finder for SRCEI

This script checks for available appointments at the SRCEI (Servicio de Registro Civil de Chile) and will notify you on telegram if an earlier appointment is found.

## Setup and run

1. Download chromedriver from https://googlechromelabs.github.io/chrome-for-testing/#stable and put it in the root of the project

2. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a telegram bot for notifications:
- Go to https://t.me/BotFather and create a new bot
- Get the token and chat id

5. Create a .env file in the root of the project with your credentials:
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

6. Make chromedriver executable:
```bash
chmod +x chromedriver
```

7. Run the script:
```bash
python3 appointment_checker.py
```