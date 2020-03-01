from abc import abstractstaticmethod
from contextlib import contextmanager
from typing import Any

from arugifa.cms.typing import SourceParsingErrors


class CatchParserErrors(type):
    """Meta-class used by all document parsers.

    Catch errors automatically when calling parsing methods.

    This allows to process a document all at once, without having to bother with
    multiple try-catch blocks.
    """

    def __new__(meta, classname, supers, classdict):  # noqa: D102, N804

        def catch_errors(func):
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except exceptions.DocumentParsingError as exc:
                    if not self._catch_errors:
                        raise

                    self._errors.add(exc)

            return wrapper

        for attr, attrval in classdict.items():
            if attr.startswith('parse_'):
                classdict[attr] = catch_errors(attrval)

        return type.__new__(meta, classname, supers, classdict)


class BaseSourceParser(metaclass=CatchParserErrors):

    def __init__(self, source: str):
        self._source = self.deserialize(source)

        self._errors = set()  # To store parsing errors

        # To catch potential exceptions when parsing the document's source.
        self._catch_errors = False

    @property
    def source(self):
        """File source. Read only."""
        return self._source

    @abstractstaticmethod
    def deserialize(self) -> Any:
        pass

    @contextmanager
    def collect_errors(self) -> SourceParsingErrors:
        """Catch  and return potential errors when parsing document's source.

        Can be used as follows::

            source_file = BaseDocumentSourceParser(file_path)

            with source_file.collect_errors() as errors:
                source_file.parse_title()
                source_file.parse_category()
                source_file.parse_tags()
                print(errors)
        """
        try:
            self._catch_errors = True
            yield self._errors
        finally:
            self._catch_errors = False
            self._errors = set()
