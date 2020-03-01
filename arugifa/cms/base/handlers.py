from abc import abstractmethod
from pathlib import Path
from typing import Any, Callable, ClassVar

import aiofiles

from arugifa.cms.base.processors import BaseFileProcessor


class BaseFileHandler:
    #: Model class.
    model: ClassVar[Any]
    #: Processor class.
    processor: ClassVar[BaseFileProcessor]

    def __init__(self, path: Path, *, reader: Callable = aiofiles.open):
        #: Processor to analyze source file.
        self.source_file = self.processor(path, reader=reader)

        # self.logger = CustomAdapter(logger, {'source_file': self.source_file.path})

    @abstractmethod
    async def insert(self) -> Any:
        pass

    @abstractmethod
    async def update(self) -> Any:
        pass

    @abstractmethod
    async def rename(self) -> Any:
        pass

    @abstractmethod
    async def delete(self) -> None:
        pass
