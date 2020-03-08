import inspect

import pytest

from arugifa.cms.git import GitRepository


# Configuration

def pytest_collection_modifyitems(items):
    """Apply dynamic test markers."""
    for item in items:
        # Apply marker to identify async tests.
        if inspect.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


@pytest.fixture(scope='session')
def git():
    return GitRepository
