"""The Salus iT500 integration (heating only)."""
import logging
from asyncio import sleep
from aiohttp import ClientError, ClientResponseError, ServerDisconnectedError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL, MIN_TIME_BETWEEN_UPDATES
from .pyit500.auth import Auth, AuthenticationError
from .pyit500.device import Device
from .pyit500.pyit500 import PyIt500

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]


class QuietLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that suppresses debug messages."""

    def debug(self, msg, *args, **kwargs):
        """Suppress debug messages."""
        pass  # Don't forward debug messages


class SalusDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for Salus devices."""

    def __init__(self, hass: HomeAssistant, api: PyIt500, device: Device) -> None:
        """Initialize the coordinator."""
        # Use QuietLoggerAdapter to suppress debug messages
        quiet_logger = QuietLoggerAdapter(_LOGGER, {})
        super().__init__(
            hass,
            quiet_logger,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            # Add rate limiting to prevent overwhelming the API
            request_refresh_debouncer=Debouncer(
                hass,
                quiet_logger,
                cooldown=MIN_TIME_BETWEEN_UPDATES.total_seconds(),
                immediate=False,
            ),
        )
        self.api = api
        self.device = device

    async def _async_update_data(self):
        """Fetch data from API."""
        max_retries = 2
        retry_delay = 2

        for attempt in range(max_retries + 1):
            try:
                await self.device.async_update()
                return self.device
            except AuthenticationError as err:
                # Credentials are no longer accepted: ask the user to re-authenticate
                raise ConfigEntryAuthFailed(
                    "Salus credentials were rejected"
                ) from err
            except (ServerDisconnectedError, ClientResponseError) as err:
                # Handle connection and auth errors with retry
                if attempt < max_retries:
                    error_type = "Auth" if isinstance(err, ClientResponseError) and err.status in (401, 403) else "Connection"
                    _LOGGER.warning(
                        "%s error (attempt %d/%d), retrying in %d seconds... Error: %s",
                        error_type,
                        attempt + 1,
                        max_retries + 1,
                        retry_delay,
                        err,
                    )
                    await sleep(retry_delay)
                    # Try to refresh auth token on retry (auth.request already does this, but as fallback)
                    try:
                        await self.device.auth.refresh_token()
                    except AuthenticationError as refresh_err:
                        raise ConfigEntryAuthFailed(
                            "Salus credentials were rejected"
                        ) from refresh_err
                    except Exception as refresh_err:
                        _LOGGER.debug("Token refresh failed: %s", refresh_err)
                    continue
                else:
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Error communicating with API: {err}") from err


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Salus component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Salus from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = async_get_clientsession(hass)
    auth = Auth(session, username, password)
    api = PyIt500(auth)

    try:
        await auth.refresh_token()
        device_list = await api.async_get_device_list()

        if not device_list:
            _LOGGER.error("No devices found for this account")
            return False

        # Use the first device (most users have only one thermostat)
        device = await api.async_get_device(device_list[0].device_id)
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed("Salus credentials were rejected") from err
    except (ClientError, TimeoutError) as err:
        # Cloud unreachable or erroring: Home Assistant retries setup automatically
        raise ConfigEntryNotReady(f"Cannot reach Salus API: {err}") from err

    # Create coordinator
    coordinator = SalusDataCoordinator(hass, api, device)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
