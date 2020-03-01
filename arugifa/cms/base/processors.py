from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, ClassVar, Tuple

import aiofiles

from arugifa.cms import exceptions
from arugifa.cms.base.parsers import BaseSourceParser
from arugifa.cms.exceptions import FileProcessingError, SourceParsingError
from arugifa.cms.typing import FileProcessingErrors, FileProcessingResult


class CatchProcessorErrors(type):
    """Meta-class used by all document processors.

    Catch errors automatically when calling processing or scanning methods
    (i.e., methods starting with ``process_`` or ``scan_``).

    This allows to process a document all at once, without having to bother with
    multiple try-catch blocks.
    """

    def __new__(meta, classname, supers, classdict) -> 'BaseFileProcessor':  # noqa: C901, D102, E501, N804

        def catch_processing_errors(func):
            async def wrapper(self, *args, **kwargs):
                try:
                    return await func(self, *args, **kwargs)
                except (FileProcessingError, SourceParsingError) as exc:
                    if not self._catch_errors:
                        raise

                    self._errors.add(exc)
                    # self.logger.debug(f"Processing error: {exc}")

            return wrapper

        def catch_scanning_errors(func):
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except exceptions.FilePathScanningError as exc:
                    if not self._catch_errors:
                        raise

                    self._errors.add(exc)
                    # self.logger.debug(f"Path scanning error: {exc}")

            return wrapper

        for attr, attrval in classdict.items():
            if attr.startswith('process_'):
                classdict[attr] = catch_processing_errors(attrval)

            elif attr.startswith('scan_'):
                classdict[attr] = catch_scanning_errors(attrval)

        return type.__new__(meta, classname, supers, classdict)


class BaseFileProcessor(metaclass=CatchProcessorErrors):
    #: File parser class.
    parser: ClassVar[BaseSourceParser]

    def __init__(self, path: Path, *, reader: Callable = aiofiles.open):
        self.path = path
        self.reader = reader

        self._source = None  # To cache source
        self._errors = set()  # To store processing/parsing errors

        # To catch potential exceptions when processing source file.
        self._catch_errors = False

        # self.logger = CustomAdapter(logger, {'source_file': self.path})

    @abstractmethod
    async def process(self) -> Tuple[FileProcessingResult, FileProcessingErrors]:
        """Analyze source file.

        :return: item's attributes, as defined in item's model.
        """

    # Helpers

    @contextmanager
    def collect_errors(self) -> FileProcessingErrors:
        """Catch  and return potential errors when processing source file.

        Can be used as follows::

            class ArticleFileProcessor(BaseFileProcessor):
                parser = ArticleSourceParser

                def scan_uri(self):
                    # Look for URI in file's path.

                def process_category(self):
                    # Parse and look for article's category in database.

                def proces_tags(self):
                    # Parse and look for article's tags in database.

            article_file = ArticleFileProcessor(article_path)

            with article_file.collect_errors() as errors:
                article = {
                    'uri': article_file.scan_uri(),
                    'category': article_file.process_category(),
                    'tags': article_file.process_tags(),
                }
                print(errors)
        """
        try:
            self._catch_errors = True
            yield self._errors
        finally:
            self._catch_errors = False
            self._errors = set()

    async def load(self) -> Any:
        """Read and prepare for parsing the source file located at :attr:`path`.

        :raise website.exceptions.FileLoadingError:
            when something wrong happens while reading the source file
            (e.g., file not found or unsupported format).
        """
        if not self._source:
            try:
                async with self.reader(self.path) as source_file:
                    content = await source_file.read()
            except (OSError, UnicodeDecodeError) as exc:
                raise exceptions.FileLoadingError(self, exc)

            self._source = self.parser(content)

        return self._source
