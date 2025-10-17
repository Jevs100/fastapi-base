"""This module manages the database connection"""

import json
import time
import logging
from typing import Any, AsyncGenerator
from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base


class AppMysqlManager:
    """This class manages the database connection"""

    pool_logger: bool
    command_logger: bool

    def __init__(
        self,
        pool_logger: bool = False,
        command_logger: bool = False,
    ) -> None:
        """Initialize the database manager"""

        self.pool_logger = pool_logger
        self.command_logger = command_logger
        self.engine = None
        self.async_session_local = None
        self.base = None

    async def startup(self, **kwargs: Any) -> None:
        """Startup function to initialize the database connection"""
        self.engine = create_async_engine(
            **kwargs,
            echo=False,
            pool_pre_ping=True,
            # defaults pool_size=5, max_overflow=10, pool_timeout=30, pool_recycle=1800
        )
        # Attach event listeners here
        if self.command_logger:
            MysqlCommandLogger.attach(
                self.engine.sync_engine, logging.getLogger("mysql")
            )
        self.async_session_local = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.base = declarative_base()

    async def get_db(self) -> AsyncGenerator[Any, Any]:
        """This function returns the database session"""
        if self.async_session_local is None:
            await self.startup()
            if self.async_session_local is None:
                raise Exception("Database connection failed for service 'be-gateway'")
        async with self.async_session_local() as session:
            yield session

    async def shutdown(self):
        """This function closes the database connection"""
        if self.engine is None:
            return
        await self.engine.dispose()


class MysqlCommandLogger:
    """This class logs SQL commands executed on the MySQL database"""

    @staticmethod
    def attach(engine: Engine, logger: logging.Logger) -> None:
        """Attach the command logger to the SQLAlchemy engine"""

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(  # noqa: F811
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            context._query_start_time = time.perf_counter()

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            duration = (time.perf_counter() - context._query_start_time) * 1000
            level = "white"
            performance = "UNKNOWN"

            try:
                raw = statement + " | " + json.dumps(parameters, default=str)
                payload_bytes = len(raw.encode("utf-8"))
            except Exception:
                payload_bytes = None

            if duration > 1000:
                level = "level6"
                performance = "CRITICAL"
            elif duration > 500:
                level = "level5"
                performance = "VERY SLOW"
            elif duration > 250:
                level = "level4"
                performance = "SLOW"
            elif duration > 100:
                level = "level3"
                performance = "FAST"
            elif duration > 10:
                level = "level2"
                performance = "VERY FAST"
            else:
                level = "level1"
                performance = "OPTIMAL"

            logger.info(
                f"[MysqlCommandLogger] SQL Success | [{performance}] Duration: {duration:.2f} ms | "
                f"Payload size: {payload_bytes if payload_bytes is not None else 'unknown'} bytes\n"
                f"Query: {statement}\n"
                f"Parameters: {json.dumps(parameters, default=str) if parameters else 'None'}"
            )

        @event.listens_for(engine, "handle_error")
        def handle_error(exception_context: Any) -> None:
            statement = exception_context.statement
            parameters = exception_context.parameters
            error = exception_context.original_exception

            logger.error(
                f"[MysqlCommandLogger] SQL Error | Error: {error}\n"
                f"Query: {statement}\n"
                f"Parameters: {json.dumps(parameters, default=str) if parameters else 'None'}"
            )
