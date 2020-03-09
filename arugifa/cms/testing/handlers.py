from abc import ABC, abstractmethod
from typing import ClassVar

from arugifa.cms.base.handlers import BaseFileHandler


class BaseFileHandlerTest(ABC):
    handler: ClassVar[BaseFileHandler] = None  # Handler class to test

    # Insert file.

    @abstractmethod
    async def test_insert_file(self):
        pass

    # Update file.

    @abstractmethod
    async def test_update_file(self):
        pass

    # Rename file.

    @abstractmethod
    async def test_rename_file(self):
        pass

    # Delete file.

    @abstractmethod
    def test_delete_file(self):
        pass
