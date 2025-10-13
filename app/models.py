"""Base Models for the Base FastAPI application."""

from typing import ClassVar, Optional
from datetime import datetime
from pydantic import BaseModel, SecretStr, ConfigDict
from fastapi import Query


class IglwBase(BaseModel):
    """Base Pydantic model with shared config for Dispatch models."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
        json_encoders={
            # custom output conversion for datetime
            datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if v else None,
            SecretStr: lambda v: v.get_secret_value() if v else None,
        },
    )


class Pagination(IglwBase):
    """Pagination base model."""

    total: int
    page: int
    per_page: int


class QueryBase(IglwBase):
    """Base class for lead query parameters."""

    page: int = Query(1, ge=1)
    page_size: int = Query(10, ge=1, le=10000)

    search: Optional[str] = None
