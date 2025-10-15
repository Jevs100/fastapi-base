"""This module provides utilities for logging SQLAlchemy operations"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.event import listens_for
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import History
from sqlalchemy.orm.state import AttributeState, InstanceState
from modules.base import Base


@dataclass(frozen=True)
class BlockChangeContext:
    """Metadata for a block operation that mutates multiple models."""

    operation: str
    block_id: str
    lead_uuid: str


_BLOCK_CHANGE_CONTEXT_KEY = "block_change_context"
_BLOCK_CHANGE_RECORDS_KEY = "block_change_records"


def _get_sync_session(db_session: Session | AsyncSession) -> Session:
    """Return a synchronous SQLAlchemy Session for event compatibility."""
    if isinstance(db_session, AsyncSession):
        return db_session.sync_session
    return db_session


def _serialize_value(value: Any) -> Any:
    """Convert common ORM values into JSON-serializable primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _serialize_value(value.value)
    if isinstance(value, Mapping):
        mapped_value = cast(Mapping[Any, Any], value)
        return {str(k): _serialize_value(v) for k, v in mapped_value.items()}
    if isinstance(value, (list, tuple, set)):
        iterable_value = cast(Sequence[Any], value)
        return [_serialize_value(v) for v in iterable_value]
    return str(value)


@contextmanager
def block_change_tracking(
    db_session: Session | AsyncSession,
    operation: str,
    block_id: str,
    lead_uuid: str,
):
    """Track ORM changes during one block operation execution."""
    sync_session = _get_sync_session(db_session)
    sync_session.info[_BLOCK_CHANGE_CONTEXT_KEY] = BlockChangeContext(
        operation=operation,
        block_id=block_id,
        lead_uuid=lead_uuid,
    )
    sync_session.info[_BLOCK_CHANGE_RECORDS_KEY] = []
    try:
        yield
    except Exception:
        sync_session.info.pop(_BLOCK_CHANGE_CONTEXT_KEY, None)
        sync_session.info.pop(_BLOCK_CHANGE_RECORDS_KEY, None)
        raise
    finally:
        sync_session.info.pop(_BLOCK_CHANGE_CONTEXT_KEY, None)


def pop_block_changes(db_session: Session | AsyncSession) -> list[dict[str, Any]]:
    """Return and clear collected block change records."""
    sync_session = _get_sync_session(db_session)
    records = list(sync_session.info.get(_BLOCK_CHANGE_RECORDS_KEY, []))
    sync_session.info[_BLOCK_CHANGE_RECORDS_KEY] = []
    return records


def _append_or_merge_change(session: Session, record: dict[str, Any]) -> None:
    """Merge updates for the same entity to avoid noisy duplicate records."""
    records = list(session.info.get(_BLOCK_CHANGE_RECORDS_KEY, []))

    if record.get("operation") == "update":
        for existing in records:
            if (
                existing.get("operation") == "update"
                and existing.get("model") == record.get("model")
                and existing.get("entity_id") == record.get("entity_id")
            ):
                existing_fields = cast(
                    dict[str, Any], existing.setdefault("fields", {})
                )
                new_fields = cast(dict[str, Any], record.get("fields", {}))
                existing_fields.update(new_fields)
                session.info[_BLOCK_CHANGE_RECORDS_KEY] = records
                return

    records.append(record)
    session.info[_BLOCK_CHANGE_RECORDS_KEY] = records


def _entity_id(state: InstanceState[Any]) -> str | None:
    identity = state.identity or ()
    return "-".join(str(part) for part in identity) if identity else None


def _column_keys(state: InstanceState[Any]) -> list[str]:
    return [column.key for column in state.mapper.column_attrs]


def _first_or_none(values: Sequence[Any]) -> Any | None:
    """Return the first history value when present."""
    return values[0] if values else None


def _field_change_from_history(hist: History) -> dict[str, Any] | None:
    """Return normalized old/new pair when values differ; otherwise None."""
    old_value = _serialize_value(_first_or_none(hist.deleted))
    new_value = _serialize_value(_first_or_none(hist.added))

    if old_value == new_value:
        return None

    return {"old": old_value, "new": new_value}


def _field_change_pair(old_value: Any, new_value: Any) -> dict[str, Any] | None:
    """Return normalized old/new pair when values differ; otherwise None."""
    normalized_old = _serialize_value(old_value)
    normalized_new = _serialize_value(new_value)

    if normalized_old == normalized_new:
        return None

    return {"old": normalized_old, "new": normalized_new}


@listens_for(Session, "before_flush")
def collect_block_changes(
    session: Session, _flush_context: Any, _instances: Any
) -> None:
    """Collect ORM changes for active block tracking scope."""
    context = session.info.get(_BLOCK_CHANGE_CONTEXT_KEY)
    if context is None:
        return

    for instance in session.new:
        if not isinstance(instance, Base):
            continue

        state: InstanceState[Any] = cast(InstanceState[Any], inspect(instance))
        fields: dict[str, dict[str, Any]] = {}
        for key in _column_keys(state):
            field_change = _field_change_pair(None, getattr(instance, key, None))
            if field_change is None:
                continue
            fields[key] = field_change

        if not fields:
            continue

        _append_or_merge_change(
            session,
            {
                "operation": "create",
                "model": instance.__class__.__name__,
                "entity_id": _entity_id(state),
                "fields": fields,
            },
        )

    for instance in session.dirty:
        if not isinstance(instance, Base):
            continue
        if not session.is_modified(instance, include_collections=False):
            continue

        state = cast(InstanceState[Any], inspect(instance))
        fields: dict[str, dict[str, Any]] = {}
        for key in _column_keys(state):
            attr: AttributeState = state.attrs[key]
            hist: History = attr.history
            if not hist.has_changes():
                continue
            field_change = _field_change_from_history(hist)
            if field_change is None:
                continue
            fields[key] = field_change

        if fields:
            _append_or_merge_change(
                session,
                {
                    "operation": "update",
                    "model": instance.__class__.__name__,
                    "entity_id": _entity_id(state),
                    "fields": fields,
                },
            )

    for instance in session.deleted:
        if not isinstance(instance, Base):
            continue

        state = cast(InstanceState[Any], inspect(instance))
        fields: dict[str, dict[str, Any]] = {}
        for key in _column_keys(state):
            field_change = _field_change_pair(getattr(instance, key, None), None)
            if field_change is None:
                continue
            fields[key] = field_change

        if not fields:
            continue

        _append_or_merge_change(
            session,
            {
                "operation": "delete",
                "model": instance.__class__.__name__,
                "entity_id": _entity_id(state),
                "fields": fields,
            },
        )
