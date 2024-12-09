"""E3DC Switch platform."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class E3DCSwitchEntityDescription(SwitchEntityDescription):
    """Derived helper for advanced configs."""

    on_icon: str | None = None
    off_icon: str | None = None
    async_turn_on_action: (
        Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
    ) = None
    async_turn_off_action: (
        Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
    ) = None


SWITCHES: Final[tuple[E3DCSwitchEntityDescription, ...]] = (
    # CONFIG AND DIAGNOSTIC SWITCHES
    E3DCSwitchEntityDescription(
        key="pset-powersaving-enabled",
        translation_key="pset-powersaving-enabled",
        on_icon="mdi:leaf",
        off_icon="mdi:leaf-off",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        async_turn_on_action=lambda coordinator: coordinator.async_set_powersave(True),
        async_turn_off_action=lambda coordinator: coordinator.async_set_powersave(
            False
        ),
        entity_registry_enabled_default=False,
    ),
    E3DCSwitchEntityDescription(
        key="pset-weatherregulationenabled",
        translation_key="pset-weatherregulationenabled",
        on_icon="mdi:weather-sunny",
        off_icon="mdi:weather-sunny-off",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        async_turn_on_action=lambda coordinator: coordinator.async_set_weather_regulated_charge(
            True
        ),
        async_turn_off_action=lambda coordinator: coordinator.async_set_weather_regulated_charge(
            False
        ),
    ),
    # REGULAR SWITCHES (None yet)
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Switch Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCSwitch] = [
        E3DCSwitch(coordinator, description, entry.unique_id)
        for description in SWITCHES
    ]

    for wallbox in coordinator.wallboxes:
        # Get the UID & Key for the given wallbox
        unique_id = list(wallbox["deviceInfo"]["identifiers"])[0][1]
        wallbox_key = wallbox["key"]

        wallbox_sun_mode_description = E3DCSwitchEntityDescription(
            # TODO: Figure out how the icons match the on/off state
            key=f"{wallbox_key}-sun-mode",
            translation_key="wallbox-sun-mode",
            name="Wallbox Sun Mode",
            on_icon="mdi:weather-sunny",
            off_icon="mdi:weather-sunny-off",
            device_class=SwitchDeviceClass.SWITCH,
            async_turn_on_action=lambda coordinator, index=wallbox[
                "index"
            ]: coordinator.async_set_wallbox_sun_mode(True, index),
            async_turn_off_action=lambda coordinator, index=wallbox[
                "index"
            ]: coordinator.async_set_wallbox_sun_mode(False, index),
        )
        entities.append(
            E3DCSwitch(
                coordinator,
                wallbox_sun_mode_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_schuko_description = E3DCSwitchEntityDescription(
            key=f"{wallbox_key}-schuko",
            translation_key="wallbox-schuko",
            name="Wallbox Schuko",
            on_icon="mdi:power-plug",
            off_icon="mdi:power-plug-off",
            device_class=SwitchDeviceClass.OUTLET,
            async_turn_on_action=lambda coordinator, index=wallbox[
                "index"
            ]: coordinator.async_set_wallbox_schuko(True, index),
            async_turn_off_action=lambda coordinator, index=wallbox[
                "index"
            ]: coordinator.async_set_wallbox_schuko(False, index),
            entity_registry_enabled_default=False,  # Disabled per default as only Wallbox multi connect I provides this feature
        )
        entities.append(
            E3DCSwitch(
                coordinator,
                wallbox_schuko_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

    async_add_entities(entities)


class E3DCSwitch(CoordinatorEntity, SwitchEntity):
    """Custom E3DC Switch Implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSwitchEntityDescription,
        uid: str,
        device_info: DeviceInfo | None = None,
    ) -> None:
        """Initialize the Switch."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCSwitchEntityDescription = description
        self._attr_is_on = self.coordinator.data.get(self.entity_description.key)
        self._attr_unique_id = f"{uid}_{description.key}"
        self._has_custom_icons: bool = (
            self.entity_description.on_icon is not None
            and self.entity_description.off_icon is not None
        )
        if device_info is not None:
            self._deviceInfo = device_info
        else:
            self._deviceInfo = self.coordinator.device_info()

    @property
    def icon(self) -> str | None:
        """Return dynamic icon reference."""
        if self._has_custom_icons:
            return (
                self.entity_description.on_icon
                if (self.is_on)
                else self.entity_description.off_icon
            )

        return self._attr_icon

    @callback
    def _handle_coordinator_update(self) -> None:
        """Process coordinator updates."""
        self._attr_is_on = self.coordinator.data.get(self.entity_description.key)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn off the switch asynchronnously."""
        if self.entity_description.async_turn_on_action is not None:
            self._attr_is_on = True
            self.async_write_ha_state()
            await self.entity_description.async_turn_on_action(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn on the switch asynchronnously."""
        if self.entity_description.async_turn_off_action is not None:
            self._attr_is_on = False
            self.async_write_ha_state()
            await self.entity_description.async_turn_off_action(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo
