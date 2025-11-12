"""General utilities for the ubiquiti package."""

from __future__ import annotations

import os
import sys
import warnings

from loguru import logger
from mac_vendor_lookup import (  # type: ignore[import-untyped]
    MacLookup,
    VendorNotFoundError,
)
from urllib3.exceptions import InsecureRequestWarning

_LOGGER_CONFIGURED = False
_MAC_LOOKUP: MacLookup | None = None


def configure_logging(*, force: bool = False) -> None:
    """Set up the global Loguru logger with application defaults."""
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED and not force:
        return

    log_level = os.getenv("UBIQUITI_LOG_LEVEL", "INFO")
    diagnose = os.getenv("UBIQUITI_LOG_DIAGNOSE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        backtrace=False,
        diagnose=diagnose,
        enqueue=False,
        colorize=True,
    )

    _LOGGER_CONFIGURED = True


def suppress_insecure_request_warning(verify_ssl: bool) -> None:
    """Silence urllib3 insecure request warnings when SSL verification is disabled."""
    if verify_ssl:
        return

    warnings.filterwarnings(
        "ignore",
        category=InsecureRequestWarning,
        message="Unverified HTTPS request is being made to host",
    )


def lookup_mac_vendor(mac: str | None) -> str | None:
    """Return the vendor/manufacturer name for the provided MAC address."""
    if not mac:
        return None

    global _MAC_LOOKUP
    if _MAC_LOOKUP is None:
        lookup = MacLookup()
        loaded = False
        try:
            lookup.load_vendors()
            loaded = True
        except FileNotFoundError:
            try:
                lookup.update_vendors()
                lookup.load_vendors()
                loaded = True
            except Exception as exc:  # pragma: no cover - network/load failure
                logger.warning("Unable to download MAC vendor database: {}", exc)
                return None
        except Exception as exc:  # pragma: no cover - unexpected load failure
            logger.warning("Unable to load MAC vendor database: {}", exc)
            return None

        if loaded:
            logger.bind(cache_path=str(lookup.cache_path)).debug(
                "Loaded MAC vendor database"
            )
        _MAC_LOOKUP = lookup

    try:
        return _MAC_LOOKUP.lookup(mac)
    except (KeyError, VendorNotFoundError):
        return None
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.debug("MAC vendor lookup failed for {}: {}", mac, exc)
        return None


configure_logging()

__all__ = [
    "configure_logging",
    "suppress_insecure_request_warning",
    "lookup_mac_vendor",
    "logger",
]
