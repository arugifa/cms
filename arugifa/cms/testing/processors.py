import gzip
import inspect
from abc import ABC, abstractmethod, abstractproperty
from typing import ClassVar

import pytest

from arugifa.cms import exceptions
from arugifa.cms.base.processors import BaseFileProcessor


class BaseFileProcessorTest(ABC):
    processor: ClassVar[BaseFileProcessor] = None  # Processor class to test

    @abstractproperty
    @pytest.fixture(scope='class')
    def source_file(self, fixtures):
        return fixtures['document.html']

    # Process file.

    @abstractmethod
    def test_process_file(self):
        pass

    # Collect errors.

    async def test_collect_errors(self, app, tmp_path):
        source_file = tmp_path / 'invalid_file.html'
        source_file.write_text("Invalid file")

        processor = self.processor(source_file)
        error_count = 0

        with processor.collect_errors() as errors:
            for name, method in inspect.getmembers(processor):
                if name.startswith('process_'):
                    result = await method()  # Should probably raise

                elif name.startswith('scan_'):
                    result = method()  # Should probably raise

                else:
                    continue

                if result is None:
                    error_count += 1

            assert len(errors) == error_count

    # Load file.

    async def test_load_file(self, tmp_path):
        source_file = tmp_path / 'source_file.html'
        source_file.write_text("Hello, World!")

        processor = self.processor(source_file)
        source = await processor.load()

        # XXX: How to test loading different file formats? (03/2020)
        # assert source.html.text_content() == "Hello, World!"
        assert source is not None

    async def test_load_not_existing_file(self, tmp_path):
        source_file = tmp_path / 'missing.html'

        with pytest.raises(exceptions.FileLoadingError):
            await self.processor(source_file).load()

    async def test_load_not_supported_file_format(self, tmp_path):
        archive = tmp_path / 'source_file.html.gz'

        with gzip.open(str(archive), 'wb') as f:
            f.write(b'random content')

        with pytest.raises(exceptions.FileLoadingError):
            await self.processor(archive).load()
