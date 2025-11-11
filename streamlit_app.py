"""Streamlit dashboard for managing UniFi device locks."""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from datetime import UTC, datetime
from textwrap import dedent

import streamlit as st

from ubiquiti.config import settings
from ubiquiti.devices import DEVICES, Device, device_by_mac
from ubiquiti.firewall import FirewallManager
from ubiquiti.lock import DeviceLocker
from ubiquiti.network import NetworkDeviceService
from ubiquiti.unifi import UniFiAPIError, UniFiClient
from ubiquiti.utils import (
    configure_logging,
    logger,
    lookup_mac_vendor,
    suppress_insecure_request_warning,
)

configure_logging()

REFRESH_INTERVAL_OPTIONS: dict[str, int] = {
    "10s": 10,
    "1m": 60,
    "5m": 300,
    "10m": 600,
}


def apply_global_styles() -> None:
    """Inject custom CSS to elevate the Streamlit UI."""
    st.markdown(
        dedent(
            """
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            :root {
                --color-bg-primary: #0b1224;
                --color-bg-secondary: #111a36;
                --color-panel: #121c35;
                --color-card: rgba(17, 26, 54, 0.85);
                --color-accent: #38bdf8;
                --color-accent-soft: rgba(56, 189, 248, 0.18);
                --color-text-primary: #f8fafc;
                --color-text-secondary: #cbd5f5;
                --color-border: rgba(148, 163, 184, 0.2);
                --color-success: #22c55e;
                --color-danger: #ef4444;
                --color-muted: rgba(148, 163, 184, 0.6);
                --shadow-card: 0 20px 45px rgba(15, 23, 42, 0.45);
            }

            html, body, [data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"] {
                font-family: 'Inter', sans-serif;
                background: radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.18), transparent 45%),
                            radial-gradient(circle at 80% 0%, rgba(59, 130, 246, 0.18), transparent 45%),
                            var(--color-bg-primary);
                color: var(--color-text-primary);
            }

            main .block-container {
                padding-top: 18px !important;
            }

            .hero {
                background: linear-gradient(135deg, rgba(56, 189, 248, 0.22), rgba(99, 102, 241, 0.18));
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 24px;
                padding: 24px 28px;
                box-shadow: var(--shadow-card);
                position: relative;
                overflow: hidden;
                margin-bottom: 28px;
            }

            .hero::after {
                content: "";
                position: absolute;
                top: -120px;
                right: -160px;
                width: 280px;
                height: 280px;
                background: radial-gradient(circle, rgba(255,255,255,0.22), transparent 65%);
                opacity: 0.8;
            }

            .hero__title {
                font-size: 2rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin-bottom: 10px;
                color: var(--color-text-primary);
            }

            .hero__subtitle {
                color: var(--color-text-secondary);
                font-size: 1rem;
                max-width: 580px;
                margin: 0;
            }

            .hero__meta {
                display: flex;
                gap: 18px;
                margin-top: 18px;
                flex-wrap: wrap;
            }

            .hero__meta-item {
                background: rgba(15, 23, 42, 0.55);
                border: 1px solid rgba(148, 163, 184, 0.22);
                padding: 10px 16px;
                border-radius: 14px;
                font-size: 0.95rem;
            }

            .controls-wrapper {
                position: sticky;
                top: 24px;
                z-index: 10;
                margin: 28px 0 26px;
            }

            .controls-panel {
                background: rgba(15, 23, 42, 0.65);
                border: 1px solid rgba(148, 163, 184, 0.25);
                padding: 18px 22px;
                border-radius: 18px;
                box-shadow: 0 18px 28px rgba(15, 23, 42, 0.35);
            }

            .stat-card {
                background: rgba(17, 24, 39, 0.65);
                border: 1px solid rgba(56, 189, 248, 0.18);
                border-radius: 18px;
                padding: 20px 24px;
                box-shadow: var(--shadow-card);
                backdrop-filter: blur(14px);
            }

            .stat-card__label {
                font-size: 0.85rem;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: var(--color-muted);
                margin-bottom: 6px;
            }

            .stat-card__value {
                font-size: 1.9rem;
                font-weight: 600;
                margin: 0;
                color: var(--color-text-primary);
            }

            .stat-card__description {
                margin: 4px 0 0;
                font-size: 0.9rem;
                color: var(--color-text-secondary);
            }

            .stat-card.stat-card--muted {
                background: rgba(17, 24, 39, 0.45);
                border-color: rgba(56, 189, 248, 0.12);
            }

            .stat-card.stat-card--muted .stat-card__label {
                color: rgba(148, 163, 184, 0.75);
            }

            .stat-card.stat-card--muted .stat-card__value {
                color: #e2e8f0;
            }

            .owner-section {
                background: rgba(15, 23, 42, 0.65);
                border-radius: 18px;
                border: 1px solid rgba(148, 163, 184, 0.22);
                padding: 22px 24px 18px;
                margin-bottom: 26px;
                box-shadow: var(--shadow-card);
                backdrop-filter: blur(12px);
            }

            .owner-section__header {
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                margin-bottom: 18px;
            }

            .owner-section__title {
                font-size: 1.35rem;
                font-weight: 600;
                color: var(--color-text-primary);
            }

            .owner-section__meta {
                font-size: 0.85rem;
                color: var(--color-muted);
            }

            .owner-divider {
                border: none;
                height: 1px;
                background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.28), transparent);
                margin: 0 0 18px;
            }

            .table-heading {
                color: var(--color-muted);
                font-size: 0.75rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 6px;
            }

            @media (max-width: 768px) {
                .table-heading {
                    display: none;
                }
            }

            .device-cell {
                background: rgba(15, 23, 42, 0.45);
                border: 1px solid rgba(148, 163, 184, 0.18);
                padding: 12px 16px;
                border-radius: 12px;
                min-height: 54px;
                display: flex;
                align-items: center;
                color: var(--color-text-primary);
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
            }

            .device-cell--muted {
                color: var(--color-text-secondary);
            }

            .device-chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 999px;
                background: rgba(56, 189, 248, 0.12);
                color: var(--color-accent);
                font-size: 0.82rem;
                font-weight: 500;
            }

            .device-chip--align {
                margin-left: auto;
            }

            .details-list {
                display: grid;
                gap: 4px;
                font-size: 0.85rem;
                color: rgba(148, 163, 184, 0.78);
            }

            .details-list > div {
                display: flex;
                justify-content: space-between;
                gap: 12px;
            }

            .details-list span:first-child {
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 0.7rem;
                color: rgba(148, 163, 184, 0.65);
            }

            details summary {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: 0.72rem;
                color: rgba(148, 163, 184, 0.7);
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }

            details summary p {
                font-size: inherit !important;
                color: inherit !important;
                margin: 0;
            }

            details summary:hover {
                color: rgba(148, 163, 184, 0.9);
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 999px;
                font-size: 0.82rem;
                font-weight: 500;
            }

            .status-badge--locked {
                background: rgba(252, 165, 165, 0.12);
                border: 1px solid rgba(252, 165, 165, 0.28);
                color: rgba(254, 226, 226, 0.9);
            }

            .status-badge--unlocked {
                background: rgba(34, 197, 94, 0.18);
                border: 1px solid rgba(34, 197, 94, 0.35);
                color: #bbf7d0;
            }

            .stButton > button {
                border-radius: 999px;
                padding: 8px 16px !important;
                border: 1px solid rgba(52, 152, 219, 0.55);
                background: #3498DB;
                color: #ffffff;
                font-weight: 500;
                transition: all 0.2s ease;
                white-space: nowrap;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
            }

            .stButton > button:hover {
                border-color: rgba(93, 173, 226, 0.8);
                background: #5DADE2;
                transform: translateY(-1px);
            }

            button[kind="primary"] {
                background: #C0392B !important;
                border-color: rgba(192, 57, 43, 0.75) !important;
                color: #fff4f4 !important;
            }

            button[kind="primary"]:hover {
                background: #E74C3C !important;
                border-color: rgba(231, 76, 60, 0.85) !important;
                color: #ffffff !important;
            }

            button[kind="secondary"] {
                background: #27AE60 !important;
                border-color: rgba(39, 174, 96, 0.75) !important;
                color: #f3fff8 !important;
            }

            button[kind="secondary"]:hover {
                background: #2ECC71 !important;
                border-color: rgba(46, 204, 113, 0.85) !important;
                color: #ffffff !important;
            }


            .ghost-card {
                background: rgba(17, 24, 39, 0.55);
                border: 1px solid rgba(56, 189, 248, 0.18);
                border-radius: 16px;
                padding: 18px 20px;
                box-shadow: var(--shadow-card);
                backdrop-filter: blur(10px);
                height: 100%;
            }

            .ghost-card-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
                gap: 22px;
                margin-top: 18px;
            }

            .ghost-card__title {
                font-size: 1.05rem;
                font-weight: 600;
                margin-bottom: 6px;
                color: var(--color-text-primary);
            }

            .ghost-card__meta {
                display: grid;
                gap: 6px;
                font-size: 0.88rem;
                color: var(--color-text-secondary);
            }

            .ghost-card__meta strong {
                color: var(--color-text-primary);
            }

            .toast-success {
                background: rgba(34, 197, 94, 0.92);
                color: #052e16;
            }

            @media (max-width: 1024px) {
                .hero {
                    padding: 26px 28px;
                }

                .hero__title {
                    font-size: 1.95rem;
                }

                .hero__meta {
                    gap: 12px;
                    margin-top: 22px;
                }
            }

            @media (max-width: 768px) {
                .hero {
                    padding: 22px;
                }

                .hero__title {
                    font-size: 1.7rem;
                }

                .hero__subtitle {
                    font-size: 0.95rem;
                }

                .hero__meta {
                    flex-direction: column;
                    gap: 10px;
                }

                .hero__meta-item {
                    width: 100%;
                    justify-content: space-between;
                }

                .controls-wrapper {
                    position: static;
                    top: auto;
                    margin: 18px 0 20px;
                }

                .controls-panel {
                    padding: 16px;
                }

                .table-heading {
                    text-align: left;
                }

                .owner-section {
                    padding: 18px;
                }

                .owner-section__header {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 4px;
                }

                .table-heading {
                    font-size: 0.68rem;
                }

                .device-cell {
                    padding: 10px 14px;
                    min-height: 48px;
                }

                .stat-card {
                    margin-bottom: 12px;
                }

                .stat-card.stat-card--muted {
                    margin-top: 6px;
                }

                .ghost-card-grid {
                    gap: 16px;
                }

                .ghost-card {
                    padding: 16px;
                }

                div[data-testid="column"] {
                    width: 100% !important;
                    flex: 1 1 100% !important;
                }
            }
            </style>
            """
        ),
        unsafe_allow_html=True,
    )


def _format_timestamp(timestamp: float | int | None) -> str:
    if not timestamp and timestamp != 0:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(float(timestamp), tz=UTC).astimezone()
    except (ValueError, OSError):
        return "unknown"
    return dt.strftime("%d/%m/%Y • %I:%M%p")


def _create_client() -> UniFiClient:
    return UniFiClient(
        settings.unifi_base_url,
        api_key=settings.unifi_api_key,
        verify_ssl=settings.verify_ssl,
    )


@contextlib.contextmanager
def locker_context() -> Iterable[tuple[FirewallManager, DeviceLocker]]:
    client = _create_client()
    firewall = FirewallManager(client)
    locker = DeviceLocker(firewall)
    try:
        yield firewall, locker
    finally:
        client.close()


def load_device_status() -> list[dict[str, object]]:
    with locker_context() as (firewall, locker):
        suppress_insecure_request_warning(firewall.client.verify_ssl)
        rules = firewall.list_rules()
        rows: list[dict[str, object]] = []
        for device in DEVICES:
            locked = locker.is_device_locked(device, rules)
            vendor = lookup_mac_vendor(device.mac)
            rows.append(
                {
                    "name": device.name,
                    "owner": device.owner,
                    "type": device.type,
                    "mac": device.mac,
                    "locked": locked,
                    "vendor": vendor,
                }
            )
    return rows


def lock_devices(devices: list[Device], *, unlock: bool) -> None:
    action = "unlock" if unlock else "lock"
    with locker_context() as (_, locker):
        try:
            if unlock:
                locker.unlock_devices(devices)
            else:
                list(locker.lock_devices(devices))
            logger.bind(action=action, count=len(devices)).info(
                "{} devices via Streamlit", action.capitalize()
            )
        except UniFiAPIError as exc:
            st.error(f"UniFi API error while attempting to {action} devices: {exc}")
            logger.exception("Failed to {} devices", action)
        else:
            event_time = datetime.now()
            st.session_state["last_action"] = {
                "message": f"{action.title()}ed {len(devices)} device(s)",
                "timestamp": event_time,
            }
            toast_icon = "🔓" if unlock else "🔒"
            st.toast(
                f"{action.title()}ed {len(devices)} device(s)",
                icon=toast_icon,
            )
            refresh_dashboard(at=event_time)


def refresh_dashboard(*, at: datetime | None = None) -> None:
    """Record the most recent refresh time and rerun the app."""
    timestamp = at or datetime.now()
    st.session_state["last_refreshed"] = timestamp
    st.session_state["last_auto_refresh"] = timestamp
    st.rerun()


def maybe_trigger_auto_refresh() -> None:
    """Rerun the app when the session's refresh interval elapses."""
    interval_seconds = st.session_state.get("refresh_interval_seconds", 0)
    if not interval_seconds:
        return

    last_auto = st.session_state.get("last_auto_refresh")
    if not isinstance(last_auto, datetime):
        st.session_state["last_auto_refresh"] = datetime.now()
        return

    now = datetime.now()
    if (now - last_auto).total_seconds() >= interval_seconds:
        st.session_state["last_auto_refresh"] = now
        refresh_dashboard(at=now)


def render_stat_cards(stats: list[tuple[str, str, str]], *, muted: bool = False) -> None:
    columns = st.columns(len(stats) + 1 if not muted else len(stats), gap="large")
    stats_iter = stats
    if not muted:
        stats_iter = [*stats, ("Last sync", "", "")]

    for index, ((label, value, description), column) in enumerate(
        zip(stats_iter, columns, strict=False)
    ):
        if not muted and index == len(stats):
            column.markdown(
                f"""
                <div class="stat-card" style="text-align:right;">
                    <p class="stat-card__label">{label}</p>
                    <p class="stat-card__value">{value}</p>
                    <p class="stat-card__description">Controller time</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            continue

        card_class = "stat-card stat-card--muted" if muted else "stat-card"
        column.markdown(
            f"""
            <div class="{card_class}">
                <p class="stat-card__label">{label}</p>
                <p class="stat-card__value">{value}</p>
                <p class="stat-card__description">{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_hero(
    total_devices: int,
    locked_total: int,
    owner_count: int,
    refreshed_at: str,
) -> None:
    locked_pct = (
        f"{(locked_total / total_devices * 100):.0f}% locked"
        if total_devices
        else "No devices locked"
    )
    st.markdown(
        f"""
        <section class="hero condensed">
            <h1 class="hero__title">UniFi Device Lock Controller</h1>
            <div class="hero__meta">
                <span class="hero__meta-item"><strong>{total_devices}</strong> registered devices</span>
                <span class="hero__meta-item"><strong>{owner_count}</strong> active owners</span>
                <span class="hero__meta-item"><strong>{locked_total}</strong> locked • {locked_pct}</span>
                <span class="hero__meta-item">Last sync {refreshed_at}</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_owner_table(
    owner: str,
    rows_with_devices: list[tuple[dict[str, object], Device]],
) -> None:
    owner_label = owner.title() if owner else "Unknown owner"
    device_count = len(rows_with_devices)
    subtitle = f"{device_count} device{'s' if device_count != 1 else ''}"
    card = st.container()
    with card:
        st.markdown(
            f"""
            <div class="owner-section">
                <div class="owner-section__header">
                    <div class="owner-section__title">{owner_label}</div>
                    <div class="owner-section__meta">{subtitle}</div>
                </div>
                <hr class="owner-divider"/>
            """,
            unsafe_allow_html=True,
        )
        column_sizes = [6, 2, 1]
        headers = ["Device", "Status", "Action"]
        header_cols = st.columns(column_sizes)
        for col, label in zip(header_cols, headers):
            col.markdown(
                f"<div class='table-heading'>{label}</div>", unsafe_allow_html=True
            )

        for row, device in sorted(
            rows_with_devices, key=lambda item: str(item[0].get("name", "")).lower()
        ):
            vendor_label = row.get("vendor") or "Unknown"
            status_label = "🔒 Locked" if row["locked"] else "🔓 Unlocked"
            status_class = (
                "status-badge--locked" if row["locked"] else "status-badge--unlocked"
            )
            button_label = "🔓 Unlock" if row["locked"] else "🔒 Lock"
            row_cols = st.columns(column_sizes)
            with row_cols[0]:
                st.markdown(
                    f"<div class='device-cell'><span>{row['name']}</span><span class='device-chip device-chip--align'>{row['type'].title()}</span></div>",
                    unsafe_allow_html=True,
                )
                with st.expander("Details", expanded=False):
                    st.markdown(
                        f"""
                        <div class="details-list">
                            <div><span>Owner</span><span>{row['owner'].title()}</span></div>
                            <div><span>Type</span><span>{row['type']}</span></div>
                            <div><span>MAC</span><span><code>{row['mac']}</code></span></div>
                            <div><span>Vendor</span><span>{vendor_label}</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            row_cols[1].markdown(
                f"<div class='device-cell'><span class='status-badge {status_class}'>{status_label}</span></div>",
                unsafe_allow_html=True,
            )
            with row_cols[2]:
                button_type = "secondary" if row["locked"] else "primary"
                clicked = st.button(
                    button_label,
                    key=f"table-action-{row['mac']}",
                    use_container_width=True,
                    help="Unlock this device" if row["locked"] else "Lock this device",
                    type=button_type,
                )
                if clicked:
                    lock_devices([device], unlock=row["locked"])

        st.markdown(
            "</div>",
            unsafe_allow_html=True,
        )


def render_unregistered_cards(
    records_with_devices: list[tuple[dict[str, object], Device]]
) -> None:
    if not records_with_devices:
        st.info("No active unregistered devices detected.")
        return

    chunk_size = 3
    for start in range(0, len(records_with_devices), chunk_size):
        subset = records_with_devices[start : start + chunk_size]
        columns = st.columns(len(subset), gap="large")
        for column, (record, device) in zip(columns, subset, strict=False):
            vendor = record.get("vendor") or "Unknown"
            mac = record.get("mac") or "Unknown"
            last_seen = record.get("last_seen") or "unknown"
            ip_addr = record.get("ip") or "unknown"
            locked = bool(record.get("locked"))
            status_label = "🔒 Locked" if locked else "🔓 Unlocked"
            status_class = (
                "status-badge--locked" if locked else "status-badge--unlocked"
            )
            with column:
                st.markdown(
                    f"""
                    <div class="ghost-card">
                        <div class="ghost-card__title">{record['name']}</div>
                        <div class="ghost-card__meta">
                            <div><strong>MAC:</strong> {mac}</div>
                            <div><strong>IP:</strong> {ip_addr}</div>
                            <div><strong>Vendor:</strong> {vendor}</div>
                            <div><strong>Last seen:</strong> {last_seen}</div>
                        </div>
                        <div style="margin-top:12px;">
                            <span class="status-badge {status_class}">{status_label}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                button_label = "🔓 Unlock" if locked else "🔒 Lock"
                button_type = "secondary" if locked else "primary"
                mac_key = record.get("mac") or f"unknown-{start}"
                if st.button(
                    button_label,
                    key=f"unregistered-action-{mac_key}",
                    use_container_width=True,
                    type=button_type,
                    help="Unlock this device" if locked else "Lock this device",
                ):
                    lock_devices([device], unlock=locked)


def load_unregistered_active_clients() -> list[tuple[dict[str, object], Device]]:
    with locker_context() as (firewall, locker):
        service = NetworkDeviceService(firewall.client)
        try:
            clients = service.list_active_clients()
        except UniFiAPIError as exc:
            st.error(f"UniFi API error while loading active clients: {exc}")
            logger.exception("Failed to load active clients")
            return []

        rules = list(firewall.list_rules())
        unknown_clients: list[tuple[dict[str, object], Device]] = []
        for client_info in clients:
            mac = client_info.get("mac")
            mac_value = mac if isinstance(mac, str) else None
            if not mac_value or device_by_mac(mac_value):
                continue

            vendor = lookup_mac_vendor(mac_value)
            last_seen_value = client_info.get("last_seen")
            try:
                last_seen_raw = (
                    float(last_seen_value) if last_seen_value is not None else 0.0
                )
            except (TypeError, ValueError):
                last_seen_raw = 0.0

            device = Device(
                name=client_info.get("hostname")
                or client_info.get("name")
                or mac_value,
                mac=mac_value,
                type="unknown",
                owner="unregistered",
            )
            locked = locker.is_device_locked(device, rules)

            record: dict[str, object] = {
                "name": device.name,
                "mac": mac_value,
                "ip": client_info.get("ip") or client_info.get("network"),
                "last_seen": _format_timestamp(last_seen_value),
                "last_seen_raw": last_seen_raw,
                "locked": locked,
            }
            if vendor:
                record["vendor"] = vendor
            unknown_clients.append((record, device))

    unknown_clients.sort(
        key=lambda pair: pair[0].get("last_seen_raw", 0.0), reverse=True
    )
    return unknown_clients


def main() -> None:
    st.set_page_config(page_title="UniFi Device Lock Controller", layout="wide")
    apply_global_styles()

    st.session_state.setdefault("last_refreshed", datetime.now())
    st.session_state.setdefault("last_action", None)
    st.session_state.setdefault("refresh_interval_label", "10s")
    st.session_state.setdefault(
        "refresh_interval_seconds",
        REFRESH_INTERVAL_OPTIONS["10s"],
    )
    st.session_state.setdefault("last_auto_refresh", datetime.now())

    with st.spinner("Loading device inventory..."):
        rows_all = load_device_status()

    owners = sorted({row["owner"] for row in rows_all})
    total_devices = len(rows_all)
    locked_total = sum(1 for row in rows_all if row["locked"])
    unknown_total = sum(1 for row in rows_all if not row["vendor"])
    refreshed_at_dt = st.session_state["last_refreshed"]
    refreshed_at = refreshed_at_dt.strftime("%d/%m/%Y • %I:%M:%S%p")

    render_hero(total_devices, locked_total, len(owners), refreshed_at)

    column_weights = [2.4, 3.0, 1.8]
    filter_col, search_col, refresh_col = st.columns(column_weights, gap="large")
    selected_owners = filter_col.multiselect(
        "Owners",
        owners,
        placeholder="All owners",
    )
    search_term = search_col.text_input(
        "Search devices",
        placeholder="Search by name, MAC, type, or vendor",
    )
    with refresh_col:
        options = list(REFRESH_INTERVAL_OPTIONS.keys())
        default_index = options.index(st.session_state["refresh_interval_label"])
        selected_label = st.radio(
            "Auto refresh",
            options,
            index=default_index,
            horizontal=True,
            key="refresh-interval-selector",
        )
        if selected_label != st.session_state["refresh_interval_label"]:
            st.session_state["refresh_interval_label"] = selected_label
            st.session_state["refresh_interval_seconds"] = REFRESH_INTERVAL_OPTIONS[
                selected_label
            ]
            st.session_state["last_auto_refresh"] = datetime.now()
        st.caption(f"Refreshing every {selected_label}")
        if st.button("Refresh status", use_container_width=True):
            refresh_dashboard()

    maybe_trigger_auto_refresh()

    owner_filter = set(selected_owners) if selected_owners else None
    rows_owner_filtered = [
        row for row in rows_all if not owner_filter or row["owner"] in owner_filter
    ]

    search_lower = search_term.strip().lower()
    if search_lower:
        rows_filtered = [
            row
            for row in rows_owner_filtered
            if search_lower
            in " ".join(
                str(row[field]).lower() if row.get(field) else ""
                for field in ("name", "owner", "type", "mac", "vendor")
            )
        ]
    else:
        rows_filtered = rows_owner_filtered

    rows_with_devices = [
        (row, device)
        for row in rows_filtered
        if (device := device_by_mac(row["mac"])) is not None
    ]
    filtered_devices = [device for _, device in rows_with_devices]

    rows_by_owner: dict[str, list[tuple[dict[str, object], Device]]] = {}
    for row, device in rows_with_devices:
        rows_by_owner.setdefault(device.owner, []).append((row, device))

    filtered_total = len(rows_filtered)
    filtered_locked = sum(1 for row in rows_filtered if row["locked"])
    filtered_unknown = sum(1 for row in rows_filtered if not row["vendor"])

    global_stats = [
        ("Total devices", str(total_devices), "Registered across the network"),
        (
            "Locked devices",
            str(locked_total),
            f"{(locked_total / total_devices * 100):.0f}% of inventory"
            if total_devices
            else "No locks applied",
        ),
        ("Unknown vendors", str(unknown_total), "Devices missing vendor metadata"),
    ]

    filtered_stats = [
        ("Filtered devices", str(filtered_total), "Match current filters"),
        ("Filtered locked", str(filtered_locked), "Locks within filtered set"),
        ("Filtered unknown", str(filtered_unknown), "Filtered devices without vendors"),
    ]

    action_row = st.columns(2)
    lock_disabled = not filtered_devices
    if action_row[0].button(
        "🔒 Lock filtered",
        use_container_width=True,
        disabled=lock_disabled,
        type="primary",
    ):
        lock_devices(filtered_devices, unlock=False)
    if action_row[1].button(
        "🔓 Unlock filtered",
        use_container_width=True,
        disabled=lock_disabled,
        type="secondary",
    ):
        lock_devices(filtered_devices, unlock=True)

    with st.expander("Filter details", expanded=False):
        render_stat_cards(global_stats)
    render_stat_cards(filtered_stats, muted=True)

    st.markdown("### Registered devices")
    if rows_by_owner:
        for owner in sorted(rows_by_owner):
            render_owner_table(owner, rows_by_owner[owner])
    else:
        st.info("No devices match the selected filters.")

    with st.spinner("Checking for active unregistered clients..."):
        unregistered_clients = load_unregistered_active_clients()
    if search_lower:
        unregistered_clients = [
            (record, device)
            for record, device in unregistered_clients
            if search_lower
            in " ".join(
                str(record.get(field, "")).lower()
                for field in ("name", "mac", "ip", "vendor", "last_seen")
            )
        ]

    st.markdown("### Active unregistered devices")
    render_unregistered_cards(unregistered_clients)


if __name__ == "__main__":
    main()
