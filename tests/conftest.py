import inspect
import sys

import pytest

from arugifa.cms.git import GitRepository

if not sys.warnoptions:
    # TODO: Remove when aiofiles will have been migrated to Python 3.8 (03/2020)
    # Otherwise, tests output is polluted with tons of messages like:
    #
    #   DeprecationWarning: "@coroutine" decorator is deprecated since Python 3.8,
    #                       use "async def" instead
    #
    import aiofiles
    import warnings
    warnings.filterwarnings('ignore', category=DeprecationWarning, module=aiofiles.__name__)  # noqa: E501


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
