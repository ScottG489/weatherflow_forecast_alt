"""Configure WeatherFlow public stations and personal-token access."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from pyweatherflow_forecast import (
    AUTH_PERSONAL_TOKEN, AUTH_PUBLIC_MAP, PUBLIC_FIREBASE_API_KEY, PUBLIC_MAP_API_KEY,
    WeatherFlowForecastBadRequest, WeatherFlowForecastInternalServerError,
    WeatherFlowForecastUnauthorized, WeatherFlowForecastWongStationId,
)

from .auth import async_create_weather, normalize_auth
from .const import (
    CONF_ADD_SENSORS, CONF_API_TOKEN, CONF_AUTH_MODE, CONF_DEVICE_ID,
    CONF_FIRMWARE_REVISION, CONF_FIREBASE_API_KEY, CONF_FORECAST_HOURS,
    CONF_MAP_API_KEY, CONF_SERIAL_NUMBER, CONF_STATION_ID,
    DEFAULT_ADD_SENSOR, DEFAULT_FORECAST_HOURS, DOMAIN,
)

AUTH_FIELDS = (CONF_AUTH_MODE, CONF_API_TOKEN, CONF_MAP_API_KEY, CONF_FIREBASE_API_KEY)


def _schema(data, options, *, station=False):
    """Describe authentication and forecast settings."""
    fields = {}
    if station:
        fields[vol.Required(CONF_STATION_ID, default=data.get(CONF_STATION_ID, ""))] = str
    fields[vol.Required(CONF_AUTH_MODE, default=data.get(CONF_AUTH_MODE, AUTH_PUBLIC_MAP))] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=[
            {"value": AUTH_PUBLIC_MAP, "label": "Public station"},
            {"value": AUTH_PERSONAL_TOKEN, "label": "Personal access token"},
        ])
    )
    fields[vol.Optional(CONF_API_TOKEN, default=data.get(CONF_API_TOKEN, ""))] = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )
    fields[vol.Optional(CONF_FORECAST_HOURS, default=options.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS))] = vol.All(
        vol.Coerce(int), vol.Range(min=12, max=96)
    )
    fields[vol.Optional(CONF_ADD_SENSORS, default=options.get(CONF_ADD_SENSORS, DEFAULT_ADD_SENSOR))] = bool
    fields[vol.Optional("public_application")] = section(
        vol.Schema({
            vol.Optional(CONF_MAP_API_KEY, default=data.get(CONF_MAP_API_KEY, PUBLIC_MAP_API_KEY)): str,
            vol.Optional(CONF_FIREBASE_API_KEY, default=data.get(CONF_FIREBASE_API_KEY, PUBLIC_FIREBASE_API_KEY)): str,
        }),
        {"collapsed": True},
    )
    return vol.Schema(fields)


def _auth_data(user_input, previous=None):
    """Keep credentials in entry data, removing unused personal tokens."""
    result = dict(previous or {})
    user_input = {**user_input, **user_input.get("public_application", {})}
    for key in AUTH_FIELDS:
        if key in user_input:
            result[key] = user_input[key].strip() if isinstance(user_input[key], str) else user_input[key]
    if result[CONF_AUTH_MODE] == AUTH_PUBLIC_MAP:
        result.pop(CONF_API_TOKEN, None)
    return result


async def _validate(hass, data, options):
    """Validate credentials and the selected station with the runtime client."""
    if data[CONF_AUTH_MODE] == AUTH_PERSONAL_TOKEN and not data.get(CONF_API_TOKEN):
        return None, {CONF_API_TOKEN: "token_required"}
    try:
        client = await async_create_weather(hass, data, forecast_hours=options.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS))
        station = await client.async_get_station()
        if options.get(CONF_ADD_SENSORS, DEFAULT_ADD_SENSOR):
            if not (await client.async_fetch_sensor_data()).data_available:
                return None, {"base": "offline_error"}
        return station, {}
    except WeatherFlowForecastWongStationId:
        return None, {"base": "wrong_station_id"}
    except WeatherFlowForecastBadRequest:
        return None, {"base": "bad_request"}
    except WeatherFlowForecastInternalServerError:
        return None, {"base": "server_error"}
    except WeatherFlowForecastUnauthorized:
        return None, {"base": "public_auth_error" if data[CONF_AUTH_MODE] == AUTH_PUBLIC_MAP else "wrong_token"}


class WeatherFlowForecastHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a station while preserving its station-based unique ID."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the configuration editor."""
        return WeatherFlowForecastOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle initial setup."""
        errors = {}
        if user_input is not None:
            data = _auth_data(user_input)
            data[CONF_STATION_ID] = user_input[CONF_STATION_ID].strip()
            await self.async_set_unique_id(data[CONF_STATION_ID])
            self._abort_if_unique_id_configured()
            station, errors = await _validate(self.hass, data, user_input)
            if not errors:
                data.update({
                    CONF_NAME: station.station_name,
                    CONF_DEVICE_ID: station.device_id,
                    CONF_FIRMWARE_REVISION: station.firmware_revision,
                    CONF_SERIAL_NUMBER: station.serial_number,
                })
                return self.async_create_entry(
                    title=station.station_name, data=data,
                    options={
                        CONF_FORECAST_HOURS: user_input.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS),
                        CONF_ADD_SENSORS: user_input.get(CONF_ADD_SENSORS, DEFAULT_ADD_SENSOR),
                    },
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}, user_input or {}, station=True),
            errors=errors,
        )


    async def async_step_reauth(self, entry_data):
        """Start replacing a rejected personal access token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate replacement credentials before reloading the entry."""
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = _auth_data({CONF_AUTH_MODE: AUTH_PERSONAL_TOKEN, **user_input}, entry.data)
            _, errors = await _validate(self.hass, data, entry.options)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_API_TOKEN): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )


class WeatherFlowForecastOptionsFlowHandler(config_entries.OptionsFlow):
    """Validate and save authentication changes together with polling options."""

    def __init__(self, config_entry):
        """Remember the entry without replacing HA's config_entry property."""
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit settings and atomically save credentials and options."""
        data = normalize_auth(self._entry.data, self._entry.options)
        errors = {}
        if user_input is not None:
            data = _auth_data(user_input, data)
            _, errors = await _validate(self.hass, data, user_input)
            if not errors:
                options = {
                    CONF_FORECAST_HOURS: user_input.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS),
                    CONF_ADD_SENSORS: user_input.get(CONF_ADD_SENSORS, DEFAULT_ADD_SENSOR),
                }
                self.hass.config_entries.async_update_entry(self._entry, data=data, options=options)
                return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="init", data_schema=_schema(data, user_input or self._entry.options),
            errors=errors,
        )
