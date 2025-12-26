"""Shared test fixtures and configuration for pytest."""

import asyncio
from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_database_url() -> str:
    """Mock database URL for testing."""
    return "postgresql://test:test@localhost:5432/test_debate"


@pytest.fixture
def mock_redis_url() -> str:
    """Mock Redis URL for testing."""
    return "redis://localhost:6379/1"
