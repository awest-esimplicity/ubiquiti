"""Owner metadata and PIN configuration with repository abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import get_engine, get_session_factory, is_database_configured
from .db_models import OwnerModel


@dataclass(frozen=True)
class Owner:
    """Represents an owner in the dashboard with a secure access PIN."""

    key: str
    display_name: str
    pin: str


class OwnerRepository(Protocol):
    """Port defining operations for managing owners."""

    def get(self, key: str | None) -> Owner | None:
        ...

    def list_all(self) -> list[Owner]:
        ...

    def verify_pin(self, owner_key: str, pin: str) -> bool:
        ...

    def register(self, owner: Owner) -> None:
        ...


class InMemoryOwnerRepository(OwnerRepository):
    """Adapter that manages owners in memory."""

    def __init__(self, owners: list[Owner]) -> None:
        self._owners: dict[str, Owner] = {owner.key.lower(): owner for owner in owners}

    def get(self, key: str | None) -> Owner | None:
        if key is None:
            return None
        return self._owners.get(key.lower())

    def list_all(self) -> list[Owner]:
        return list(self._owners.values())

    def verify_pin(self, owner_key: str, pin: str) -> bool:
        owner = self.get(owner_key)
        return owner is not None and owner.pin == pin.strip()

    def register(self, owner: Owner) -> None:
        self._owners[owner.key.lower()] = owner


class SQLAlchemyOwnerRepository(OwnerRepository):
    """Adapter that manages owners via SQLAlchemy."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, key: str | None) -> Owner | None:
        if key is None:
            return None
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(OwnerModel).where(OwnerModel.key == key.lower())
                )
                .scalars()
                .first()
            )
            return (
                Owner(key=row.key, display_name=row.display_name, pin=row.pin)
                if row
                else None
            )

    def list_all(self) -> list[Owner]:
        with self._session_factory() as session:
            rows = session.execute(select(OwnerModel)).scalars().all()
            return [
                Owner(key=row.key, display_name=row.display_name, pin=row.pin)
                for row in rows
            ]

    def verify_pin(self, owner_key: str, pin: str) -> bool:
        owner = self.get(owner_key)
        return owner is not None and owner.pin == pin.strip()

    def register(self, owner: Owner) -> None:
        with self._session_factory() as session:
            instance = session.get(OwnerModel, owner.key.lower())
            if instance is None:
                instance = OwnerModel(
                    key=owner.key.lower(),
                    display_name=owner.display_name,
                    pin=owner.pin,
                )
                session.add(instance)
            else:
                instance.display_name = owner.display_name
                instance.pin = owner.pin
            session.commit()


MASTER_OWNER = Owner("master", "Master Control", "5161")

DEFAULT_OWNERS: list[Owner] = [
    MASTER_OWNER,
    Owner("house", "House", "3841"),
    Owner("jayce", "Jayce", "7023"),
    Owner("kade", "Kade", "9482"),
    Owner("kailah", "Kailah", "2157"),
]


@lru_cache
def _default_owner_repository() -> InMemoryOwnerRepository:
    return InMemoryOwnerRepository(list(DEFAULT_OWNERS))


_SQL_OWNER_REPOSITORY: SQLAlchemyOwnerRepository | None = None


def _get_sql_owner_repository() -> SQLAlchemyOwnerRepository:
    global _SQL_OWNER_REPOSITORY
    if _SQL_OWNER_REPOSITORY is None:
        session_factory = get_session_factory()
        _SQL_OWNER_REPOSITORY = SQLAlchemyOwnerRepository(session_factory)
    return _SQL_OWNER_REPOSITORY


def get_owner_repository() -> OwnerRepository:
    """Return the configured owner repository."""
    if is_database_configured() and get_engine() is not None:
        try:
            return _get_sql_owner_repository()
        except RuntimeError:
            return _default_owner_repository()
    return _default_owner_repository()


def get_owner(key: str | None) -> Owner | None:
    """Return the Owner entry for the given key, if one exists."""
    return get_owner_repository().get(key)


def register_owner(owner: Owner) -> None:
    """Register or override an Owner entry."""
    get_owner_repository().register(owner)


def all_owners() -> dict[str, Owner]:
    """Return a copy of the owner registry."""
    repository = get_owner_repository()
    return {owner.key.lower(): owner for owner in repository.list_all()}


def verify_owner_pin(owner_key: str, pin: str) -> bool:
    """Validate the provided PIN for the owner."""
    return get_owner_repository().verify_pin(owner_key, pin)


__all__ = [
    "Owner",
    "OwnerRepository",
    "InMemoryOwnerRepository",
    "SQLAlchemyOwnerRepository",
    "MASTER_OWNER",
    "DEFAULT_OWNERS",
    "get_owner_repository",
    "get_owner",
    "register_owner",
    "all_owners",
    "verify_owner_pin",
]
