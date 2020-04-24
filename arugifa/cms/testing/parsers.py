import inspect
from typing import ClassVar

from arugifa.cms.base.parsers import BaseSourceParser


class BaseSourceParserTest:
    parser: ClassVar[BaseSourceParser] = None  # Handler class to test

    # Collect errors.

    async def test_collect_errors(self):
        parser = self.parser('')
        error_count = 0

        with parser.collect_errors() as errors:
            for name, method in inspect.getmembers(parser):
                if name.startswith('parse_'):
                    result = method()  # Should probably raise

                else:
                    continue

                if result is None:
                    error_count += 1

            assert len(errors) == error_count
