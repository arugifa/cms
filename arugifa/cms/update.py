"""Entry point to manage all content of my website.

Mainly base classes to be inherited by website's components.
"""

import re
import sys
from contextlib import contextmanager
from itertools import chain
from pathlib import Path, PurePath
from typing import TextIO, Tuple, Union

import jinja2
from arugifa.cli.update.base import BaseUpdateRunner
from arugifa.cli.update.input import Prompt

from arugifa.cms import exceptions
from arugifa.cms.base.handlers import BaseFileHandler
from arugifa.cms.exceptions import (
    DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidSourceFile)
from arugifa.cms.git import GitRepository
from arugifa.cms.typing import (
    ContentAdditionErrors, ContentAdditionResult, ContentDeletionErrors,
    ContentDeletionResult, ContentHandlers, ContentModificationErrors,
    ContentModificationResult, ContentRenamingErrors, ContentRenamingResult,
    ContentUpdateResult, ContentUpdateTodo, DatabaseItem)

templates = jinja2.Environment(loader=jinja2.PackageLoader('arugifa.cms', 'templates'))


class ContentManager:
    """Manage website's content life cycle.

    The content is organized as a set of categorized documents. For example::

        blog/
            2019/
                01-31. first_article_of_the_year.adoc
                12-31. last_article_of_the_year.adoc

    As part of website's content update, every document is loaded, processed,
    and finally stored, updated or deleted in the database.

    :param repository:
        path of the Git repository where website's content is stored.
    """

    def __init__(self, repository: GitRepository, handlers: ContentHandlers):
        self.repository = repository
        self.handlers = handlers

    # Main API

    @contextmanager
    def load_changes(
            self, since: str, *,
            output: TextIO = sys.stdout, show_progress: bool = True) -> 'ContentUpdateRunner':  # noqa; E501
        yield ContentUpdateRunner(self, since, output=output, show_progress=show_progress)  # noqa: E501

    async def add(self, src: Path) -> DatabaseItem:
        """Manually insert specific new documents into database.

        :param new:
            paths of documents source files.

        :raise arugifa.cms.exceptions.DatabaseError:
            XXX
        :raise arugifa.cms.exceptions.FileAlreadyAdded:
            XXX
        :raise arugifa.cms.exceptions.FileNotVersioned:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise arugifa.cms.exceptions.InvalidFile:
            XXX

        :return:
            newly created documents.
        """
        return await self.get_handler(src).insert()

    async def modify(self, src: Path) -> DatabaseItem:
        """Manually update specific existing documents in database.

        :param existing:
            paths of documents source files.

        :raise arugifa.cms.exceptions.DatabaseError:
            XXX
        :raise arugifa.cms.exceptions.FileNotAddedYet:
            XXX
        :raise arugifa.cms.exceptions.FileNotVersioned:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise arugifa.cms.exceptions.InvalidFile:
            XXX

        :return:
            updated documents.
        """
        return await self.get_handler(src).update()

    async def rename(self, src: PurePath, dst: Path) -> DatabaseItem:
        """Manually rename and update specific existing documents in database.

        :param existing:
            previous and new paths of documents source files.

        :raise arugifa.cms.exceptions.DatabaseError:
            XXX
        :raise arugifa.cms.exceptions.FileNotAddedYet:
            XXX
        :raise arugifa.cms.exceptions.FileNotVersioned:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerChangeForbidden:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise arugifa.cms.exceptions.InvalidFile:
            XXX

        :return:
            updated documents.
        """
        # Can raise FileNotVersioned, HandlerNotFound.
        src_handler = self.get_handler(src)
        dst_handler = self.get_handler(dst)

        try:
            assert src_handler.__class__ is dst_handler.__class__
        except (AssertionError, HandlerNotFound):
            raise exceptions.HandlerChangeForbidden(src, dst)

        # Can raise DatabaseError, FileNotAddedYet, InvalidFile.
        await src_handler.rename(dst)
        return await dst_handler.update()

    async def delete(self, src: PurePath) -> None:
        """Manually delete specific documents from database.

        :param removed:
            paths of deleted documents source files.

        :raise arugifa.cms.exceptions.DatabaseError:
            XXX
        :raise arugifa.cms.exceptions.FileNotAddedYet:
            XXX
        :raise arugifa.cms.exceptions.FileNotVersioned:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerChangeForbidden:
            when a source file is stored in a wrong directory.
        :raise arugifa.cms.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise arugifa.cms.exceptions.InvalidFile:
            XXX
        """
        return await self.get_handler(src).delete()

    # Helpers

    def get_handler(self, source_file: Union[Path, PurePath]) -> BaseFileHandler:
        """Return handler to process the source file of a document.

        :param document:
            path of the document's source file.

        :raise website.exceptions.HandlerNotFound:
            if no handler in :attr:`handlers` is defined
            for this type of document.
        :raise website.exceptions.InvalidDocumentLocation:
            when the source file is not located in :attr:`directory`
            or inside a subdirectory.
        """
        if source_file.is_absolute():
            try:
                relative_path = source_file.relative_to(self.repository.path)
            except ValueError:
                raise exceptions.FileNotVersioned(source_file)
        else:
            relative_path = source_file

        for glob_pattern, handler in self.handlers.items():
            # Replace sub-directory wildcards:
            # <DIR>/**/*.<EXTENSION> -> <DIR>/.+/*.<EXTENSION>
            regex = re.sub(r'\*\*', r'.+', glob_pattern)

            # Replace file name wildcards:
            # <DIR>/**/*.<EXTENSION> -> <DIR>/**/.+\.<EXTENSION>
            regex = regex = re.sub(r'\*\.(.+)', r'.+\.\1', regex)

            if re.match(regex, str(relative_path)):
                return handler(source_file)
        else:
            raise HandlerNotFound(source_file)


class ContentUpdateRunner(BaseUpdateRunner):

    def __init__(
            self, manager: ContentManager, commit: str, *,
            prompt: Prompt = None, output: TextIO = sys.stdout,
            show_progress: bool = True):

        self.commit = commit
        BaseUpdateRunner.__init__(
            self, manager,
            prompt=prompt, output=output, show_progress=show_progress)

    @property
    def preview(self) -> str:
        template = templates.get_template('preview/success.txt')
        return template.render(todo=self.todo)

    @property
    def report(self) -> str:
        template = templates.get_template('report/success.txt')
        return template.render(result=self.result)

    async def _plan(self) -> ContentUpdateTodo:
        """:raise ContentUpdatePlanFailure: ..."""
        try:
            diff = self.manager.repository.diff(self.commit)
        except exceptions.GitError as exc:
            errors = {'git_diff': exc}
            raise exceptions.ContentUpdatePlanFailure(errors)

        return {
            'to_add': diff['added'],
            'to_rename': diff['renamed'],
            'to_modify': diff['modified'],
            'to_delete': diff['deleted'],
        }

    async def _run(self) -> ContentUpdateResult:
        """:raise ContentUpdateRunFailure: ..."""
        result = {}
        errors = {}

        document_count = len([chain(self.todo.values())])

        with self.progress_bar(total=document_count):
            result['added'], errors['added'] = await self.add_content()
            result['modified'], errors['modified'] = await self.modify_content()
            result['renamed'], errors['renamed'] = await self.rename_content()
            result['deleted'], errors['deleted'] = await self.delete_content()

        if any(errors.values()):
            raise exceptions.ContentUpdateRunFailure(errors)

        return result

    async def add_content(self) -> Tuple[ContentAdditionResult, ContentAdditionErrors]:
        result = {}
        errors = {}

        for src in self.todo['to_add']:
            self.progress.set_description(f"Adding {src}")

            try:
                result[src] = await self.manager.add(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def modify_content(self) -> Tuple[ContentModificationResult, ContentModificationErrors]:  # noqa: E501
        result = {}
        errors = {}

        for src in self.todo['to_modify']:
            self.progress.set_description(f"Modifying {src}")

            try:
                result[src] = await self.manager.modify(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def rename_content(self) -> Tuple[ContentRenamingResult, ContentRenamingErrors]:  # noqa: E501
        result = {}
        errors = {}

        for src, dst in self.todo['to_rename']:
            self.progress.set_description(f"Renaming {src}")

            try:
                result[src] = await self.manager.rename(src, dst)
            except (DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidSourceFile) as exc:  # noqa: E501
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def delete_content(self) -> Tuple[ContentDeletionResult, ContentDeletionErrors]:  # noqa: E501
        result = []
        errors = {}

        for src in self.todo['to_delete']:
            self.progress.set_description(f"Deleting {src}")

            try:
                self.manager.delete(src)
                result.append(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

        return result, errors
