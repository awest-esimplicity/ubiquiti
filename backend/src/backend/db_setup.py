"""Utility CLI for creating and seeding the SQL database."""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .database import get_engine, get_session_factory, is_database_configured
from .db_models import Base, DeviceModel, OwnerModel, ScheduleModel
from .defaults import DEFAULT_SCHEDULE_CONFIG
from .owners import DEFAULT_OWNERS, Owner
from .schedules import get_schedule_repository
from .schemas import ScheduleConfig
from .ubiquiti.devices import DEVICES, Device


def ensure_configured() -> None:
    if not is_database_configured():
        raise SystemExit("UBIQUITI_DB_URL is not set; cannot run database commands.")


def init_db() -> None:
    """Create database tables if they do not already exist."""
    ensure_configured()
    engine = get_engine()
    if engine is None:
        raise SystemExit("Unable to create engine for configured database URL.")

    Base.metadata.create_all(engine)
    print("Database tables ensured.")


def _merge_owners(session, owners: list[Owner], *, mode: str, force: bool) -> None:
    if mode == "replace" and owners:
        session.query(OwnerModel).delete()
    for owner in owners:
        session.merge(
            OwnerModel(
                key=owner.key.lower(),
                display_name=owner.display_name,
                pin=owner.pin,
            )
        )


def _merge_devices(
    session,
    devices: list[Device],
    *,
    mode: str,
    owner_mode: str,
    force: bool,
) -> None:
    if mode == "replace" and devices:
        session.query(DeviceModel).delete()
    for device in devices:
        session.merge(
            DeviceModel(
                name=device.name,
                mac=device.mac.lower(),
                device_type=device.type,
                owner_key=device.owner.lower(),
            )
        )


def seed_db(
    *,
    force: bool = False,
    owner_mode: str = "merge",
    device_mode: str = "merge",
    schedule_mode: str = "merge",
) -> None:
    """Seed the database with default owners, devices, and schedules."""
    ensure_configured()
    session_factory = get_session_factory()

    owner_mode = owner_mode.lower()
    device_mode = device_mode.lower()
    schedule_mode = schedule_mode.lower()
    if owner_mode not in {"merge", "replace"}:
        raise SystemExit("owner_mode must be 'merge' or 'replace'.")
    if device_mode not in {"merge", "replace"}:
        raise SystemExit("device_mode must be 'merge' or 'replace'.")
    if schedule_mode not in {"merge", "replace"}:
        raise SystemExit("schedule_mode must be 'merge' or 'replace'.")

    try:
        with session_factory() as session:
            owners_existing = session.execute(select(OwnerModel)).scalars().first()
            devices_existing = session.execute(select(DeviceModel)).scalars().first()
            schedules_existing = session.execute(select(ScheduleModel)).scalars().first()
            if owners_existing and devices_existing and schedules_existing and not force:
                print("Database already contains seed data; skipping.")
                return

            _merge_owners(session, DEFAULT_OWNERS, mode=owner_mode, force=force)
            _merge_devices(
                session,
                DEVICES,
                mode=device_mode,
                owner_mode=owner_mode,
                force=force,
            )

            session.commit()

        schedule_repo = get_schedule_repository()
        schedule_config = ScheduleConfig.model_validate(DEFAULT_SCHEDULE_CONFIG)
        schedule_repo.sync_from_config(
            schedule_config,
            replace=schedule_mode == "replace" or force,
        )
        print("Seed data inserted.")
    except SQLAlchemyError as exc:
        raise SystemExit(f"Failed to seed database: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the backend SQL database.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database tables.")
    seed_parser = sub.add_parser("seed", help="Seed the database with sample data.")
    seed_parser.add_argument(
        "--force",
        action="store_true",
        help="Insert seed data even if records already exist.",
    )
    seed_parser.add_argument(
        "--owner-mode",
        choices=["merge", "replace"],
        default="merge",
        help="Merge with or replace existing owners (default: merge).",
    )
    seed_parser.add_argument(
        "--device-mode",
        choices=["merge", "replace"],
        default="merge",
        help="Merge with or replace existing devices (default: merge).",
    )
    seed_parser.add_argument(
        "--schedule-mode",
        choices=["merge", "replace"],
        default="merge",
        help="Merge with or replace existing schedules (default: merge).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "init":
        init_db()
    elif args.command == "seed":
        seed_db(
            force=args.force,
            owner_mode=args.owner_mode,
            device_mode=args.device_mode,
            schedule_mode=args.schedule_mode,
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main(sys.argv[1:])
