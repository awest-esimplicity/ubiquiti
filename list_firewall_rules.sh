#!/usr/bin/env bash
set -euo pipefail

export UBIQUITI_ENV_FILE="$(pwd)/.env"

uv run python - <<'PY'
from ubiquiti import FirewallManager, UniFiClient, settings, suppress_insecure_request_warning

suppress_insecure_request_warning(settings.verify_ssl)

client = UniFiClient(
    settings.unifi_base_url,
    api_key=settings.unifi_api_key,
    verify_ssl=settings.verify_ssl,
)
manager = FirewallManager(client)
response = client.request("get", manager._base_endpoint())
for rule in response.json().get("data", []):
    print(rule)
PY
