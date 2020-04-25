"""Base classes to test documents processing."""

from hashlib import sha1
from typing import ClassVar

import pytest
from arugifa.toolbox.cli.testing import BaseCommandLineTest

from arugifa.cms.readers import BaseFileReader


class BaseReaderTest(BaseCommandLineTest):
    reader: ClassVar[BaseFileReader] = None  # Reader class to test

    @pytest.fixture
    def program_factory(self):
        # To be defined for BaseCommandLineTest.
        return self.reader

    # Open document.

    def test_open_not_existing_file(self, tmp_path):
        source_file = tmp_path / 'missing.txt'

        with pytest.raises(FileNotFoundError):
            self.reader()(source_file)

    # Read document.

    async def test_error_happening_while_reading_file(self, shell, tmp_path):
        source_file = tmp_path / 'source_file.txt'
        source_file.touch()

        reader = self.reader(shell=shell)
        shell.result = ("Invalid file", 1)

        with pytest.raises(OSError) as excinfo:
            await reader(source_file).read()

        assert "Invalid file" in str(excinfo)

    async def test_cannot_decode_reader_output(self, shell, tmp_path):
        source_file = tmp_path / 'source_file.txt'
        source_file.touch()

        shell.result = sha1(b"Nich Gut!").digest()
        reader = self.reader(shell=shell)

        with pytest.raises(UnicodeDecodeError):
            await reader(source_file).read()
