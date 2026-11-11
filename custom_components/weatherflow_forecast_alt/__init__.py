"""WeatherFlow Forecast Platform."""
from __future__ import annotations

from datetime import timedelta
import logging
from random import randrange
from types import MappingProxyType
from typing import Any, Self

from pyweatherflow_forecast import (
    AUTH_PERSONAL_TOKEN,
    WeatherFlow,
    WeatherFlowForecastData,
    WeatherFlowForecastDaily,
    WeatherFlowForecastHourly,
    WeatherFlowForecastUnauthorized,
    WeatherFlowForecastInternalServerError,
    WeatherFlowSensorData,
    WeatherFlowStationData,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration

from .auth import async_create_weather, normalize_auth

from .const import (
    DEFAULT_ADD_SENSOR,
    DEFAULT_FORECAST_HOURS,
    DOMAIN,
    CONF_ADD_SENSORS,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_FORECAST_HOURS,
    CONF_STATION_ID,
    STARTUP,
)

PLATFORMS = [Platform.WEATHER, Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)

def _get_platforms(config_entry: ConfigEntry):

    add_sensors = DEFAULT_ADD_SENSOR if config_entry.options.get(
        CONF_ADD_SENSORS) is None else config_entry.options.get(CONF_ADD_SENSORS)

    return add_sensors

def _get_forecast_hours(config_entry: ConfigEntry):

    forecast_hours = DEFAULT_FORECAST_HOURS if config_entry.options.get(
        CONF_FORECAST_HOURS) is None else config_entry.options.get(CONF_FORECAST_HOURS)

    return forecast_hours


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up WeatherFlow Forecast as config entry."""
    hass.data.setdefault(DOMAIN, {})
    integration = await async_get_integration(hass, DOMAIN)
    _LOGGER.info(STARTUP, integration.version, str(config_entry.data[CONF_STATION_ID]))

    add_sensors = _get_platforms(config_entry)
    forecast_hours = _get_forecast_hours(config_entry)

    coordinator = WeatherFlowForecastDataUpdateCoordinator(
        hass, config_entry, add_sensors, forecast_hours)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = coordinator

    config_entry.async_on_unload(config_entry.add_update_listener(async_update_entry))

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    if not add_sensors:
        await cleanup_old_device(hass, str(config_entry.data[CONF_STATION_ID]))

    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)

    return unload_ok

async def async_update_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Reload WeatherFlow Forecast component when options changed."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def cleanup_old_device(hass: HomeAssistant, station_id) -> None:
    """Cleanup device without proper device identifier."""
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(
        identifiers={(DOMAIN, station_id)})  # type: ignore[arg-type]
    if device:
        _LOGGER.debug("Removing deselected sensors: %s", device.name)
        device_reg.async_remove_device(device.id)
    device = device_reg.async_get_device(
        identifiers={(DOMAIN, f"{station_id}_binary")})  # type: ignore[arg-type]
    if device:
        _LOGGER.debug("Removing deselected sensors: %s", device.name)
        device_reg.async_remove_device(device.id)

class WeatherFlowForecastDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching WeatherFlow data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, add_sensors: bool, forecast_hours: int) -> None:
        """Initialize global WeatherFlow forecast data updater."""
        self.weather = WeatherFlowForecastWeatherData(
            hass, config_entry.data, add_sensors, forecast_hours)
        self.add_sensors = add_sensors
        self.forecast_hours = forecast_hours

        if add_sensors:
            update_interval = timedelta(minutes=randrange(1, 5))
        else:
            update_interval = timedelta(minutes=randrange(25, 35))

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval, config_entry=config_entry)

    async def _async_setup(self) -> None:
        """Load shared authentication before the first update."""
        await self.weather.async_initialize_data()

    async def _async_update_data(self) -> WeatherFlowForecastWeatherData:
        """Fetch data and distinguish personal credentials from public outages."""
        try:
            return await self.weather.fetch_data()
        except WeatherFlowForecastUnauthorized as err:
            if self.config_entry.data.get(CONF_AUTH_MODE) == AUTH_PERSONAL_TOKEN:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(f"Public map authentication failed: {err}") from err
        except WeatherFlowForecastInternalServerError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Update failed: {err}") from err


class WeatherFlowForecastWeatherData:
    """Keep data for WeatherFlow Forecast entity data."""

    def __init__(self, hass: HomeAssistant, config: MappingProxyType[str, Any], add_sensors: bool, forecast_hours: int) -> None:
        """Initialise the weather entity data."""
        self.hass = hass
        self._config = config
        self._add_sensors = add_sensors
        self._forecast_hours = forecast_hours
        self._weather_data: WeatherFlow
        self.current_weather_data: WeatherFlowForecastData = {}
        self.daily_forecast: WeatherFlowForecastDaily = []
        self.hourly_forecast: WeatherFlowForecastHourly = []
        self.sensor_data: WeatherFlowSensorData = {}
        self.station_data: WeatherFlowStationData = {}

    async def async_initialize_data(self) -> None:
        """Load shared authentication and construct the API client."""
        self._weather_data = await async_create_weather(
            self.hass, self._config, forecast_hours=self._forecast_hours
        )

    async def fetch_data(self) -> Self:
        """Fetch a complete update before replacing the last successful data."""
        forecast = await self._weather_data.async_get_forecast()
        if self._add_sensors:
            sensors = await self._weather_data.async_fetch_sensor_data()
            station = await self._weather_data.async_get_station()
            self.sensor_data = sensors
            self.station_data = station
            if not sensors.data_available:
                _LOGGER.warning("Weather station has no recent observations")
        self.current_weather_data = forecast
        self.daily_forecast = forecast.forecast_daily
        self.hourly_forecast = forecast.forecast_hourly
        return self


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate credentials without changing entity identities or station settings."""
    if config_entry.version > 2:
        return False
    if config_entry.version == 1:
        data = normalize_auth(config_entry.data, config_entry.options)
        options = {key: value for key, value in config_entry.options.items() if key != CONF_API_TOKEN}
        hass.config_entries.async_update_entry(config_entry, data=data, options=options, version=2)
    return True
