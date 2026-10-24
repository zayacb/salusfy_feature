"""Support for Salus iT500 climate devices.

Presets auto/manual are virtual (stored in HA). The Salus device itself is
always kept in its MANUAL mode when heating:
  - preset "auto"   -> HA automation controls the setpoint
  - preset "manual" -> the user controls the setpoint from HA
"""
import asyncio
import logging

from aiohttp import ClientResponseError

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SalusDataCoordinator
from .const import DOMAIN
from .pyit500.heatingzone import ConsolidatedMode, HeatingZone
from .pyit500.zone import OnOffStatus, Prefix
from .pyit500.device import SystemType, TemperatureUnit

_LOGGER = logging.getLogger(__name__)

# Virtual presets (both are Salus MANUAL on the device)
PRESET_AUTO = "auto"
PRESET_MANUAL = "manual"

PRESET_MODES = [PRESET_AUTO, PRESET_MANUAL]

# HA HVAC modes -> Salus modes. Heating is always Salus MANUAL.
HVAC_MODE_TO_SALUS = {
    HVACMode.OFF: ConsolidatedMode.OFF,
    HVACMode.HEAT: ConsolidatedMode.MANUAL,
}

SALUS_MODE_TO_HVAC = {
    ConsolidatedMode.OFF: HVACMode.OFF,
    ConsolidatedMode.AUTO: HVACMode.HEAT,
    ConsolidatedMode.MANUAL: HVACMode.HEAT,
    ConsolidatedMode.TEMP_HOLD: HVACMode.HEAT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus climate entities from a config entry."""
    coordinator: SalusDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Always add CH1 (primary heating zone)
    entities.append(SalusThermostat(coordinator, Prefix.CH1, "Heating Zone 1"))

    # Add CH2 if system supports it
    if coordinator.device.system_type == SystemType.CH1_CH2:
        entities.append(SalusThermostat(coordinator, Prefix.CH2, "Heating Zone 2"))

    async_add_entities(entities)


class SalusThermostat(CoordinatorEntity[SalusDataCoordinator], ClimateEntity, RestoreEntity):
    """Representation of a Salus thermostat."""

    _attr_has_entity_name = False  # We set full name including device name
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = PRESET_MODES

    def __init__(
        self,
        coordinator: SalusDataCoordinator,
        zone_prefix: Prefix,
        name: str,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._zone_prefix = zone_prefix

        # Virtual preset (restored after restart)
        self._virtual_preset = PRESET_AUTO

        # Optimistic state for immediate UI updates
        self._optimistic_target_temp = None
        self._optimistic_hvac_mode = None

        # Set temperature unit based on device configuration
        if coordinator.device.temperature_unit == TemperatureUnit.FAHRENHEIT:
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        # Use device name as prefix for entity name
        device_name = coordinator.device.description or "Salus iT500"
        self._attr_name = f"{device_name} {name}"
        self._attr_unique_id = (
            f"{coordinator.device.device_id}_{zone_prefix.value}_climate"
        )

    async def async_added_to_hass(self) -> None:
        """Restore the virtual preset."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            restored = last_state.attributes.get("preset_mode")
            if restored in PRESET_MODES:
                self._virtual_preset = restored

    @property
    def _zone(self) -> HeatingZone:
        """Return the heating zone for this thermostat."""
        if self._zone_prefix == Prefix.CH1:
            return self.coordinator.device.ch1
        return self.coordinator.device.ch2

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._zone.current_room_temp

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if self._optimistic_target_temp is not None:
            return self._optimistic_target_temp
        return self._zone.current_setpoint

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation mode."""
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        mode = self._zone.consolidated_mode
        return SALUS_MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        if self._zone.relay_status == OnOffStatus.ON:
            return HVACAction.HEATING
        if self._zone.consolidated_mode == ConsolidatedMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the virtual preset.

        Device OFF -> None. Device MANUAL -> stored virtual preset.
        Device AUTO/TEMP_HOLD (changed from the Salus app or thermostat)
        -> "auto", so the automation takes over and puts it back to MANUAL.
        """
        mode = self._zone.consolidated_mode
        if mode == ConsolidatedMode.OFF:
            return None
        if mode == ConsolidatedMode.MANUAL:
            return self._virtual_preset
        return PRESET_AUTO

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 41.0  # 5°C in Fahrenheit
        return 5.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 95.0  # 35°C = 95°F
        return 35.0

    async def _run_with_retry(self, description: str, func) -> None:
        """Run an API call with retry on transient server errors, then refresh."""
        max_retries = 3
        retry_delays = [1, 2, 4]  # Exponential backoff

        for attempt in range(max_retries):
            try:
                await func()
                await self.coordinator.async_request_refresh()
                return
            except ClientResponseError as err:
                if err.status in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = retry_delays[attempt]
                    _LOGGER.warning(
                        "API error %s (attempt %d/%d), retrying in %ds: %s",
                        description,
                        attempt + 1,
                        max_retries,
                        delay,
                        err,
                    )
                    await asyncio.sleep(delay)
                    continue
                _LOGGER.error(
                    "Failed %s: API returned %s - %s",
                    description,
                    err.status,
                    err.message,
                )
                raise HomeAssistantError(
                    f"Failed {description}: API error {err.status}"
                ) from err

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._optimistic_target_temp = temperature
        self.async_write_ha_state()

        try:
            await self._run_with_retry(
                f"setting temperature to {temperature}",
                lambda: self._zone.async_set_current_setpoint(temperature),
            )
        finally:
            self._optimistic_target_temp = None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode (heat = Salus MANUAL)."""
        if hvac_mode not in HVAC_MODE_TO_SALUS:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            return

        self._optimistic_hvac_mode = hvac_mode
        self.async_write_ha_state()

        salus_mode = HVAC_MODE_TO_SALUS[hvac_mode]
        try:
            await self._run_with_retry(
                f"setting HVAC mode to {hvac_mode}",
                lambda: self._zone.async_set_consolidated_mode(salus_mode),
            )
        finally:
            self._optimistic_hvac_mode = None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set virtual preset. The device is kept in MANUAL in both cases."""
        if preset_mode not in PRESET_MODES:
            _LOGGER.error("Unsupported preset mode: %s", preset_mode)
            return

        self._virtual_preset = preset_mode
        self.async_write_ha_state()

        # Device was switched to AUTO/TEMP_HOLD elsewhere: bring it back to MANUAL.
        # Never turn on a zone that is OFF just because the preset changed.
        mode = self._zone.consolidated_mode
        if mode not in (ConsolidatedMode.OFF, ConsolidatedMode.MANUAL):
            await self._run_with_retry(
                f"setting preset to {preset_mode}",
                lambda: self._zone.async_set_consolidated_mode(ConsolidatedMode.MANUAL),
            )

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "frost_active": self._zone.frost_active.friendly_name,
            "schedule_type": self._zone.schedule_type.friendly_name,
            "salus_mode": self._zone.consolidated_mode.name.lower(),
        }
