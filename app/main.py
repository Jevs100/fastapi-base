"""Main module for the Base FastAPI application."""

from fastapi import FastAPI
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize resources here
    yield
    # Cleanup resources here
