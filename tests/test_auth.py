"""Authentication migration, setup, storage and coordinator behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyweatherflow_forecast import (
    AUTH_PERSONAL_TOKEN, AUTH_PUBLIC_MAP, PUBLIC_MAP_API_KEY,
    WeatherFlowForecastUnauthorized,
)

from custom_components.weatherflow_forecast_alt import (
    WeatherFlowForecastDataUpdateCoordinator, async_migrate_entry,
)
from custom_components.weatherflow_forecast_alt.auth import (
    PublicAuthStore, async_create_weather, normalize_auth,
)
from custom_components.weatherflow_forecast_alt.config_flow import (
    WeatherFlowForecastHandler, WeatherFlowForecastOptionsFlowHandler, _auth_data, _schema, _validate,
)
from custom_components.weatherflow_forecast_alt.const import (
    CONF_ADD_SENSORS, CONF_API_TOKEN, CONF_AUTH_MODE, CONF_FORECAST_HOURS,
    CONF_STATION_ID, DOMAIN,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def hass(tmp_path):
    """Use a real HA storage backend in a temporary configuration directory."""
    instance = HomeAssistant(str(tmp_path))
    yield instance
    await instance.async_stop(force=True)


def entry(**kwargs):
    data = {CONF_STATION_ID: "95467", CONF_API_TOKEN: PUBLIC_MAP_API_KEY, "name": "Oxford St"}
    return SimpleNamespace(data=data, options={CONF_FORECAST_HOURS: 96, CONF_ADD_SENSORS: True},
                           version=1, unique_id="95467", entry_id="unchanged", **kwargs)


async def test_migration_preserves_identity_and_forecast_settings():
    original = entry()
    update = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    assert await async_migrate_entry(hass, original)
    args = update.call_args
    assert args.args == (original,)
    assert args.kwargs["version"] == 2
    assert args.kwargs["data"] == {
        CONF_STATION_ID: "95467", CONF_AUTH_MODE: AUTH_PUBLIC_MAP, "name": "Oxford St",
    }
    assert args.kwargs["options"] == original.options
    assert original.entry_id == "unchanged" and original.unique_id == "95467"


async def test_migration_prefers_edited_options_credentials():
    original = entry()
    original.options[CONF_API_TOKEN] = "new-personal-token"
    update = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    assert await async_migrate_entry(hass, original)
    data = update.call_args.kwargs["data"]
    assert data[CONF_API_TOKEN] == "new-personal-token"
    assert data[CONF_AUTH_MODE] == AUTH_PERSONAL_TOKEN
    assert CONF_API_TOKEN not in update.call_args.kwargs["options"]


async def test_future_config_version_is_not_downgraded():
    original = entry()
    original.version = 3
    assert not await async_migrate_entry(None, original)


async def test_normalization_removes_unused_credentials():
    data = normalize_auth({CONF_AUTH_MODE: AUTH_PUBLIC_MAP, CONF_API_TOKEN: "unused"}, {})
    assert CONF_API_TOKEN not in data


async def test_storage_survives_new_manager_and_is_shared(hass, monkeypatch):
    request = AsyncMock(return_value={"idToken": "identity", "refreshToken": "saved-refresh", "expiresIn": "3600"})
    monkeypatch.setattr("pyweatherflow_forecast.auth.request_json", request)
    store = PublicAuthStore(hass)
    managers = await asyncio.gather(*(store.async_get("firebase-key") for _ in range(5)))
    assert all(manager is managers[0] for manager in managers)
    await managers[0].async_get_token(object())
    assert request.call_count == 1
    restored = await PublicAuthStore(hass).async_get("firebase-key")
    assert restored is not managers[0]
    assert restored.refresh_token == "saved-refresh"
    assert restored._id_token is None


async def test_runtime_clients_share_identity_but_keep_independent_api(hass, monkeypatch):
    session = object()
    monkeypatch.setattr("custom_components.weatherflow_forecast_alt.auth.async_get_clientsession", lambda _: session)
    data = {CONF_STATION_ID: "95467", CONF_AUTH_MODE: AUTH_PUBLIC_MAP}
    first, second = await asyncio.gather(
        async_create_weather(hass, data), async_create_weather(hass, data),
    )
    assert first._api is not second._api
    assert first._api.auth is second._api.auth
    assert first._api.session is second._api.session


async def test_public_setup_requires_no_personal_token():
    schema = _schema({}, {}, station=True)
    values = schema({CONF_STATION_ID: "95467", CONF_AUTH_MODE: AUTH_PUBLIC_MAP})
    assert not values.get(CONF_API_TOKEN)
    assert values[CONF_FORECAST_HOURS] == 48


async def test_personal_setup_requires_a_token():
    _, errors = await _validate(None, {CONF_AUTH_MODE: AUTH_PERSONAL_TOKEN}, {})
    assert errors == {CONF_API_TOKEN: "token_required"}


async def test_public_authentication_errors_are_not_wrong_personal_token(monkeypatch):
    client = SimpleNamespace(async_get_station=AsyncMock(side_effect=WeatherFlowForecastUnauthorized("rejected")))
    monkeypatch.setattr(
        "custom_components.weatherflow_forecast_alt.config_flow.async_create_weather",
        AsyncMock(return_value=client),
    )
    _, errors = await _validate(None, {CONF_AUTH_MODE: AUTH_PUBLIC_MAP}, {})
    assert errors == {"base": "public_auth_error"}


async def test_options_edits_update_runtime_credentials_atomically(monkeypatch):
    original = entry()
    original.data = {CONF_STATION_ID: "95467", CONF_AUTH_MODE: AUTH_PERSONAL_TOKEN, CONF_API_TOKEN: "old"}
    original.version = 2
    validate = AsyncMock(return_value=(object(), {}))
    monkeypatch.setattr("custom_components.weatherflow_forecast_alt.config_flow._validate", validate)
    update = Mock()
    flow = WeatherFlowForecastOptionsFlowHandler(original)
    flow.hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
    flow.flow_id = "test"
    flow.handler = original.entry_id
    result = await flow.async_step_init({
        CONF_AUTH_MODE: AUTH_PERSONAL_TOKEN, CONF_API_TOKEN: "replacement",
        CONF_FORECAST_HOURS: 72, CONF_ADD_SENSORS: True,
    })
    assert result["type"] == "create_entry"
    assert update.call_count == 1
    assert update.call_args.kwargs["data"][CONF_API_TOKEN] == "replacement"
    assert update.call_args.kwargs["options"][CONF_FORECAST_HOURS] == 72
    assert CONF_API_TOKEN not in result["data"]


@pytest.mark.parametrize("mode,error", [
    (AUTH_PUBLIC_MAP, UpdateFailed),
    (AUTH_PERSONAL_TOKEN, ConfigEntryAuthFailed),
])
async def test_coordinator_distinguishes_public_outages_from_personal_auth(mode, error):
    coordinator = SimpleNamespace(
        weather=SimpleNamespace(fetch_data=AsyncMock(side_effect=WeatherFlowForecastUnauthorized("rejected"))),
        config_entry=SimpleNamespace(data={CONF_AUTH_MODE: mode}),
    )
    with pytest.raises(error):
        await WeatherFlowForecastDataUpdateCoordinator._async_update_data(coordinator)


async def test_existing_public_entry_keeps_domain():
    assert DOMAIN == "weatherflow_forecast_alt"


async def test_application_overrides_are_flattened_for_runtime():
    result = _auth_data({
        CONF_AUTH_MODE: AUTH_PUBLIC_MAP,
        "public_application": {"map_api_key": "override-map", "firebase_api_key": "override-firebase"},
    })
    assert result["map_api_key"] == "override-map"
    assert result["firebase_api_key"] == "override-firebase"
    assert "public_application" not in result


async def test_reauthentication_validates_replacement_before_reload(monkeypatch):
    original = entry()
    original.data = {CONF_STATION_ID: "95467", CONF_AUTH_MODE: AUTH_PERSONAL_TOKEN, CONF_API_TOKEN: "old"}
    validate = AsyncMock(return_value=(object(), {}))
    monkeypatch.setattr("custom_components.weatherflow_forecast_alt.config_flow._validate", validate)
    flow = WeatherFlowForecastHandler()
    flow.hass = object()
    flow._get_reauth_entry = Mock(return_value=original)
    flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
    assert await flow.async_step_reauth_confirm({CONF_API_TOKEN: "replacement"}) == {"type": "abort"}
    assert validate.call_args.args[1][CONF_API_TOKEN] == "replacement"
    assert flow.async_update_reload_and_abort.call_args.kwargs["data_updates"][CONF_API_TOKEN] == "replacement"
