from typing import Iterable

from arugifa.toolbox.update.base import BaseUpdatePlanFailure, BaseUpdateRunFailure

from arugifa.cms import templates


class CMSError(Exception):
    pass


# Git

class GitError(CMSError):
    pass


class GitRepositoryNotFound(GitError):
    """If a directory doesn't contain any Git repository."""


class GitCLIError(GitError):
    pass


class GitUnknownCommit(GitError):
    pass


# Database

class DatabaseError(CMSError):
    """Errors related to the database."""


# Source File Processing

class ContentError(CMSError):
    pass


class FileNotVersioned(ContentError):
    pass


class DupplicatedContent(ContentError):
    pass


class HandlerNotFound(ContentError):

    def __eq__(self, other):
        return self.__class__ == other.__class__

    def __str__(self):
        return "No handler configured"


# TODO: Rename to HandlerChangeNotPermitted? (04/2020)
class HandlerChangeForbidden(ContentError):
    # TODO: Remove exception arguments (05/2020)
    def __init__(self, original: 'BaseFileHandler' = None, new: 'BaseFileHandler' = None):  # noqa: E501
        self.original = original
        self.new = new

    def __eq__(self, other):
        return (self.original == other.original) and (self.new == other.new)

    def __str__(self):
        original = self.original.__class__.__name__
        new = self.new.__class__.__name__

        return (
            f"Cannot use {new} insted of {original} to handle file. "
            f"You must keep using the same handler"
        )


class FileAlreadyAdded(ContentError):
    pass


class FileNotAddedYet(ContentError):
    pass


class FileLoadingError(ContentError):
    """Error happening when loading (i.e., reading and parsing) a source file."""


class FileProcessingError(ContentError):
    pass


class FilePathScanningError(FileProcessingError):
    pass


class SourceParsingError(FileProcessingError):
    """When errors raise while parsing a document."""


class SourceMalformatted(SourceParsingError):
    pass


class InvalidFile(ContentError):
    def __init__(self, errors: Iterable[FileProcessingError]):
        self.errors = errors

    def __eq__(self, other):
        return self.errors == other.errors


# Database Update

class ContentUpdatePlanFailure(BaseUpdatePlanFailure):
    def __str__(self):
        template = templates.get_template('preview/failure.txt')
        return template.render(errors=self.errors)


class ContentUpdateRunFailure(BaseUpdateRunFailure):
    def __str__(self):
        template = templates.get_template('report/failure.txt')
        return template.render(errors=self.errors)
