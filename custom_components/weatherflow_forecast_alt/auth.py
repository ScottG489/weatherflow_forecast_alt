"""Home Assistant storage and client construction for WeatherFlow."""

import asyncio

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from pyweatherflow_forecast import (
    AnonymousAuth,
    AUTH_PERSONAL_TOKEN,
    AUTH_PUBLIC_MAP,
    PUBLIC_FIREBASE_API_KEY,
    PUBLIC_MAP_API_KEY,
    WeatherFlow,
)

from .const import (
    CONF_API_TOKEN, CONF_AUTH_MODE, CONF_FIREBASE_API_KEY, CONF_MAP_API_KEY,
    CONF_STATION_ID, DOMAIN,
)


class PublicAuthStore:
    """Share identities across stations and persist only their refresh tokens."""

    def __init__(self, hass):
        """Create the storage helper without doing disk I/O."""
        self._store = Store(hass, 1, f"{DOMAIN}.public_auth", private=True)
        self._lock = asyncio.Lock()
        self._loaded = False
        self._saved = {}
        self._managers = {}

    async def async_get(self, firebase_api_key):
        """Load each identity once, even during concurrent setup flows."""
        async with self._lock:
            if not self._loaded:
                self._saved = await self._store.async_load() or {}
                self._loaded = True
            if firebase_api_key not in self._managers:
                async def save(token):
                    async with self._lock:
                        self._saved[firebase_api_key] = token
                        await self._store.async_save(dict(self._saved))

                self._managers[firebase_api_key] = AnonymousAuth(
                    firebase_api_key=firebase_api_key,
                    refresh_token=self._saved.get(firebase_api_key),
                    on_refresh_token=save,
                )
            return self._managers[firebase_api_key]


def normalize_auth(data, options):
    """Migrate old credentials, preferring edits made through the options form."""
    result = dict(data)
    token = options.get(CONF_API_TOKEN, result.get(CONF_API_TOKEN, ""))
    mode = result.get(CONF_AUTH_MODE)
    if mode is None:
        mode = AUTH_PUBLIC_MAP if not token or token == PUBLIC_MAP_API_KEY else AUTH_PERSONAL_TOKEN
    result[CONF_AUTH_MODE] = mode
    if mode == AUTH_PUBLIC_MAP:
        result.pop(CONF_API_TOKEN, None)
    else:
        result[CONF_API_TOKEN] = token
    return result


async def async_create_weather(hass, data, *, forecast_hours=48):
    """Construct a client using HA's shared HTTP session."""
    mode = data.get(CONF_AUTH_MODE, AUTH_PUBLIC_MAP)
    auth = None
    if mode == AUTH_PUBLIC_MAP:
        runtime = hass.data.setdefault(DOMAIN, {})
        if "_public_auth" not in runtime:
            runtime["_public_auth"] = PublicAuthStore(hass)
        auth = await runtime["_public_auth"].async_get(
            data.get(CONF_FIREBASE_API_KEY) or PUBLIC_FIREBASE_API_KEY
        )
    return WeatherFlow(
        str(data[CONF_STATION_ID]),
        (data.get(CONF_MAP_API_KEY) or PUBLIC_MAP_API_KEY) if mode == AUTH_PUBLIC_MAP else data.get(CONF_API_TOKEN),
        auth_mode=mode,
        auth=auth,
        session=async_get_clientsession(hass),
        forecast_hours=forecast_hours,
        elevation=hass.config.elevation,
    )
