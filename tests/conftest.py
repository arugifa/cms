import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from arugifa.cms.git import GitRepository


# Configuration

def pytest_collection_modifyitems(items):
    """Apply dynamic test markers."""
    for item in items:
        # Apply marker to identify async tests.
        if inspect.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


# Fixtures

@pytest.fixture
def db(db_session):
    yield db_session
    db_session.rollback()


@pytest.fixture(scope='session')
def db_engine():
    return create_engine('sqlite:///:memory:')


@pytest.fixture(scope='session')
def db_session(db_engine):
    return sessionmaker(bind=db_engine)()


@pytest.fixture(scope='session')
def git():
    return GitRepository
