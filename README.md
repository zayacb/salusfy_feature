# Home Assistant Custom Component - Salus iT500
Enhanced integration for Salus iT500 thermostats with Home Assistant (http://www.home-assistant.io)

Based on the original work by [@floringhimie](https://github.com/floringhimie/salusfy), this version provides significant improvements and new features.

## Overview

This component interfaces with the Salus iT500 cloud API (salus-it500.com) to control and monitor your Salus thermostats. Compatible with devices like RT301i, RT500, and other models that work with the iT500 system.

**⚠️ This is not an official integration.**

## What's New in This Enhanced Version

### Major Improvements

#### 1. **Modern Config Flow Integration**
- ✅ **UI-based setup** - No more manual configuration.yaml editing
- ✅ **Automatic device discovery** - No need to manually find device IDs
- ✅ **Proper integration setup** - Add via Settings → Devices & Services → Add Integration → "Salus iT500"

#### 2. **Complete API Library (`pyit500`)**
A full-featured async Python library for the Salus iT500 API with:
- Comprehensive device attribute support
- Type-safe enums for all device states
- Support for system types CH1 and CH1+CH2 (a hot water zone, if present, is ignored)
- Proper authentication and token management
- Full async/await support

#### 3. **Multi-Zone Heating Support**
- ✅ Automatic detection of system configuration
- ✅ Support for dual heating zones (CH1 + CH2)
- ✅ Each zone appears as a separate climate entity

#### 4. **Preset Modes for Heating**
- **Auto** - Follow the programmed schedule
- **Manual** - Manual temperature control
- **Temp Hold** - Temporarily hold a temperature
- Easy switching between modes without changing HVAC state

#### 5. **Robust Error Handling**
- ✅ Automatic retry logic with exponential backoff
- ✅ Graceful handling of API server errors (500, 502, 503, 504)
- ✅ Connection error recovery with retry attempts
- ✅ Token refresh on authentication failures
- ✅ Detailed error logging for troubleshooting

#### 6. **Optimistic State Updates**
- ✅ Instant UI feedback when changing settings
- ✅ No lag when adjusting temperature or modes
- ✅ Automatic state synchronization after changes

#### 7. **Smart API Management**
- ✅ DataUpdateCoordinator for efficient polling
- ✅ Rate limiting to prevent API overload (5-second minimum between updates)
- ✅ Debounced refresh requests
- ✅ Configurable update intervals (30 seconds default)
- ✅ Reduced debug logging to minimize noise

#### 8. **Temperature Unit Support**
- ✅ Automatic detection of Celsius or Fahrenheit
- ✅ Proper temperature ranges based on unit setting
- ✅ Correct min/max temperature limits

#### 9. **Additional Features**
- ✅ Frost protection status monitoring
- ✅ Schedule type information
- ✅ Relay status (heating/idle/off)
- ✅ Extra state attributes for advanced automation
- ✅ Device information and descriptions
- ✅ Unique IDs for all entities (proper entity registry support)

### Technical Improvements

- **Modern Home Assistant architecture** - Uses ConfigEntry, DataUpdateCoordinator, CoordinatorEntity
- **Full async implementation** - No blocking calls
- **Type hints throughout** - Better code quality and IDE support
- **Proper entity lifecycle management** - Clean setup and teardown
- **Localization support** - English and Czech translations included
- **API workarounds** - Handles quirks like TEMP_HOLD → AUTO mode transitions
- **Comprehensive testing** - Better reliability through code improvements

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right
4. Select "Custom repositories"
5. Add this repository URL with category "Integration"
6. Click "Install"
7. Restart Home Assistant

### Manual Installation
1. Create directory: `config/custom_components/salusfy`
2. Copy all files from this repository's `custom_components/salusfy/` to the directory
3. Restart Home Assistant

## Updates and releases

Install through HACS (custom repository) and Home Assistant will show updates as an `update.*` entity. A restart is required after every update.

To publish a version: bump `version` in `custom_components/salusfy/manifest.json`, then push a matching tag (for example `git tag v1.1.0 && git push origin v1.1.0`). The `Release` workflow checks that the tag equals the manifest version and creates a GitHub Release, which HACS then offers as an update.

## Configuration

### Setup via UI (Recommended)
1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Salus iT500"**
4. Enter your salus-it500.com credentials:
   - Email address
   - Password
5. The integration will automatically discover your devices

### Legacy configuration.yaml (Deprecated)
The old YAML configuration method is no longer supported. Please use the UI configuration flow.

## Scope

This fork is **heating only**. Systems with a hot water zone (CH1 + Hot Water) still work: the heating zone is exposed as a climate entity, the hot water zone is not exposed to Home Assistant.

## Reliability

- If the Salus cloud is unreachable at startup, Home Assistant retries the setup automatically.
- If Salus rejects the saved password, Home Assistant starts a re-authentication flow (Settings → Devices & Services). Requires a recent Home Assistant version (2024.11+).

## Supported Features

### Climate Entity (Heating Zones)
- Current temperature reading
- Target temperature control (5-35°C / 41-95°F)
- HVAC modes: Heat, Off
- Preset modes: Auto, Manual, Temp Hold
- Current action: Heating, Idle, Off
- Frost protection status
- Schedule type information

## Known Issues & Workarounds

### API Rate Limiting
The Salus API may block your IP if too many requests are made. This version includes:
- Built-in rate limiting (minimum 5 seconds between requests)
- Automatic retry logic for temporary failures
- Debounced refresh requests

If you still experience blocking:
- Restart your router (for PPOE connections)
- Contact Salus support
- The integration will automatically recover once the block is lifted

### API Response Delays
The Salus API can be slow to reflect changes (10-30 seconds). This version uses:
- Optimistic state updates for instant UI feedback
- Automatic refresh after changes to sync state
- Configurable polling intervals

## Troubleshooting

### Enable Debug Logging
Add to `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.salusfy: debug
```

### Common Issues
1. **"Invalid authentication"** - Check your email/password for salus-it500.com
2. **"No devices found"** - Ensure your device is set up in the Salus app
3. **"Cannot connect"** - Check internet connection and Salus API status
4. **Slow updates** - Normal behavior, Salus API has inherent delays

## Credits

**Original Component**: [@floringhimie](https://github.com/floringhimie/salusfy)

**Enhanced Version**: Significant improvements including config flow, multi-zone heating, re-authentication flow, robust error handling, and complete API implementation.

## Contributing

Issues and pull requests are welcome! Please report bugs or suggest features via GitHub issues.

## License

This project maintains the same license as the original work.
