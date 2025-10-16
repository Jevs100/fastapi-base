"""This module defines the lead workflow stages router."""

from typing import Any
from datetime import datetime, timezone
from sqlalchemy.orm import mapped_column, Mapped, declarative_mixin
from sqlalchemy import DateTime, inspect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    __repr_attrs__: list[Any] = []
    __repr_max_length__ = 15

    def dict(self):
        """Returns a dict representation of a model."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @property
    def _id_str(self):
        ids = inspect(self).identity
        if ids:
            if ids and len(ids) > 1:
                return "-".join([str(x) for x in ids])
            elif ids and len(ids) == 1:
                return str(ids[0])
            else:
                return "None"
        else:
            return "None"

    @property
    def _repr_attrs_str(self):
        max_length = self.__repr_max_length__

        values: list[Any] = []
        single = len(self.__repr_attrs__) == 1
        for key in self.__repr_attrs__:
            if not hasattr(self, key):
                raise KeyError(
                    "{} has incorrect attribute '{}' in __repr__attrs__".format(
                        self.__class__, key
                    )
                )
            value = getattr(self, key)
            wrap_in_quote = isinstance(value, str)

            value = str(value)
            if len(value) > max_length:
                value = value[:max_length] + "..."

            if wrap_in_quote:
                value = "'{}'".format(value)
            values.append(value if single else "{}:{}".format(key, value))

        return " ".join(values)

    def __repr__(self):
        # get id like '#123'
        id_str = ("#" + self._id_str) if self._id_str else ""
        # join class name, id and repr_attrs
        return "<{} {}{}>".format(
            self.__class__.__name__,
            id_str,
            " " + self._repr_attrs_str if self._repr_attrs_str else "",
        )


@declarative_mixin
class TimeStampMixin(object):
    """Timestamping mixin for created_at and updated_at fields."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    created_at._creation_order = 9998  # type: ignore
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at._creation_order = 9998  # type: ignore


@declarative_mixin
class SoftDeleteMixin(object):
    """Soft delete mixin for deleted_at field."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True
    )
    deleted_at._creation_order = 9999  # type: ignore
