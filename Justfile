set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default recipe lists available commands.
default:
    just --list

# Run the unit test suite via uv/pytest.
test:
    uv run pytest

# Lock all devices belonging to the provided owner.
lock owner:
    uv run ubiquiti --owner {{owner}}

# Unlock all devices belonging to the provided owner.
unlock owner:
    uv run ubiquiti --owner {{owner}} --unlock

# List UniFi devices managed by the controller.
list-devices:
    uv run ubiquiti --list-devices

# List currently active client devices.
list-active:
    uv run ubiquiti --list-active

# List active clients that are not registered in devices.py.
list-non-registered-active:
    uv run ubiquiti --list-non-registered-active

# Launch the Streamlit UI on the chosen port (defaults to 8501).
ui port="8501":
    uv run streamlit run streamlit_app.py --server.port {{port}}

# Launch the Streamlit UI with live reload on save.
ui-dev port="8501":
    uv run streamlit run streamlit_app.py --server.port {{port}} --server.runOnSave true

# Refresh the MAC vendor cache used for lookup.
update-vendors:
    uv run python -c "from mac_vendor_lookup import MacLookup; MacLookup().update_vendors()"
