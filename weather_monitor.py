import os
import time
import requests
import socket
from datetime import datetime, timedelta
import zoneinfo
import urllib3.util.connection as urllib_conn

def allowed_gai_family():
    """Forces all outbound requests to bypass IPv6 and use IPv4 only. Necessary since gemini thinks IPv6 causes timeout issues"""
    return socket.AF_INET

urllib_conn.allowed_gai_family = allowed_gai_family

# Configuration
LATITUDE = 39.7895
LONGITUDE = -104.8842
TIMEZONE = "America/Denver"

# Pushover credentials
PUSHOVER_APP_API_TOKEN = os.getenv("PUSHOVER_APP_API_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

# Debug mode setting (Single source of truth default: False)
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Determine freezing temperature threshold with manual YAML overrides
CUSTOM_TEMP_ENV = os.getenv("FREEZING_TEMP_F")
if CUSTOM_TEMP_ENV is not None and CUSTOM_TEMP_ENV.strip() != "":
    try:
        FREEZING_TEMP_F = float(CUSTOM_TEMP_ENV)
        print(f"🔧 Using custom freezing temperature override from YAML: {FREEZING_TEMP_F}°F")
    except ValueError:
        print(f"⚠️ Warning: Invalid FREEZING_TEMP_F value received ('{CUSTOM_TEMP_ENV}'). Falling back to defaults.")
        FREEZING_TEMP_F = 200.0 if DEBUG_MODE else 32.0
else:
    FREEZING_TEMP_F = 200.0 if DEBUG_MODE else 32.0
    print(f"ℹ️ Freezing threshold set to: {FREEZING_TEMP_F}°F")

def get_query_window():
    """Returns (start_hour, end_hour) strings for the next 12 hours."""
    denver_tz = zoneinfo.ZoneInfo(TIMEZONE)
    now_denver = datetime.now(denver_tz)
    
    # Start: Current hour today
    start_hour = now_denver.strftime("%Y-%m-%dT%H:00")
    
    # End: 12 hours from now
    future_time = now_denver + timedelta(hours=12)
    end_hour = future_time.strftime("%Y-%m-%dT%H:00")
    
    return start_hour, end_hour

def fetch_forecast(max_retries=4, base_timeout=15):
    # Retrieve only the next 12 hours to speed up requests
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}&"
        f"hourly=temperature_2m&temperature_unit=fahrenheit&"
        f"timezone={TIMEZONE}&"
        f"forecast_hours=12"
    )
    
    headers = {
        "User-Agent": "WeatherFreezeAlertWorkflow/1.0 (Personal Automation)"
    }
    
    for attempt in range(1, max_retries + 1):
        current_timeout = base_timeout + (attempt - 1) * 5
        print(f"📡 Requesting weather data (Attempt {attempt}/{max_retries}, timeout={current_timeout}s)...")
        
        try:
            response = requests.get(url, headers=headers, timeout=current_timeout)
            response.raise_for_status()
            data = response.json()
            print("✅ Successfully retrieved forecast data.")
            return data
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                sleep_seconds = 2 ** attempt
                print(f"⏳ Waiting {sleep_seconds}s before retrying...")
                time.sleep(sleep_seconds)
            else:
                print("❌ All retry attempts to Open-Meteo failed.")
                raise e

def check_freezing_window(data):
    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    
    freezing_hours = []
    for t_str, temp in zip(times, temps):
        dt = datetime.fromisoformat(t_str)
        if temp <= FREEZING_TEMP_F:
            freezing_hours.append((dt, temp))
                
    return freezing_hours

def send_pushover_notification(message):
    if not PUSHOVER_APP_API_TOKEN or not PUSHOVER_USER_KEY:
        raise ValueError("Pushover credentials are missing from environment variables.")

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_APP_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": "Freeze Alert ❄️"
    }
    response = requests.post(url, data=data, timeout=15)
    response.raise_for_status()

def main():
    try:
        data = fetch_forecast()
        freezing_events = check_freezing_window(data)
        
        if freezing_events:
            min_temp = min(t[1] for t in freezing_events)
            
            # Start time = first hour freezing occurs
            start_dt = freezing_events[0][0]
            start_time_str = start_dt.strftime("%I:%M %p")
            
            # End time = last hour freezing occurs
            end_dt = freezing_events[-1][0]
            end_time_str = end_dt.strftime("%I:%M %p")
            
            if start_time_str == end_time_str:
                msg = (
                    f"❄️ Freeze Alert: Dips below freezing at {start_time_str}! "
                    f"Expected low: {min_temp}°F."
                )
            else:
                msg = (
                    f"❄️ Freeze Alert: Freeze expected between {start_time_str} and {end_time_str}! "
                    f"Expected low: {min_temp}°F."
                )
                
            print(f"Sending notification: {msg}")
            send_pushover_notification(msg)
            print("Notification sent successfully!")
        else:
            print(f"No freezing temperatures (<= {FREEZING_TEMP_F}°F) forecasted for the next 12 hours.")
            
    except Exception as e:
        print(f"Error checking weather forecast: {e}")
        raise e

if __name__ == "__main__":
    main()
