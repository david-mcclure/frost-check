import os
import requests
from datetime import datetime, timedelta
import time
import zoneinfo
import socket
import urllib3.util.connection as urllib_conn

def allowed_gai_family():
    """Forces all outbound requests to bypass IPv6 and use IPv4 only."""
    return socket.AF_INET

urllib_conn.allowed_gai_family = allowed_gai_family

# Configuration
LATITUDE = 39.7894
LONGITUDE = -104.8842
TIMEZONE = "America/Denver"

# Pushover credentials
PUSHOVER_APP_API_TOKEN = os.getenv("PUSHOVER_APP_API_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

# Debug mode setting
FORCE_TEXT = os.getenv("FORCE_TEXT").lower() == "true"

# --- DETERMINE FREEZING TEMPERATURE ---
# Check if a custom override temperature is passed from the YAML environment
OVERRIDE_FREEZING_TEMP = os.getenv("OVERRIDE_FREEZING_TEMP")

if OVERRIDE_FREEZING_TEMP is not None and OVERRIDE_FREEZING_TEMP.strip() != "":
    FREEZING_TEMP_F = float(OVERRIDE_FREEZING_TEMP)
    print(f"🔧 Using custom freezing temperature override from YAML: {FREEZING_TEMP_F}°F")
else:
    # Fallback to standard default/debug logic if no custom override exists
    FREEZING_TEMP_F = 32.0
    

def get_query_window():
    """Returns (start_hour, end_hour) strings formatted for Open-Meteo."""
    denver_tz = zoneinfo.ZoneInfo(TIMEZONE)
    now_denver = datetime.now(denver_tz)

    # Current hour today
    start_hour = now_denver.strftime("%Y-%m-%dT%H:00")

    # End: Exactly 12 hours into the future
    future_time = now_denver + timedelta(hours=12)
    end_hour = future_time.strftime("%Y-%m-%dT%H:00")

    return start_hour, end_hour

def fetch_forecast(max_retries=4, base_timeout=15):
    start_hour, end_hour = get_query_window()
    print(f"🕒 Requesting forecast window: {start_hour} to {end_hour}")

    # Query ONLY from current hour to tomorrow at noon
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={LATITUDE}&longitude={LONGITUDE}&"
        f"hourly=temperature_2m&temperature_unit=fahrenheit&"
        f"timezone={TIMEZONE}&"
        f"start_hour={start_hour}&end_hour={end_hour}"
    )
    
    print(f"📡 Requesting weather data from Open-Meteo...")
    for attempt in range(1, max_retries + 1):
        # Slightly scale timeout with each attempt
        current_timeout = base_timeout + (attempt - 1) * 5
        print(f"📡 Requesting weather data from Open-Meteo (Attempt {attempt}/{max_retries}, timeout={current_timeout}s)...")

        try:
            response = requests.get(url, timeout=current_timeout)
            response.raise_for_status()
            data = response.json()
            print("✅ Successfully retrieved forecast data.")
            break
    

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            print(f"⚠️ Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                sleep_seconds = 2 ** attempt  # 2s, 4s, 8s backoff
                print(f"⏳ Waiting {sleep_seconds} seconds before retrying...")
                time.sleep(sleep_seconds)
            else:
                print("❌ All retry attempts exhausted.")
                raise e

    
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

            print("\n• Print all raw data points:")
            for i in range(len(times)):
                print(f"  [{i}] {times[i]} -> {temps[i]}°F")
        else:
            print("⚠️ Hourly arrays are empty!")
    else:
        print("⚠️ No 'hourly' block found in API response!")
    print("="*50 + "\n")
    
    return data

def check_freezing_temperatures(data):
    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    
    freezing_hours = []
    for t_str, temp in zip(times, temps):
        dt = datetime.fromisoformat(t_str)
        if temp <= FREEZING_TEMP_F:
            freezing_hours.append((dt.strftime("%H:%M"), temp))
                
    return freezing_hours

def send_notification(message):
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_APP_API_TOKEN,  # Load from GitHub Secrets
        "user": PUSHOVER_USER_KEY, # Load from GitHub Secrets
        "message": message,
        "title": "Freeze Alert ❄️"
    }
    response = requests.post(url, data=data)
    response.raise_for_status()

def main():
    data = fetch_forecast()
    freezing_events = check_freezing_temperatures(data)
    
    if freezing_events:
        min_temp = min(t[1] for t in freezing_events)
        first_time = freezing_events[0][0]
        n_hours = len(freezing_events)
        msg = (
            f"❄️ Freezing Alert: Temps tomorrow drop below freezing! "
            f"Low: {min_temp}°F, starting around {first_time} and lasting {n_hours} hour(s)."
        )
        send_notification(msg)
    elif FORCE_TEXT:
        send_notification('No freezing temperature found, but still sending notification because FORCE_TEXT = true')
    else:
        print("No freezing temperatures forecasted for tomorrow.")

if __name__ == "__main__":
    main()
