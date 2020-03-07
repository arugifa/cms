import jinja2

from arugifa.cli.update.base import BaseUpdatePlanFailure, BaseUpdateRunFailure

templates = jinja2.Environment(loader=jinja2.PackageLoader('arugifa.cms', 'templates'))


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
    pass


class HandlerChangeForbidden(ContentError):
    pass


class FileAlreadyAdded(ContentError):
    pass


class FileNotAddedYet(ContentError):
    pass


class FileLoadingError(ContentError):
    """Error happening when loading (i.e., reading and parsing) a source file."""


class InvalidSourceFile(ContentError):
    pass


class FileProcessingError(ContentError):
    pass


class SourceParsingError(ContentError):
    """When errors raise while parsing a document."""


# Database Update

class ContentUpdatePlanFailure(BaseUpdatePlanFailure):
    def __str__(self):
        template = templates.get_template('preview/failure.txt')
        return template.render(errors=self.errors)


class ContentUpdateRunFailure(BaseUpdateRunFailure):
    def __str__(self):
        template = templates.get_template('report/failure.txt')
        return template.render(errors=self.errors)
