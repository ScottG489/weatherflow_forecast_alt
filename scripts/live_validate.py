# ruff: noqa: T201
"""Validate migration, entities, forecasts, reload and restart in a temporary HA instance."""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant import bootstrap, loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pyweatherflow_forecast import AUTH_PUBLIC_MAP, PUBLIC_MAP_API_KEY

from custom_components.weatherflow_forecast_alt.auth import async_create_weather
from custom_components.weatherflow_forecast_alt.const import DOMAIN


async def create_hass(directory):
    """Load HA's real integration and storage infrastructure."""
    hass = HomeAssistant(directory)
    hass.config.skip_pip = True
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    assert await bootstrap.async_load_base_functionality(hass)
    assert await async_setup_component(hass, "network", {})
    return hass


async def check_weather(hass, expected_hours=96):
    """Exercise the weather forecast service and live sensor states."""
    await hass.async_block_till_done()
    states = hass.states.async_all()
    weather = [state for state in states if state.entity_id.startswith("weather.")]
    sensors = [state for state in states if state.entity_id.startswith("sensor.")]
    assert weather and weather[0].state not in {"unavailable", "unknown", "exceptional"}
    assert weather[0].attributes.get("temperature") is not None
    assert any(state.state not in {"unavailable", "unknown"} for state in sensors)
    for forecast_type in ("daily", "hourly"):
        response = await hass.services.async_call(
            "weather", "get_forecasts",
            {"entity_id": weather[0].entity_id, "type": forecast_type},
            blocking=True, return_response=True,
        )
        count = len(response[weather[0].entity_id]["forecast"])
        assert count == (10 if forecast_type == "daily" else expected_hours)
        print("PASS HA forecast service", forecast_type, count, flush=True)
    print("PASS HA weather", weather[0].state, "sensor entities", len(sensors), flush=True)
    return {state.entity_id for state in states if state.entity_id.startswith(("weather.", "sensor.", "binary_sensor."))}


async def main():
    """Validate using temporary configuration, never the installed HA instance."""
    logging.basicConfig(level=logging.WARNING)
    with tempfile.TemporaryDirectory(prefix="weatherflow-ha-") as directory:
        Path(directory, "custom_components").symlink_to(Path(__file__).resolve().parents[1] / "custom_components")
        hass = await create_hass(directory)
        try:
            station = await (await async_create_weather(hass, {"station_id": "95467", "auth_mode": AUTH_PUBLIC_MAP})).async_get_station()
            entry = ConfigEntry(
                domain=DOMAIN, title=station.station_name, source="user", unique_id="95467",
                version=1, minor_version=1, discovery_keys=MappingProxyType({}), subentries_data=[],
                data={
                    "station_id": "95467", "name": station.station_name, "api_token": PUBLIC_MAP_API_KEY,
                    "device_id": station.device_id, "firmware_revision": station.firmware_revision,
                    "serial_number": station.serial_number,
                },
                options={"add_sensors": True, "forecast_hours": 96},
            )
            await hass.config_entries.async_add(entry)
            assert entry.version == 2 and entry.data["auth_mode"] == AUTH_PUBLIC_MAP
            assert "api_token" not in entry.data
            print("PASS real config-entry migration", flush=True)
            before = await check_weather(hass)
            original_auth = hass.data[DOMAIN]["_public_auth"]
            flow = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                flow["flow_id"], {"auth_mode": AUTH_PUBLIC_MAP, "forecast_hours": 72, "add_sensors": True},
            )
            assert result["type"] == "create_entry"
            await hass.async_block_till_done()
            assert hass.data[DOMAIN]["_public_auth"] is original_auth
            assert await check_weather(hass, 72) == before
            print("PASS options validation, reload, shared identity, and entity-ID preservation", flush=True)
        finally:
            await hass.async_stop(force=True)
        hass = await create_hass(directory)
        try:
            entries = hass.config_entries.async_entries(DOMAIN)
            assert len(entries) == 1
            assert await hass.config_entries.async_setup(entries[0].entry_id)
            assert await check_weather(hass, 72) == before
            print("PASS HA restart with persisted credentials and unchanged entity IDs", flush=True)
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    asyncio.run(main())
