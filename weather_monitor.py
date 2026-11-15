import os
import smtplib
from email.message import EmailMessage
import requests
from datetime import datetime, timedelta

# Configuration
LATITUDE = 39.7392
LONGITUDE = -104.9903
TIMEZONE = "America/Denver"

# Credentials loaded securely from environment variables
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECIPIENT_SMS = os.getenv("RECIPIENT_SMS")  # e.g., 1234567890@vtext.com

# Pushover credentials
PUSHOVER_APP_API_TOKEN = os.getenv("PUSHOVER_APP_API_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

# Debug mode setting
DEBUG_MODE = os.getenv("DEBUG_MODE").lower() == "true"

if DEBUG_MODE: #If true, sets "freezing" to 200 degrees to ensure text message sent
    FREEZING_TEMP_F = 200.0
else:
    FREEZING_TEMP_F = 32.0

def fetch_forecast():
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}&"
        f"hourly=temperature_2m&temperature_unit=fahrenheit&"
        f"timezone={TIMEZONE}"
    )
    print(f"📡 Requesting weather data from Open-Meteo...")
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    if DEBUG_MODE: 
        print("\n" + "="*50)
        print("🔍 METEO API DIAGNOSTICS")
        print("="*50)
        print(f"• Request URL: {url}")
        print(f"• Configured Script Timezone: {TIMEZONE}")
        print(f"• API Returned Timezone: {data.get('timezone')} ({data.get('timezone_abbreviation')})")
        print(f"• Elevation: {data.get('elevation')}m")
    
        if "hourly" in data:
            times = data["hourly"].get("time", [])
            temps = data["hourly"].get("temperature_2m", [])
            print(f"• Total hourly data points returned: {len(times)}")
    
            if len(times) > 0:
                print(f"• Data range start: {times[0]} ({temps[0]}°F)")
                print(f"• Data range end  : {times[-1]} ({temps[-1]}°F)")
    
                print("\n• First 5 raw data points returned:")
                for i in range(min(5, len(times))):
                    print(f"  [{i}] {times[i]} -> {temps[i]}°F")
            else:
                print("⚠️ Hourly arrays are empty!")
        else:
            print("⚠️ No 'hourly' block found in API response!")
        print("="*50 + "\n")
    
    return data

def check_freezing_tomorrow(data):
    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 Looking for freezing temperatures on target date: {tomorrow_str}")
    
    freezing_hours = []
    for t_str, temp in zip(times, temps):
        dt = datetime.fromisoformat(t_str)
        if dt.strftime("%Y-%m-%d") == tomorrow_str:
            if temp <= FREEZING_TEMP_F:
                freezing_hours.append((dt.strftime("%H:%M"), temp))
                
    return freezing_hours

def send_pushover_notification(message):
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_APP_API_TOKEN,  # Load from GitHub Secrets
        "user": PUSHOVER_USER_KEY, # Load from GitHub Secrets
        "message": message,
        "title": "Freeze Alert ❄️"
    }
    response = requests.post(url, data=data)
    response.raise_for_status()

def send_sms(message):
    if not RECIPIENT_SMS:
        raise ValueError("RECIPIENT_SMS environment variable is not set.")
        
    msg = EmailMessage()
    msg.set_content(message)
    msg["Subject"] = "Freeze Alert"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_SMS
    
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

def main():
    try:
        data = fetch_forecast()
        freezing_events = check_freezing_tomorrow(data)
        
        if freezing_events:
            min_temp = min(t[1] for t in freezing_events)
            first_time = freezing_events[0][0]
            msg = (
                f"❄️ Freezing Alert: Temps tomorrow drop below freezing! "
                f"Low: {min_temp}°F, starting around {first_time}."
            )
            send_pushover_notification(msg)
        else:
            print("No freezing temperatures forecasted for tomorrow.")
            
    except Exception as e:
        print(f"Error checking weather forecast: {e}")

if __name__ == "__main__":
    main()
