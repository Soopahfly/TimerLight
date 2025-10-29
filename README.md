# Bedtime Clock with NeoPixel Ring

A visual sleep/wake indicator for kids (or adults!) using a Raspberry Pi Pico and WS2812 LED ring. Gradually transitions colors to show when it's time to stay in bed vs. when it's okay to get up.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![MicroPython](https://img.shields.io/badge/MicroPython-1.24-green.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Pico-red.svg)

## Features

### Visual Indicators
- **Stay in Bed Color** (default: red) - Signals it's still sleep time
- **Wake Color** (default: green) - Signals it's okay to get up
- **Smooth Color Transition** - Gradual change from red to green before wake time
- **Brightness Ramping** - Optional gradual brightness increase after wake color
- **Bedtime Mode** - Automatic switch back to sleep color at night
- **Flash Notification** - Optional flashing at bedtime to signal sleep time

### Hardware Support
- **Multiple Boards**: Raspberry Pi Pico, Pico W, Pico 2, Waveshare RP2040-Mini, and any RP2040-based board
- **Flexible LED Support**: Any WS2812/WS2812B/SK6812 ring (8, 12, 16, 24, 60 LEDs)
- **Color Order Selection**: RGB, GRB, RGBW, GRBW support
- **Optional RTC**: DS3231 real-time clock for accurate timekeeping
- **Network Options**: USB networking (Pico W) or WiFi

### Configuration
- **Web Interface**: Beautiful, mobile-friendly GUI for all settings
- **Timezone Support**: Automatic timezone conversion with DST handling
- **Persistent Settings**: All configurations saved to flash memory
- **No Code Changes**: Everything configurable via web interface

## Hardware Requirements

### Required
- Raspberry Pi Pico (any variant) or compatible RP2040 board
- WS2812/WS2812B LED ring (any size)
- USB cable for power and programming

### Optional
- DS3231 RTC module (for accurate timekeeping when offline)

## Wiring

### LED Ring (WS2812)
```
WS2812 Ring          Raspberry Pi Pico
─────────────────────────────────────
DI (Data In)  ────→  GPIO 0 (Pin 1)
5V            ────→  VBUS (Pin 40)
GND           ────→  GND (Pin 3 or 38)
```

### DS3231 RTC (Optional)
```
DS3231 RTC           Raspberry Pi Pico
─────────────────────────────────────
SDA           ────→  GPIO 4 (Pin 6)
SCL           ────→  GPIO 5 (Pin 7)
VCC           ────→  3V3 (Pin 36)
GND           ────→  GND (Pin 8)
```

## Installation

### 1. Flash MicroPython Firmware
1. Download MicroPython for RP2040 from [micropython.org](https://micropython.org/download/rp2040/)
2. Hold BOOTSEL button while plugging in USB
3. Drag and drop the `.uf2` file to the RPI-RP2 drive

### 2. Upload Code
**Using Thonny IDE (Recommended):**
1. Install [Thonny](https://thonny.org/)
2. Select "MicroPython (Raspberry Pi Pico)" as interpreter
3. Open `Timerclock.py`
4. File → Save As → Raspberry Pi Pico → Save as `main.py`

**Using Command Line:**
```bash
pip install mpremote
mpremote connect COM3 cp Timerclock.py :main.py
```

### 3. Configure WiFi (if not using Pico W USB networking)
Create or edit `settings.json` on the Pico:
```json
{
  "wifi_ssid": "YourWiFiNetwork",
  "wifi_password": "YourPassword",
  "network_mode": "wifi"
}
```

## Usage

### First Boot
1. Connect Pico to power
2. Watch serial output for IP address
3. Open web browser to displayed IP address
4. Configure all settings via GUI

### Configuration Options

**LED Settings:**
- Number of LEDs in ring
- LED color order (RGB/GRB/RGBW/GRBW)
- Overall brightness (0-100%)
- Enable/disable LEDs

**Time Settings:**
- Wake-up time
- Bedtime (night mode)
- Transition duration before wake-up
- Timezone and DST settings

**Advanced Features:**
- Brightness ramp (gradual increase after wake color)
- Bedtime flash notification
- External RTC enable/disable

**Network Settings:**
- Auto-detect, USB, or WiFi mode
- WiFi credentials

### Example Schedule

**Default Settings:**
- **9:00 PM** - Bedtime (flash notification, switches to red)
- **9:00 PM - 6:30 AM** - Red (stay in bed)
- **6:30 AM - 7:00 AM** - Red → Green transition (wake-up soon)
- **7:00 AM** - Green at 10% brightness
- **7:00 AM - 7:15 AM** - Brightness ramps 10% → 100%
- **7:15 AM - 9:00 PM** - Green at 100% (okay to be awake)

## Use Cases

- **Kids' Bedtime Clock** - Visual indicator for when to stay in bed
- **Sleep Training** - Consistent visual cues for sleep schedules
- **Smart Alarm Clock** - Gentle wake-up with gradual light
- **Bedroom Ambient Light** - Automatic day/night lighting
- **Shift Workers** - Customizable sleep/wake schedules

## Configuration Examples

### For Young Children (Early Bedtime)
- Bedtime: 7:00 PM
- Wake time: 6:30 AM
- Flash enabled for bedtime reminder

### For Teenagers
- Bedtime: 10:00 PM
- Wake time: 7:00 AM
- Brightness ramp enabled for gentle wake-up

### For Adults/Shift Workers
- Fully customizable to any schedule
- Disable bedtime if not needed
- Adjust colors to preference

## Technical Details

- **Language**: MicroPython
- **Web Server**: Built-in async socket server
- **Storage**: JSON configuration on flash
- **Update Rate**: 10 seconds (configurable)
- **Network**: Auto-detection (USB LAN or WiFi)
- **Timezone**: Full DST support (US, EU, UK, AU)

## Troubleshooting

**LEDs show wrong colors:**
- Try changing LED Color Order in GUI (most common: GRB)

**Can't connect to WiFi:**
- Check SSID/password spelling
- Ensure 2.4GHz WiFi (not 5GHz)
- Check serial output for error messages

**Time drifts:**
- Add DS3231 RTC module for accurate timekeeping
- Enable "Use External RTC" in GUI

**Network unavailable:**
- Code works in offline mode (LEDs only)
- Pre-configure settings via `settings.json`

## Credits

Built with MicroPython for RP2040. Generated with assistance from Claude Code.

## License

MIT License - Feel free to modify and distribute!

## Contributing

Contributions welcome! This is a personal project but feel free to fork and adapt for your needs.

---

**Happy sleeping!** 🛏️ 🌙
