# Ubiquiti Toolkit

Command-line helpers and a Streamlit dashboard for managing UniFi devices, firewall locks, and MAC vendor lookups.

## Prerequisites

- [uv](https://docs.astral.sh/uv/latest/). The included `pyproject.toml` targets Python 3.13.
- [just](https://github.com/casey/just#installation) for running the project recipes.

Install `just` however you prefer, for example:

```bash
brew install just
```

## Configuration

Populate these environment variables (or add them to a local `.env` file):

- `UNIFI_API_KEY` – required UniFi controller API key.
- `UNIFI_BASE_URL` – controller base URL (defaults to `https://10.0.0.1/proxy/network`).
- `UNIFI_VERIFY_SSL` – set to `1` to enforce SSL verification; omit or `0` to skip.

## Project Commands

The `Justfile` captures the common workflows. Run `just` to see the list or invoke a recipe directly:

| Command | Description |
| --- | --- |
| `just test` | Run the full pytest suite under `uv`. |
| `just lock <owner>` | Lock all devices owned by `<owner>` using the CLI helper. |
| `just unlock <owner>` | Remove lock rules for the owner’s devices. |
| `just list-devices` | Dump all UniFi network devices as JSON. |
| `just list-active` | Show active client devices with their last-seen timestamp. |
| `just list-non-registered-active` | Filter active clients that are not defined in `devices.py`. |
| `just ui [port]` | Start the Streamlit UI (`port` defaults to `8501`). |
| `just ui-dev [port]` | Start the Streamlit UI with live reload on save. |
| `just update-vendors` | Refresh the cached IEEE OUI vendor database. |

Examples:

```bash
just lock kade
just ui 8080
```

The recipes delegate to `uv run`, so dependencies are installed on demand using the project’s lockfile.
