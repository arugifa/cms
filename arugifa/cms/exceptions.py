from pathlib import Path, PurePath
from typing import Iterable, Union

from arugifa.toolbox.update.base import BaseUpdatePlanFailure, BaseUpdateRunFailure

from arugifa.cms import templates


class CMSError(Exception):
    pass


# Git

class GitError(CMSError):
    pass


class RepositoryNotFound(GitError):
    """If a directory doesn't contain any Git repository."""


# Database

class DatabaseError(CMSError):
    """Errors related to the database."""


# Source File Processing

class ContentError(CMSError):
    pass


class FileNotVersioned(ContentError):
    pass


class HandlerNotFound(ContentError):
    def __init__(self, path: Union[PurePath, Path]):
        self.path = path

    def __eq__(self, other):
        return self.path == other.path

    def __str__(self):
        return "No handler configured"


class HandlerChangeForbidden(ContentError):
    pass


class FileAlreadyAdded(ContentError):
    pass


class FileNotAddedYet(ContentError):
    pass


class FileLoadingError(ContentError):
    """Error happening when loading (i.e., reading and parsing) a source file."""


class FileProcessingError(ContentError):
    pass


class SourceParsingError(ContentError):
    """When errors raise while parsing a document."""


class InvalidFile(ContentError):
    def __init__(self, path: Path, errors: Iterable[Union[FileProcessingError, SourceParsingError]]):  # noqa: E501
        self.path = path
        self.errors = errors

    def __eq__(self, other):
        return (self.path == other.path) and (self.errors == other.errors)


# Database Update

class ContentUpdatePlanFailure(BaseUpdatePlanFailure):
    def __str__(self):
        template = templates.get_template('preview/failure.txt')
        return template.render(errors=self.errors)


class ContentUpdateRunFailure(BaseUpdateRunFailure):
    def __str__(self):
        template = templates.get_template('report/failure.txt')
        return template.render(errors=self.errors)
