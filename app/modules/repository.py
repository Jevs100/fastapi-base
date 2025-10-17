"""Base repository class."""

from typing import Generic, Optional, TypeVar, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Base repository class for main entities."""

    model: type[T]

    async def get(self, db: AsyncSession, limit: Optional[int] = 100) -> Sequence[T]:
        """Get all records of the model."""
        result = await db.execute(select(self.model).limit(limit))
        return result.scalars().all()

    async def get_paginated(
        self, db: AsyncSession, offset: int = 0, limit: int = 100
    ) -> Sequence[T]:
        """Get paginated records of the model."""
        result = await db.execute(select(self.model).offset(offset).limit(limit))
        return result.scalars().all()

    async def get_by_id(self, db: AsyncSession, id: int) -> T | None:
        """Get a record by its ID."""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()

    async def create(self, db: AsyncSession, obj: T) -> T:
        """Create a new record."""
        db.add(obj)
        await db.flush()
        return obj

    async def update(self, db: AsyncSession, obj: T) -> T:
        """Update an existing record."""
        await db.flush()
        return obj

    async def delete(self, db: AsyncSession, obj: T) -> None:
        """Delete a record."""
        await db.delete(obj)
        await db.flush()
