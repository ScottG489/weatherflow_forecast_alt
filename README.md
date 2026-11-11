# WeatherFlow Forecast and Sensor integration (alternate fork)

This fork provides Tempest current conditions, daily/hourly forecasts and optional
station sensors in Home Assistant. Minimum supported Home Assistant: **2025.3.4**.

## Authentication

Choose **Public station** and enter the number from a public station URL such as
`https://tempestwx.com/station/95467`. Leave the personal-token field empty.
The integration obtains and renews the anonymous session used by Tempest's map.

For a station you own, choose **Personal access token** and generate a token under
[Tempest Settings → Data Authorizations](https://tempestwx.com/settings/tokens).
This mode uses the documented owner API and does not require anonymous sessions.

Public-map access depends on Tempest's website authentication and may change.
See Tempest's [remote data access policy](https://weatherflow.github.io/Tempest/api/remote-developer-policy.html)
for their supported third-party access options.

## Installation

In HACS / Marketplace, add `ScottG489/weatherflow_forecast_alt` as a custom
integration repository and install it. This fork is separate from the upstream
WeatherFlow Forecast integration.

For manual installation, copy `custom_components/weatherflow_forecast_alt` from
this repository into your Home Assistant configuration's `custom_components`
directory. The installed directory must be named `weatherflow_forecast_alt`.

Restart Home Assistant after installing or updating integration files, then open
**Settings → Devices & services → Add integration → WeatherFlow Forecast**.

## Upgrading from this fork's previous release

Entries using the known map key migrate automatically to Public station mode.
Their station IDs, entity IDs, forecast hours and sensor settings are preserved.
The migration also uses credentials previously edited through the options form.

The source directory now matches the existing `weatherflow_forecast_alt` domain.
If you installed the fork manually under a different directory, place the updated
files under `custom_components/weatherflow_forecast_alt` before restarting.
Keep a copy of your previous integration files for rollback. Version 2 entries
are not compatible with the old code; rollback after migration requires restoring
the previous config entry from a Home Assistant backup as well as the old files.

## Settings

| Setting | Purpose |
| --- | --- |
| Station ID | Station number from its Tempest URL. |
| Authentication | Public station or Personal access token. |
| Personal access token | Required only in personal-token mode. |
| Forecast hours | 12–96 hours; default 48. |
| Add sensors | Include station sensors and binary sensors. |

Use the integration's configuration options to change credentials or settings.
Credentials are validated before saving. Advanced options expose public application
and Firebase key overrides if Tempest changes its public configuration.

Anonymous identities are shared across stations. Only refresh tokens are persisted,
using Home Assistant's private storage API; expiring ID tokens stay in memory.
A reload or restart reuses the saved identity. Public authentication failures retry
with backoff and do not ask you to replace a personal token.

## Development and validation

The library lives in [ScottG489/pyweatherflow_forecast_alt](https://github.com/ScottG489/pyweatherflow_forecast_alt).
The manifest pins an immutable library revision.

```sh
python -m pip install homeassistant==2026.11.1 pytest pytest-asyncio ruff
# Install the requirement from custom_components/weatherflow_forecast_alt/manifest.json.
python -m pytest
scripts/lint
python scripts/live_validate.py
```

The tests exercise authentication migration, durable credential storage, setup and
options validation, and coordinator error handling. The explicit live validation
script uses a temporary Home Assistant configuration to check migration, entities,
forecast services, reload and restart. It never loads your installed configuration.

The library also provides an optional 65-minute live authentication soak test.
Public sessions and live requests are created only when those scripts are run.

Based on [briis/weatherflow_forecast](https://github.com/briis/weatherflow_forecast).

## Available Sensors

Here is the list of sensors that the program generates. Calculated means, if No, then data comes directly from the Weather Station, if yes, it is a sensor that is derived from some of the other sensors. Not all sensors show up on all installations. It depends on where in the world your station is located.

### Binary Sensors
All entities are prefixed with `[STATION NAME]_binary_sensors_`

| Sensor Name | Description | Calculated |
| --- | --- | --- |
| Data Available | Will be Off if no sensor data is returned from WeatherFlow. This typically happens if the station has not transmitted data for a while and you should check the status of the Station or the attached device. | Yes |
| Is Freezing | On when the Celcius temperature is below 0 | Yes |
| Is Lightning | On when Lightning strikes are detected | Yes |
| Is Raining | On when the rain rate is above 0mm | Yes |

### Sensors
All entities are prefixed with `[STATION NAME]_sensors_`

| Sensor Name | Description | Calculated |
| --- | --- | --- |
| Absolute Humidity | The amount of water per volume of air | Yes |
| Air Density | The Air density | No |
| Apparent Temperature | The apparent temperature, a mix of Heat Index and Wind Chill | No |
| Barometric Pressure | The Barometric pressure | No |
| Battery | The % of charge on the Battery (Tempest device only) | Yes |
| Beaufort | Beaufort scale is an empirical measure that relates wind speed to observed conditions at sea or on land | Yes |
| Beaufort Description | A descriptive text of the Beaufort value | Yes |
| Cloud Base| The cloud height altitude above sea level | Yes |
| Data Updated | The time of the last data update. Disabled by default.  | No |
| Delta T | Difference between Air Temperature and Wet Bulb Temperature | No |
| Dew Point | Dewpoint in degrees | No |
| Distance last lightning strike | Distance of the last strike | No |
| Freezing Altitude| The altitude above sea level where snow is possible | Yes |
| Heat Index | How warm does it feel? | No |
| Humidity | Relative Humidity in % | No |
| Illuminance | How much the incident light illuminates the surface | No |
| Lightning Strikes | Number of lightning strikes in the last minute | No |
| Lightning Strikes last hour | Number of lightning strikes during the last hour | No |
| Lightning Strikes last 3 hours | Number of lightning strikes the last 3 hours | No |
| Power Save Mode | [Power Save Mode](https://help.weatherflow.com/hc/en-us/articles/360048877194-Solar-Power-Rechargeable-Battery) of a Tempest device | Yes |
| Precipitation Description | Type of precipitation. Possible values are: Dry, Rain, Heavy rain/Hail. State values are: (`no_rain`,`rain`,`heavy_rain`,) The values can be translated in to local language. | No |
| Precipitation duration today | Total rain minutes for the current day. (Reset at midnight) | No |
| Precipitation duration today Checked | Total rain minutes for the current day. (Reset at midnight). Only if Rain Check enabled and in the US | No |
| Precipitation duration yesterday | Total rain minutes yesterday | No |
| Precipitation duration yesterday Checked | Total rain minutes yesterday. Only if Rain Check enabled and in the US | No |
| Precipitation Intensity| A textual representation on the current rain rate | Yes |
| Precipitation last hour | Total rain accumulation for the last hour | No |
| Precipitation Rate | How much is it raining right now | Yes |
| Precipitation today | Total rain for the current day. (Reset at midnight) | No |
| Precipitation today Checked | Total rain for the current day. (Reset at midnight) Only if Rain Check enabled and in the US | No |
| Precipitation Type | Type of precipitation. Possible values are: 0 = none, 1 = rain, 2 = heavy rain/hail | No |
| Precipitation yesterday | Total rain for yesterday (Reset at midnight) | No |
| Precipitation yesterday Checked | Total rain for yesterday (Reset at midnight) Only if Rain Check enabled and in the US | No |
| Pressure Trend | Returns Steady, Falling or Rising determined by the rate of change over the past 3 hours| No |
| Sea Level Pressure | Preasure measurement at Sea Level | No |
| Solar Radiation | Electromagnetic radiation emitted by the sun | No |
| Staton Name | Station Name as state and more information about the station in the Attributes | Yes |
| Station Pressure | Pressure measurement where the station is located | No |
| Temperature | Outside Temperature | No |
| Time of last lightning strike | When the last lightning strike occurred | No |
| UV Description | A descriptive text of the UV Index | Yes |
| UV Index | The UV index | No |
| Voltage | The Voltage of the Tempest device | No |
| Visibility | Distance to the horizon | Yes |
| Wet Bulb Globe Temperature | (WBGT) is a specialised heat stress index which considers several environmental and personal factors. | No |
| Wet Bulb Temperature | Temperature of a parcel of air cooled to saturation (100% relative humidity) | No |
| Wind Cardinal | Current measured Wind bearing as text | Yes |
| Wind Chill | How cold does it feel? | No |
| Wind Direction | Current measured Wind bearing in degrees | No |
| Wind Gust | Highest wind speed for the last minute | No |
| Wind Lull | Lowest wind for the last minute | No |
| Wind Speed | Average wind speed for the last minute | No |

## Enable Debug Logging

If logs are needed for debugging or reporting an issue, use the following configuration.yaml:

```yaml
logger:
  default: error
  logs:
    pyweatherflow-forecast: debug
    custom_components.weatherflow_forecast: debug
```

***

[commits-shield]: https://img.shields.io/github/commit-activity/y/briis/weatherflow_forecast.svg?style=flat-square
[commits]: https://github.com/briis/weatherflow_forecast/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=flat-square
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=flat-square
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/briis/weatherflow_forecast.svg?style=flat-square
[maintenance-shield]: https://img.shields.io/badge/maintainer-Bjarne%20Riis%20%40briis-blue.svg?style=flat-square
[releases-shield]: https://img.shields.io/github/release/briis/weatherflow_forecast.svg?style=flat-square
[releases]: https://github.com/briis/weatherflow_forecast/releases
