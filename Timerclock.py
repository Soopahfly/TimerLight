"""
Timer Clock with NeoPixel Ring - USB Network + RTC + Timezone/DST
With LED Enable/Disable and Configurable Count

Features:
- LEDs OFF by default until configured
- Configurable LED count (no code changes needed!)
- Enable/Disable switch in web interface
- USB networking (no WiFi needed)
- DS3231 RTC support
- Timezone and DST support

Hardware:
- Raspberry Pi Pico W (or regular Pico)
- NeoPixel Ring (any size: 8, 12, 16, 24, 60, etc.)
- DS3231 RTC Module (optional)
"""

import network
import socket
import time
import machine
from neopixel import NeoPixel
import json

# Configuration
NEOPIXEL_PIN = 0
USB_IP = "10.55.0.1"
HOST_IP = "10.55.0.2"

# I2C pins for DS3231
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5

# Initialize RTC
rtc = machine.RTC()

# Initialize NeoPixel (will be reinitialized when LED count is set)
np = None
np_pin = machine.Pin(NEOPIXEL_PIN)

# External RTC (will be initialized based on settings)
external_rtc = None
i2c = None

# Flash tracking
flash_start_time = None
last_flash_toggle = 0

# Default settings
settings = {
    'wake_time': '07:00',
    'bedtime': '21:00',       # Time to switch back to stay color (night mode)
    'bedtime_enabled': True,  # Enable automatic bedtime transition
    'stay_color': [255, 0, 0],
    'wake_color': [0, 255, 0],
    'transition_minutes': 30,
    'timezone': 'UTC',
    'utc_offset_minutes': 0,
    'dst_enabled': True,
    'dst_region': None,
    'num_leds': 12,           # Number of LEDs in ring
    'leds_enabled': False,    # LEDs OFF by default!
    'brightness': 100,        # Brightness percentage (0-100)
    'led_color_order': 'RGB', # Color order: RGB, GRB, RGBW, GRBW
    'use_external_rtc': True, # Use DS3231 external RTC if available
    'brightness_ramp_enabled': False,  # Gradually increase brightness after wake color
    'brightness_ramp_minutes': 15,     # Duration to ramp brightness (minutes)
    'brightness_ramp_start': 10,       # Starting brightness percentage
    'flash_enabled': False,   # Flash LEDs at wake time
    'flash_duration': 10,     # How long to flash (seconds)
    'flash_interval': 500,    # Flash on/off interval (milliseconds)
    'network_mode': 'auto',   # 'auto', 'usb', or 'wifi'
    'wifi_ssid': '',          # WiFi network name
    'wifi_password': '',      # WiFi password
    'wifi_ip': '192.168.1.100',  # Static IP for WiFi mode (optional)
}

SETTINGS_FILE = 'settings.json'

# Timezone definitions (UTC offset in minutes)
TIMEZONES = {
    'UTC': 0,
    'GMT': 0,
    'EST': -300, 'EDT': -240,
    'CST': -360, 'CDT': -300,
    'MST': -420, 'MDT': -360,
    'PST': -480, 'PDT': -420,
    'BST': 60,
    'CET': 60, 'CEST': 120,
    'EET': 120, 'EEST': 180,
    'AEST': 600, 'AEDT': 660,
}

# DST Rules
DST_RULES = {
    'US': {
        'start_month': 3, 'start_week': 2, 'start_hour': 2,
        'end_month': 11, 'end_week': 1, 'end_hour': 2,
        'offset_minutes': 60
    },
    'EU': {
        'start_month': 3, 'start_week': -1, 'start_hour': 1,
        'end_month': 10, 'end_week': -1, 'end_hour': 1,
        'offset_minutes': 60
    },
    'UK': {
        'start_month': 3, 'start_week': -1, 'start_hour': 1,
        'end_month': 10, 'end_week': -1, 'end_hour': 1,
        'offset_minutes': 60
    },
    'AU': {
        'start_month': 10, 'start_week': 1, 'start_hour': 2,
        'end_month': 4, 'end_week': 1, 'end_hour': 3,
        'offset_minutes': 60
    }
}

# DS3231 functions
DS3231_ADDR = 0x68  # I2C address for DS3231 RTC chip

def bcd_to_dec(bcd):
    """Convert BCD (Binary Coded Decimal) to normal decimal"""
    return (bcd >> 4) * 10 + (bcd & 0x0F)

def dec_to_bcd(dec):
    """Convert normal decimal to BCD (Binary Coded Decimal)"""
    return ((dec // 10) << 4) | (dec % 10)

def read_ds3231_time():
    """Read time from DS3231 RTC chip"""
    if not external_rtc:
        return None
    try:
        # Read 7 bytes starting from register 0x00 (seconds register)
        data = external_rtc.readfrom_mem(DS3231_ADDR, 0x00, 7)
        # Extract time components with bit masks to clear flag bits
        seconds = bcd_to_dec(data[0] & 0x7F)      # Mask bit 7 (oscillator stop flag)
        minutes = bcd_to_dec(data[1] & 0x7F)      # Mask bit 7 (unused)
        hours = bcd_to_dec(data[2] & 0x3F)        # Mask bits 6-7 (12/24 hour mode)
        day_of_week = bcd_to_dec(data[3] & 0x07)  # Mask bits 3-7 (unused)
        day = bcd_to_dec(data[4] & 0x3F)          # Mask bits 6-7 (unused)
        month = bcd_to_dec(data[5] & 0x1F)        # Mask bits 5-7 (century bit)
        year = bcd_to_dec(data[6]) + 2000         # Year is stored as 00-99
        return (year, month, day, day_of_week, hours, minutes, seconds, 0)
    except Exception as e:
        print(f"Error reading DS3231: {e}")
        return None

def write_ds3231_time(year, month, day, hours, minutes, seconds):
    if not external_rtc:
        return False
    try:
        data = bytearray([
            dec_to_bcd(seconds), dec_to_bcd(minutes), dec_to_bcd(hours),
            1, dec_to_bcd(day), dec_to_bcd(month), dec_to_bcd(year - 2000)
        ])
        external_rtc.writeto_mem(DS3231_ADDR, 0x00, data)
        return True
    except Exception as e:
        print(f"Error writing to DS3231: {e}")
        return False

def sync_time_from_ds3231():
    if not external_rtc:
        return False
    ds_time = read_ds3231_time()
    if ds_time:
        rtc.datetime(ds_time)
        print(f"Synced from DS3231: {ds_time[4]:02d}:{ds_time[5]:02d}")
        return True
    return False

def initialize_external_rtc():
    """Initialize external RTC based on settings"""
    global external_rtc, i2c

    if not settings.get('use_external_rtc', True):
        print("External RTC disabled in settings")
        external_rtc = None
        return False

    try:
        if i2c is None:
            i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA_PIN), scl=machine.Pin(I2C_SCL_PIN), freq=400000)

        devices = i2c.scan()
        if 0x68 in devices:
            print("DS3231 RTC found!")
            external_rtc = i2c
            return True
        else:
            print("DS3231 not found at address 0x68")
            external_rtc = None
            return False
    except Exception as e:
        print(f"Could not initialize external RTC: {e}")
        external_rtc = None
        return False

# Timezone and DST functions
def get_nth_weekday_of_month(year, month, weekday, n):
    """Find nth occurrence of weekday in month"""
    if n > 0:
        day = 1
        count = 0
        while day <= 31:
            try:
                t = time.mktime((year, month, day, 0, 0, 0, 0, 0))
                current_weekday = (time.localtime(t)[6] + 1) % 7
                if current_weekday == weekday:
                    count += 1
                    if count == n:
                        return day
                day += 1
            except:
                break
    else:  # Last occurrence
        if month == 12:
            next_month, next_year = 1, year + 1
        else:
            next_month, next_year = month + 1, year
        last_day = time.mktime((next_year, next_month, 1, 0, 0, 0, 0, 0)) - 86400
        last_day_tuple = time.localtime(last_day)
        day = last_day_tuple[2]
        while day >= 1:
            t = time.mktime((year, month, day, 0, 0, 0, 0, 0))
            current_weekday = (time.localtime(t)[6] + 1) % 7
            if current_weekday == weekday:
                return day
            day -= 1
    return None

def calculate_dst_transitions(year, dst_region):
    if dst_region not in DST_RULES:
        return None, None
    rules = DST_RULES[dst_region]
    start_day = get_nth_weekday_of_month(year, rules['start_month'], 6, rules['start_week'])
    end_day = get_nth_weekday_of_month(year, rules['end_month'], 6, rules['end_week'])
    if start_day and end_day:
        start_timestamp = time.mktime((year, rules['start_month'], start_day, 
                                       rules['start_hour'], 0, 0, 0, 0))
        end_timestamp = time.mktime((year, rules['end_month'], end_day,
                                     rules['end_hour'], 0, 0, 0, 0))
        return start_timestamp, end_timestamp
    return None, None

def is_dst_active(current_time, dst_region):
    if not settings['dst_enabled'] or dst_region not in DST_RULES:
        return False
    year = time.localtime(current_time)[0]
    dst_start, dst_end = calculate_dst_transitions(year, dst_region)
    if dst_start is None or dst_end is None:
        return False
    if DST_RULES[dst_region]['start_month'] < DST_RULES[dst_region]['end_month']:
        return dst_start <= current_time < dst_end
    else:
        return current_time >= dst_start or current_time < dst_end

def get_local_time():
    utc_time = rtc.datetime()
    utc_timestamp = time.mktime((utc_time[0], utc_time[1], utc_time[2],
                                 utc_time[4], utc_time[5], utc_time[6], 0, 0))
    offset_seconds = settings['utc_offset_minutes'] * 60
    dst_region = settings.get('dst_region', None)
    if dst_region and is_dst_active(utc_timestamp, dst_region):
        dst_offset = DST_RULES[dst_region]['offset_minutes'] * 60
        offset_seconds += dst_offset
    local_timestamp = utc_timestamp + offset_seconds
    return time.localtime(local_timestamp)

def get_current_minutes():
    local_time = get_local_time()
    return local_time[3] * 60 + local_time[4]

def get_current_time_str():
    local_time = get_local_time()
    return f"{local_time[3]:02d}:{local_time[4]:02d}"

def get_current_date_str():
    local_time = get_local_time()
    return f"{local_time[0]}-{local_time[1]:02d}-{local_time[2]:02d}"

# Settings functions
def load_settings():
    global settings, np
    try:
        with open(SETTINGS_FILE, 'r') as f:
            loaded = json.load(f)
            settings.update(loaded)
        print("Settings loaded from file")

        # Reinitialize NeoPixel with loaded LED count
        initialize_neopixel()

        # Initialize external RTC based on settings
        initialize_external_rtc()
    except (OSError, ValueError, KeyError) as e:
        print(f"No saved settings found or error loading: {e}, using defaults")
        # Initialize with default LED count
        initialize_neopixel()

        # Initialize external RTC based on defaults
        initialize_external_rtc()

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
        print("Settings saved")
    except Exception as e:
        print("Error saving settings:", e)

def initialize_neopixel():
    """Initialize or reinitialize NeoPixel with current settings"""
    global np
    try:
        num_leds = settings.get('num_leds', 12)
        color_order = settings.get('led_color_order', 'RGB')

        # Map color order string to NeoPixel bpp (bytes per pixel)
        # RGB/GRB = 3 bytes, RGBW/GRBW = 4 bytes
        bpp = 4 if 'W' in color_order else 3

        np = NeoPixel(np_pin, num_leds, bpp=bpp)
        print(f"NeoPixel initialized: {num_leds} LEDs, {color_order} order")
        # Turn off all LEDs initially
        set_all_leds(0, 0, 0)
    except Exception as e:
        print(f"Error initializing NeoPixel: {e}")

def detect_network_capability():
    """Detect if the board supports USB LAN or WiFi"""
    has_usb_lan = False
    has_wifi = False

    try:
        # Try to detect USB LAN (Pico W with recent firmware)
        lan = network.LAN()
        has_usb_lan = True
        print("✓ USB LAN capability detected")
    except:
        print("✗ USB LAN not available")

    try:
        # Try to detect WiFi (Pico W or WiFi-capable boards)
        wlan = network.WLAN(network.STA_IF)
        has_wifi = True
        print("✓ WiFi capability detected")
    except:
        print("✗ WiFi not available")

    return has_usb_lan, has_wifi

def setup_usb_network():
    """Setup USB network interface (Pico W only)"""
    print("Setting up USB network interface...")
    try:
        lan = network.LAN()
        lan.active(True)
        lan.ifconfig((USB_IP, '255.255.255.0', HOST_IP, HOST_IP))
        print(f"✓ USB Network ready at: http://{USB_IP}")
        return USB_IP
    except Exception as e:
        print(f"✗ USB network setup failed: {e}")
        return None

def setup_wifi_network():
    """Setup WiFi network"""
    ssid = settings.get('wifi_ssid', '')
    password = settings.get('wifi_password', '')

    if not ssid:
        print("✗ WiFi SSID not configured")
        return None

    print(f"Connecting to WiFi: {ssid}")
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(ssid, password)

        # Wait for connection (30 second timeout)
        max_wait = 30
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            max_wait -= 1
            print('.', end='')
            time.sleep(1)

        print()

        if wlan.status() != 3:
            print(f"✗ WiFi connection failed. Status: {wlan.status()}")
            return None
        else:
            ip = wlan.ifconfig()[0]
            print(f"✓ WiFi connected! IP: {ip}")
            return ip
    except Exception as e:
        print(f"✗ WiFi setup failed: {e}")
        return None

def setup_network():
    """Auto-detect and setup network (USB or WiFi)"""
    mode = settings.get('network_mode', 'auto')
    has_usb_lan, has_wifi = detect_network_capability()

    # Determine which mode to use
    if mode == 'auto':
        # Prefer USB LAN if available, fall back to WiFi
        if has_usb_lan:
            print("Auto-mode: Using USB networking")
            ip = setup_usb_network()
            if ip:
                return ip
        if has_wifi:
            print("Auto-mode: Trying WiFi")
            ip = setup_wifi_network()
            if ip:
                return ip
    elif mode == 'usb':
        if has_usb_lan:
            return setup_usb_network()
        else:
            print("✗ USB mode requested but not available")
    elif mode == 'wifi':
        if has_wifi:
            return setup_wifi_network()
        else:
            print("✗ WiFi mode requested but not available")

    print("✗ No network interface available!")
    return None

# LED functions
def get_current_brightness():
    """Calculate current brightness based on time and ramp settings"""
    base_brightness = settings.get('brightness', 100)

    # If brightness ramping is disabled, return base brightness
    if not settings.get('brightness_ramp_enabled', False):
        return base_brightness

    # Calculate if we're in the brightness ramp period
    wake_minutes = time_to_minutes(settings['wake_time'])
    current_minutes = get_current_minutes()
    ramp_duration = settings.get('brightness_ramp_minutes', 15)
    ramp_start_brightness = settings.get('brightness_ramp_start', 10)

    # Check if we're after wake time but within ramp duration
    if current_minutes >= wake_minutes and current_minutes < wake_minutes + ramp_duration:
        # Calculate progress through the ramp (0.0 to 1.0)
        minutes_into_ramp = current_minutes - wake_minutes
        ramp_progress = minutes_into_ramp / ramp_duration

        # Apply easing to the brightness ramp
        eased_progress = ease_in_out_cubic(ramp_progress)

        # Interpolate from start brightness to full brightness
        current_brightness = ramp_start_brightness + (base_brightness - ramp_start_brightness) * eased_progress
        return current_brightness
    elif current_minutes >= wake_minutes + ramp_duration:
        # Past the ramp period, use full brightness
        return base_brightness
    else:
        # Before wake time, use full brightness (color transition handles this period)
        return base_brightness

def apply_brightness(r, g, b):
    """Apply brightness scaling to RGB values"""
    brightness = get_current_brightness() / 100.0
    return (int(r * brightness), int(g * brightness), int(b * brightness))

def convert_color_order(r, g, b):
    """Convert RGB to the configured LED color order"""
    color_order = settings.get('led_color_order', 'RGB')

    if color_order == 'RGB':
        return (r, g, b)
    elif color_order == 'GRB':
        return (g, r, b)
    elif color_order == 'RGBW':
        return (r, g, b, 0)  # 0 for white channel
    elif color_order == 'GRBW':
        return (g, r, b, 0)  # 0 for white channel
    else:
        # Default to RGB if unknown
        return (r, g, b)

def set_all_leds(r, g, b):
    """Set all LEDs to the same color"""
    if np is None or not settings.get('leds_enabled', False):
        return

    # Apply brightness
    r, g, b = apply_brightness(r, g, b)

    # Convert to LED color order
    color = convert_color_order(r, g, b)

    try:
        for i in range(settings.get('num_leds', 12)):
            np[i] = color
        np.write()
    except Exception as e:
        print(f"Error setting LEDs: {e}")

def turn_off_leds():
    """Turn off all LEDs"""
    if np is None:
        return
    try:
        for i in range(settings.get('num_leds', 12)):
            np[i] = (0, 0, 0)
        np.write()
    except (OSError, IndexError) as e:
        print(f"Error turning off LEDs: {e}")

def ease_in_out_cubic(t):
    """Smooth easing function for color transitions (cubic ease-in-out)"""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2

def interpolate_color(color1, color2, ratio):
    """Interpolate between two colors with smooth easing"""
    # Apply easing function for smoother visual transition
    eased_ratio = ease_in_out_cubic(ratio)
    r = int(color1[0] + (color2[0] - color1[0]) * eased_ratio)
    g = int(color1[1] + (color2[1] - color1[1]) * eased_ratio)
    b = int(color1[2] + (color2[2] - color1[2]) * eased_ratio)
    return [r, g, b]

def time_to_minutes(time_str):
    parts = time_str.split(':')
    return int(parts[0]) * 60 + int(parts[1])

def should_flash():
    """Check if we should be flashing LEDs right now"""
    global flash_start_time

    if not settings.get('flash_enabled', False):
        flash_start_time = None
        return False

    if not settings.get('bedtime_enabled', True):
        flash_start_time = None
        return False

    bedtime_minutes = time_to_minutes(settings.get('bedtime', '21:00'))
    current_minutes = get_current_minutes()

    # Start flashing at bedtime
    if current_minutes == bedtime_minutes:
        if flash_start_time is None:
            flash_start_time = time.time()

        # Check if flash duration has elapsed
        elapsed = time.time() - flash_start_time
        flash_duration = settings.get('flash_duration', 10)

        if elapsed < flash_duration:
            return True
        else:
            flash_start_time = None
            return False
    else:
        # Reset flash if we're not at bedtime
        flash_start_time = None
        return False

def update_leds():
    """Update LED colors based on current time"""
    global last_flash_toggle

    if not settings.get('leds_enabled', False):
        turn_off_leds()
        return

    wake_minutes = time_to_minutes(settings['wake_time'])
    transition_minutes = settings['transition_minutes']
    transition_start = wake_minutes - transition_minutes
    current_minutes = get_current_minutes()

    # Handle bedtime (night mode) transition
    if settings.get('bedtime_enabled', True):
        bedtime_minutes = time_to_minutes(settings.get('bedtime', '21:00'))

        # Determine if we're in "stay in bed" period
        # This handles overnight periods (e.g., 9pm to 7am)
        if bedtime_minutes > wake_minutes:
            # Normal case: bedtime is after wake time (e.g., 21:00 to 07:00 next day)
            in_stay_period = current_minutes >= bedtime_minutes or current_minutes < transition_start
        else:
            # Edge case: bedtime is before wake time same day (unusual)
            in_stay_period = current_minutes >= bedtime_minutes and current_minutes < transition_start

        if in_stay_period:
            # It's bedtime/night - show stay color
            color = settings['stay_color']
            set_all_leds(color[0], color[1], color[2])
            return

    # Normal wake-up transition logic
    if current_minutes >= wake_minutes:
        color = settings['wake_color']
    elif current_minutes >= transition_start:
        progress = (current_minutes - transition_start) / transition_minutes
        color = interpolate_color(settings['stay_color'], settings['wake_color'], progress)
    else:
        color = settings['stay_color']

    # Handle flashing if enabled
    if should_flash():
        flash_interval = settings.get('flash_interval', 500) / 1000.0  # Convert to seconds
        current_time = time.time()

        # Toggle LEDs based on interval
        if current_time - last_flash_toggle >= flash_interval:
            last_flash_toggle = current_time
            # Toggle between color and off
            if int(current_time / flash_interval) % 2 == 0:
                set_all_leds(color[0], color[1], color[2])
            else:
                set_all_leds(0, 0, 0)
        return

    set_all_leds(color[0], color[1], color[2])

def html_escape(text):
    """Escape HTML special characters to prevent injection"""
    if isinstance(text, int):
        return str(text)
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text

# Web interface
def web_page():
    current_time = get_current_time_str()
    current_date = get_current_date_str()
    wake_minutes = time_to_minutes(settings['wake_time'])
    transition_minutes = settings['transition_minutes']
    transition_start = wake_minutes - transition_minutes
    transition_hours = transition_start // 60
    transition_mins = transition_start % 60
    
    rtc_status = "🔋 DS3231 RTC Active" if external_rtc else "⚠️ Internal RTC Only"
    
    # DST status
    dst_status = ""
    dst_region = settings.get('dst_region', None)
    if dst_region:
        utc_time = rtc.datetime()
        utc_timestamp = time.mktime((utc_time[0], utc_time[1], utc_time[2],
                                     utc_time[4], utc_time[5], utc_time[6], 0, 0))
        if is_dst_active(utc_timestamp, dst_region):
            dst_status = " (DST Active ☀️)"
    
    # LED status
    led_status = "🟢 ON" if settings.get('leds_enabled', False) else "🔴 OFF"
    
    # Timezone options
    tz_options = ""
    for tz, offset in TIMEZONES.items():
        selected = "selected" if tz == settings.get('timezone', 'UTC') else ""
        hours = offset // 60
        mins = abs(offset % 60)
        sign = "+" if offset >= 0 else ""
        tz_escaped = html_escape(tz)
        tz_options += f'<option value="{tz_escaped}" {selected}>{tz_escaped} (UTC{sign}{hours}:{mins:02d})</option>\n'
    
    # DST region options
    dst_options = ""
    current_dst = settings.get('dst_region', 'None')
    dst_options += f'<option value="None" {"selected" if current_dst == "None" else ""}>No DST</option>\n'
    for region in DST_RULES.keys():
        selected = "selected" if region == current_dst else ""
        region_escaped = html_escape(region)
        dst_options += f'<option value="{region_escaped}" {selected}>{region_escaped}</option>\n'
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta charset="UTF-8">
    <title>Bedtime Clock</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            max-width: 600px;
            margin: 20px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-top: 0;
            font-size: 28px;
        }}
        .clock-display {{
            text-align: center;
            font-size: 48px;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
        }}
        .date-display {{
            text-align: center;
            font-size: 18px;
            color: #666;
            margin-bottom: 10px;
        }}
        .status-bar {{
            display: flex;
            justify-content: space-between;
            padding: 10px;
            margin: 10px 0 20px 0;
            background: #f8f9fa;
            border-radius: 8px;
            font-size: 14px;
        }}
        .status-item {{
            flex: 1;
            text-align: center;
            padding: 5px;
        }}
        .led-status {{
            font-weight: bold;
            color: {('#4caf50' if settings.get('leds_enabled') else '#f44336')};
        }}
        .form-group {{
            margin: 20px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 12px;
            border: 2px solid #e9ecef;
        }}
        .form-group h3 {{
            margin-top: 0;
            color: #495057;
            font-size: 16px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
            font-size: 14px;
        }}
        input, select {{
            width: 100%;
            padding: 12px;
            margin-bottom: 10px;
            border: 2px solid #ddd;
            border-radius: 8px;
            box-sizing: border-box;
            font-size: 16px;
        }}
        input[type="color"] {{
            height: 50px;
            cursor: pointer;
        }}
        input[type="range"] {{
            cursor: pointer;
        }}
        .slider-value {{
            display: inline-block;
            margin-left: 10px;
            font-weight: bold;
            color: #667eea;
        }}
        .toggle-switch {{
            display: flex;
            align-items: center;
            margin: 15px 0;
        }}
        .toggle-switch input[type="checkbox"] {{
            width: auto;
            margin-right: 10px;
        }}
        button {{
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            margin-top: 10px;
        }}
        button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
        .status {{
            text-align: center;
            padding: 20px;
            margin-top: 20px;
            background: #e8f5e9;
            border-radius: 12px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            padding: 8px;
            background: white;
            border-radius: 6px;
        }}
        .color-preview {{
            display: inline-block;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            vertical-align: middle;
            margin-left: 10px;
            border: 2px solid #ddd;
        }}
        small {{
            color: #666;
            font-size: 12px;
            display: block;
            margin-top: 5px;
        }}
        .warning {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            font-size: 14px;
        }}
    </style>
    <script>
        function setCurrentTime() {{
            const now = new Date();

            // Get UTC date in YYYY-MM-DD format
            const year = now.getUTCFullYear();
            const month = String(now.getUTCMonth() + 1).padStart(2, '0');
            const day = String(now.getUTCDate()).padStart(2, '0');
            const dateString = `${{year}}-${{month}}-${{day}}`;

            // Get UTC time in HH:MM format
            const hours = String(now.getUTCHours()).padStart(2, '0');
            const minutes = String(now.getUTCMinutes()).padStart(2, '0');
            const timeString = `${{hours}}:${{minutes}}`;

            // Set the input fields
            document.getElementById('current_date').value = dateString;
            document.getElementById('current_time').value = timeString;

            // Visual feedback
            alert(`Time set to: ${{dateString}} ${{timeString}} UTC`);
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>🛏️ Bedtime Clock</h1>
        <div class="clock-display">{current_time}</div>
        <div class="date-display">{current_date}</div>
        
        <div class="status-bar">
            <div class="status-item">
                {rtc_status}{dst_status}
            </div>
            <div class="status-item led-status">
                LEDs: {led_status}
            </div>
        </div>
        
        <form action="/update" method="POST">
            <div class="form-group">
                <h3>💡 LED Configuration</h3>
                
                <div class="toggle-switch">
                    <input type="checkbox" name="leds_enabled" id="leds_enabled" {"checked" if settings.get('leds_enabled', False) else ""}>
                    <label for="leds_enabled" style="margin: 0;">Enable LEDs</label>
                </div>
                <small>Turn LEDs ON/OFF. LEDs are OFF by default for safety.</small>
                
                <label style="margin-top: 15px;">Number of LEDs in Ring:</label>
                <input type="number" name="num_leds" value="{settings.get('num_leds', 12)}"
                       min="1" max="256" required>
                <small>Common sizes: 8, 12, 16, 24, 60. Change this to match your NeoPixel ring.</small>

                <label style="margin-top: 15px;">LED Type (Color Order):</label>
                <select name="led_color_order">
                    <option value="RGB" {"selected" if settings.get('led_color_order', 'RGB') == 'RGB' else ""}>RGB (WS2812 standard)</option>
                    <option value="GRB" {"selected" if settings.get('led_color_order', 'RGB') == 'GRB' else ""}>GRB (WS2812B/SK6812)</option>
                    <option value="RGBW" {"selected" if settings.get('led_color_order', 'RGB') == 'RGBW' else ""}>RGBW (SK6812 RGBW)</option>
                    <option value="GRBW" {"selected" if settings.get('led_color_order', 'RGB') == 'GRBW' else ""}>GRBW (WS2812 RGBW)</option>
                </select>
                <small>If colors look wrong (e.g., red shows as green), try a different order. Most common: GRB.</small>
                
                <label style="margin-top: 15px;">Brightness: <span class="slider-value">{settings.get('brightness', 100)}%</span></label>
                <input type="range" name="brightness" value="{settings.get('brightness', 100)}" 
                       min="0" max="100" step="5" oninput="this.previousElementSibling.querySelector('.slider-value').textContent = this.value + '%'">
                <small>Adjust LED brightness (0-100%). Lower values save power and reduce eye strain.</small>
            </div>
            
            <div class="form-group">
                <h3>📡 Network Settings</h3>
                <label>Network Mode:</label>
                <select name="network_mode">
                    <option value="auto" {"selected" if settings.get('network_mode', 'auto') == 'auto' else ""}>Auto-detect (USB then WiFi)</option>
                    <option value="usb" {"selected" if settings.get('network_mode', 'auto') == 'usb' else ""}>USB Only (Pico W)</option>
                    <option value="wifi" {"selected" if settings.get('network_mode', 'auto') == 'wifi' else ""}>WiFi Only</option>
                </select>
                <small>Auto-detect works on all boards. Choose manually if you have both capabilities.</small>

                <label style="margin-top: 15px;">WiFi SSID (Network Name):</label>
                <input type="text" name="wifi_ssid" value="{html_escape(settings.get('wifi_ssid', ''))}" placeholder="Your WiFi Network">

                <label>WiFi Password:</label>
                <input type="password" name="wifi_password" value="{html_escape(settings.get('wifi_password', ''))}" placeholder="WiFi Password">
                <small>Leave blank if using USB networking. Required for WiFi mode.</small>
            </div>

            <div class="form-group">
                <h3>🌍 Timezone Settings</h3>
                <label>Timezone:</label>
                <select name="timezone">
                    {tz_options}
                </select>

                <label>DST Region:</label>
                <select name="dst_region">
                    {dst_options}
                </select>

                <div class="toggle-switch">
                    <input type="checkbox" name="dst_enabled" id="dst_enabled" {"checked" if settings.get('dst_enabled', True) else ""}>
                    <label for="dst_enabled" style="margin: 0;">Enable automatic DST</label>
                </div>

                <div class="toggle-switch" style="margin-top: 15px;">
                    <input type="checkbox" name="use_external_rtc" id="use_external_rtc" {"checked" if settings.get('use_external_rtc', True) else ""}>
                    <label for="use_external_rtc" style="margin: 0;">Use External RTC (DS3231)</label>
                </div>
                <small>Enable to use DS3231 hardware RTC for accurate timekeeping. Disable to use internal RTC only.</small>
            </div>
            
            <div class="form-group">
                <h3>⏰ Time Settings</h3>
                <button type="button" onclick="setCurrentTime()" style="margin-bottom: 15px; background: linear-gradient(135deg, #43a047 0%, #66bb6a 100%);">
                    🕐 Get Current Time from This Device
                </button>
                <small style="margin-bottom: 15px;">Click to automatically fill in the current date and time from your computer/phone.</small>

                <label>Current Date (UTC):</label>
                <input type="date" name="current_date" id="current_date" value="{current_date}" required>

                <label>Current Time (UTC, 24-hour):</label>
                <input type="time" name="current_time" id="current_time" value="{current_time}" required>
                <small>Set UTC time - local time is calculated automatically</small>
            </div>
            
            <div class="form-group">
                <h3>🌅 Wake-Up Settings</h3>
                <label>Wake-up Time (Local Time):</label>
                <input type="time" name="wake_time" value="{settings['wake_time']}" required>

                <label>Transition Duration (minutes):</label>
                <input type="number" name="transition_minutes" value="{settings['transition_minutes']}"
                       min="0" max="120" required>
                <small>Time to gradually change from stay color to wake color.</small>

                <div class="toggle-switch" style="margin-top: 20px;">
                    <input type="checkbox" name="bedtime_enabled" id="bedtime_enabled" {"checked" if settings.get('bedtime_enabled', True) else ""}>
                    <label for="bedtime_enabled" style="margin: 0;">Enable Bedtime (Night Mode)</label>
                </div>
                <small>Automatically switch back to stay color at bedtime.</small>

                <label style="margin-top: 15px;">Bedtime (Local Time):</label>
                <input type="time" name="bedtime" value="{settings.get('bedtime', '21:00')}" required>
                <small>Time to switch back to stay color (e.g., 9:00 PM). Creates a full day/night cycle.</small>

                <div class="toggle-switch" style="margin-top: 20px;">
                    <input type="checkbox" name="brightness_ramp_enabled" id="brightness_ramp_enabled" {"checked" if settings.get('brightness_ramp_enabled', False) else ""}>
                    <label for="brightness_ramp_enabled" style="margin: 0;">Enable Brightness Ramp</label>
                </div>
                <small>Gradually increase brightness AFTER reaching wake color for an even gentler wake-up.</small>

                <label style="margin-top: 15px;">Brightness Ramp Duration (minutes):</label>
                <input type="number" name="brightness_ramp_minutes" value="{settings.get('brightness_ramp_minutes', 15)}"
                       min="1" max="60" required>
                <small>How long to ramp from starting brightness to full brightness after wake time.</small>

                <label style="margin-top: 15px;">Starting Brightness: <span class="slider-value">{settings.get('brightness_ramp_start', 10)}%</span></label>
                <input type="range" name="brightness_ramp_start" value="{settings.get('brightness_ramp_start', 10)}"
                       min="1" max="100" step="5" oninput="this.previousElementSibling.querySelector('.slider-value').textContent = this.value + '%'">
                <small>Brightness level when wake color is first reached (then ramps up to full brightness).</small>

                <div class="toggle-switch" style="margin-top: 20px;">
                    <input type="checkbox" name="flash_enabled" id="flash_enabled" {"checked" if settings.get('flash_enabled', False) else ""}>
                    <label for="flash_enabled" style="margin: 0;">Enable Bedtime Flash Notification</label>
                </div>
                <small>Flash LEDs at bedtime to remind you it's time to sleep.</small>

                <label style="margin-top: 15px;">Flash Duration (seconds):</label>
                <input type="number" name="flash_duration" value="{settings.get('flash_duration', 10)}"
                       min="1" max="300" required>
                <small>How long to flash LEDs when bedtime is reached.</small>

                <label style="margin-top: 15px;">Flash Speed: <span class="slider-value">{settings.get('flash_interval', 500)}ms</span></label>
                <input type="range" name="flash_interval" value="{settings.get('flash_interval', 500)}"
                       min="100" max="2000" step="100" oninput="this.previousElementSibling.querySelector('.slider-value').textContent = this.value + 'ms'">
                <small>Flash on/off interval in milliseconds (100ms = very fast, 2000ms = slow).</small>
            </div>
            
            <div class="form-group">
                <h3>🎨 Color Settings</h3>
                <label>Stay in Bed Color:
                    <span class="color-preview" style="background-color: rgb({settings['stay_color'][0]}, {settings['stay_color'][1]}, {settings['stay_color'][2]});"></span>
                </label>
                <input type="color" name="stay_color" 
                       value="#{settings['stay_color'][0]:02x}{settings['stay_color'][1]:02x}{settings['stay_color'][2]:02x}">
                
                <label>Wake-up Color:
                    <span class="color-preview" style="background-color: rgb({settings['wake_color'][0]}, {settings['wake_color'][1]}, {settings['wake_color'][2]});"></span>
                </label>
                <input type="color" name="wake_color" 
                       value="#{settings['wake_color'][0]:02x}{settings['wake_color'][1]:02x}{settings['wake_color'][2]:02x}">
            </div>
            
            <button type="submit">💾 Save All Settings</button>
        </form>
        
        {"<div class='warning'>⚠️ LEDs are currently OFF. Enable them in LED Configuration above.</div>" if not settings.get('leds_enabled', False) else ""}
        
        <div class="status">
            <p><strong>Current Schedule (Local Time):</strong></p>
            <div class="info-row">
                <span>Transition Starts:</span>
                <span>{transition_hours:02d}:{transition_mins:02d}</span>
            </div>
            <div class="info-row">
                <span>Wake-up Time:</span>
                <span>{settings['wake_time']}</span>
            </div>
            <div class="info-row">
                <span>LED Count:</span>
                <span>{settings.get('num_leds', 12)} LEDs</span>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return html

def url_decode(s):
    """Decode URL-encoded string"""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                result.append(chr(int(s[i+1:i+3], 16)))
                i += 3
            except ValueError:
                result.append(s[i])
                i += 1
        elif s[i] == '+':
            result.append(' ')
            i += 1
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)

def parse_post_data(data):
    params = {}
    for item in data.split('&'):
        if '=' in item:
            key, value = item.split('=', 1)
            params[key] = url_decode(value)
    return params

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]

def set_time_from_string(date_str, time_str):
    date_parts = date_str.split('-')
    year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
    time_parts = time_str.split(':')
    hour, minute = int(time_parts[0]), int(time_parts[1])
    rtc.datetime((year, month, day, 0, hour, minute, 0, 0))
    print(f"UTC time set to: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")
    if external_rtc:
        write_ds3231_time(year, month, day, hour, minute, 0)

def handle_request(conn):
    try:
        request = conn.recv(2048).decode()
        
        if 'POST /update' in request:
            parts = request.split('\r\n\r\n')
            if len(parts) > 1:
                data = parts[1]
                params = parse_post_data(data)
                
                # Check if LED settings changed
                old_led_count = settings.get('num_leds', 12)
                old_color_order = settings.get('led_color_order', 'RGB')
                new_led_count = int(params.get('num_leds', 12))
                new_color_order = params.get('led_color_order', 'RGB')

                # Update LED settings first
                settings['leds_enabled'] = 'leds_enabled' in params
                settings['num_leds'] = new_led_count
                settings['brightness'] = int(params.get('brightness', 100))
                settings['led_color_order'] = new_color_order

                # Reinitialize NeoPixel if count or color order changed
                if old_led_count != new_led_count or old_color_order != new_color_order:
                    print(f"LED settings changed: {old_led_count} → {new_led_count} LEDs, {old_color_order} → {new_color_order}")
                    initialize_neopixel()
                
                # Update network settings
                if 'network_mode' in params:
                    settings['network_mode'] = params['network_mode']
                if 'wifi_ssid' in params:
                    settings['wifi_ssid'] = params['wifi_ssid']
                if 'wifi_password' in params:
                    settings['wifi_password'] = params['wifi_password']

                # Update timezone settings
                if 'timezone' in params:
                    tz = params['timezone']
                    settings['timezone'] = tz
                    settings['utc_offset_minutes'] = TIMEZONES.get(tz, 0)

                dst_region = params.get('dst_region', 'None')
                settings['dst_region'] = dst_region if dst_region != 'None' else None
                settings['dst_enabled'] = 'dst_enabled' in params

                # Update RTC setting
                old_rtc_setting = settings.get('use_external_rtc', True)
                settings['use_external_rtc'] = 'use_external_rtc' in params

                # Reinitialize RTC if setting changed
                if old_rtc_setting != settings['use_external_rtc']:
                    print(f"RTC setting changed to: {settings['use_external_rtc']}")
                    initialize_external_rtc()
                
                # Update time
                if 'current_date' in params and 'current_time' in params:
                    set_time_from_string(params['current_date'], params['current_time'])
                
                # Update other settings
                if 'wake_time' in params:
                    settings['wake_time'] = params['wake_time']
                if 'bedtime' in params:
                    settings['bedtime'] = params['bedtime']
                settings['bedtime_enabled'] = 'bedtime_enabled' in params
                if 'stay_color' in params:
                    settings['stay_color'] = hex_to_rgb(params['stay_color'])
                if 'wake_color' in params:
                    settings['wake_color'] = hex_to_rgb(params['wake_color'])
                if 'transition_minutes' in params:
                    settings['transition_minutes'] = int(params['transition_minutes'])

                # Update brightness ramp settings
                settings['brightness_ramp_enabled'] = 'brightness_ramp_enabled' in params
                if 'brightness_ramp_minutes' in params:
                    settings['brightness_ramp_minutes'] = int(params['brightness_ramp_minutes'])
                if 'brightness_ramp_start' in params:
                    settings['brightness_ramp_start'] = int(params['brightness_ramp_start'])

                # Update flash settings
                settings['flash_enabled'] = 'flash_enabled' in params
                if 'flash_duration' in params:
                    settings['flash_duration'] = int(params['flash_duration'])
                if 'flash_interval' in params:
                    settings['flash_interval'] = int(params['flash_interval'])
                
                save_settings()
                update_leds()
            
            response = "HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n"
            conn.send(response.encode())
        else:
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            response += web_page()
            conn.send(response.encode())
    except Exception as e:
        print("Error handling request:", e)
    finally:
        conn.close()

def run_server(ip):
    addr = socket.getaddrinfo(ip, 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    
    print(f'Web server running on http://{ip}')
    
    s.setblocking(False)
    last_update = time.time()
    last_sync = time.time()
    
    while True:
        try:
            conn, addr = s.accept()
            handle_request(conn)
        except OSError:
            pass
        
        if time.time() - last_update > 10:
            update_leds()
            last_update = time.time()
        
        if external_rtc and time.time() - last_sync > 3600:
            sync_time_from_ds3231()
            last_sync = time.time()
        
        time.sleep(0.1)

def main():
    print("=" * 50)
    print("Bedtime Clock - Configurable LED Version")
    print("=" * 50)
    
    # LEDs OFF by default
    turn_off_leds()
    
    load_settings()
    
    # Turn off LEDs if not enabled
    if not settings.get('leds_enabled', False):
        turn_off_leds()
        print("⚠️ LEDs are DISABLED. Enable via web interface.")
    
    if external_rtc:
        if sync_time_from_ds3231():
            print("✓ Time synced from DS3231")
    
    try:
        ip = setup_network()
        if ip:
            print("\n" + "=" * 50)
            print(f"Ready! Open http://{ip} in your browser")
            print("=" * 50 + "\n")
        else:
            print("\n" + "=" * 50)
            print("⚠️ WARNING: No network available!")
            print("LEDs will still work, but web config is unavailable")
            print("Connect via USB serial to configure WiFi settings")
            print("=" * 50 + "\n")
            # Continue running even without network (LEDs still work)
    except Exception as e:
        print("Network setup failed:", e)
        print("Continuing without network...")
        ip = None
    
    update_leds()

    if ip:
        run_server(ip)
    else:
        # No network - just run LED updates in a loop
        print("Running in offline mode (LEDs only)")
        while True:
            update_leds()
            if external_rtc and time.time() % 3600 < 10:  # Sync hourly
                sync_time_from_ds3231()
            time.sleep(10)

if __name__ == '__main__':
    main()