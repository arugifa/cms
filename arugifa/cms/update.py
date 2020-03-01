"""Entry point to manage all content of my website.

Mainly base classes to be inherited by website's components.
"""

import itertools
import re
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path, PurePath
from typing import TextIO, Tuple

from arugifa.cli.update import BaseUpdateRunner, Prompt

from arugifa.cms import exceptions
from arugifa.cms.base.database import BaseTransaction
from arugifa.cms.base.handlers import BaseFileHandler
from arugifa.cms.exceptions import (
    DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidSourceFile)
from arugifa.cms.git import GitRepository
from arugifa.cms.typing import (
    Content, ContentDeletionResult, ContentHandlers, ContentOperationErrors,
    ContentOperationResult, ContentUpdateErrors, ContentUpdatePlan,
    ContentUpdatePlanErrors, ContentUpdateResult, SourceFilePath)


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

    def __init__(
            self,
            repository: GitRepository, handlers: ContentHandlers, db: BaseTransaction):

        self.repository = repository
        self.handlers = handlers
        self.db = db

    # Main API

    @contextmanager
    def load_changes(
            self, since: str, *, output: TextIO = sys.stdout) -> 'ContentUpdateRunner':
        # Get new DB session.
        try:
            yield ContentUpdateRunner(self, since, output=output)
        except exceptions.UpdateFailed:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    async def add(self, src: Path) -> Content:
        """Manually insert specific new documents into database.

        :param new:
            paths of documents source files.

        :raise website.exceptions.ItemAlreadyExisting:
            if a document already exists in database.
        :raise website.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise website.exceptions.InvalidDocumentLocation:
            when a source file is stored in a wrong directory.

        :return:
            newly created documents.
        """
        # Can raise DatabaseError, FileNotVersioned, HandlerNotFound, InvalidSourceFile.
        return await self.get_handler(src).insert()

    async def modify(self, src: Path) -> Content:
        """Manually update specific existing documents in database.

        :param existing:
            paths of documents source files.

        :raise website.exceptions.ItemNotFound:
            if a document doesn't exist in database.
        :raise website.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise website.exceptions.InvalidDocumentLocation:
            when a source file is stored in a wrong directory.

        :return:
            updated documents.
        """
        # Can raise DatabaseError, FileNotVersioned, HandlerNotFound, InvalidSourceFile.
        return await self.get_handler(src).update()

    async def rename(self, src: PurePath, dst: Path) -> Content:
        """Manually rename and update specific existing documents in database.

        :param existing:
            previous and new paths of documents source files.

        :raise website.exceptions.ItemNotFound:
            if a document doesn't exist in database.
        :raise website.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise website.exceptions.DifferentFilesLocation:
            when a source file is stored in a wrong directory.

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

        # Can raise DatabaseError, InvalidSourceFile.
        await src_handler.rename(dst)
        return await dst_handler.update()

    async def delete(self, src: PurePath) -> None:
        """Manually delete specific documents from database.

        :param removed:
            paths of deleted documents source files.

        :raise website.exceptions.ItemNotFound:
            if a document doesn't exist in database.
        :raise website.exceptions.HandlerNotFound:
            if a document doesn't have any handler defined in :attr:`handlers`.
        :raise website.exceptions.InvalidDocumentLocation:
            when a source file is stored in a wrong directory.
        """
        # Can raise DatabaseError, FileNotVersioned, HandlerNotFound, InvalidSourceFile.
        return await self.get_handler(src).delete()

    # Helpers

    def get_handler(self, source_file: SourceFilePath) -> BaseFileHandler:
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
            prompt: Prompt = None, output: TextIO = sys.stdout):

        self.commit = commit
        BaseUpdateRunner.__init__(self, manager, prompt=prompt, output=output)

    @property
    def preview(self) -> str:
        # template = 'updates/content/preview.txt'
        # return render_template(template, changes=changes)
        output = StringIO()

        for action, files in self.todo:
            if files:
                print(f"The following files have been {action}:", file=output)

                for f in files:
                    if isinstance(f, tuple):
                        # - src_file -> dst_file
                        print("- ", end="", file=output)
                        print(*f, sep=" -> ", file=output)
                    else:
                        print(f"- {f}", file=output)

        return output.getvalue()

    @property
    def report(self) -> str:
        template = 'updates/content/report.txt'
        return render_template(template, result=self.result, errors=self.errors)

    async def _plan(self) -> Tuple[ContentUpdatePlan, ContentUpdatePlanErrors]:
        try:
            return self.manager.repository.diff(self.commit), []
        except exceptions.GitError as exc:
            return None, [exc]

    async def _run(self) -> Tuple[ContentUpdateResult, ContentUpdateErrors]:
        """
        :raise website.exceptions.ItemAlreadyExisting:
            when trying to create documents already existing in database.
        :raise website.exceptions.ItemNotFound:
            when trying to modify documents not existing in database.
        :raise website.exceptions.InvalidDocumentLocation:
            when a source file is stored in a wrong directory.
        """
        result = {}
        errors = {}

        document_count = len(itertools.chain(self.todo.values()))

        with self.progress_bar(total=document_count):
            result['added'], errors['added'] = await self.add_content()
            result['modified'], errors['modified'] = await self.replace_content()
            result['renamed'], errors['renamed'] = await self.rename_content()
            result['deleted'], errors['deleted'] = await self.delete_content()

        return result, errors

    async def add_content(self) -> Tuple[ContentOperationResult, ContentOperationErrors]:  # noqa: E501
        result = {}
        errors = {}

        for src in self.todo['added']:
            self.progress.set_description(f"Adding {src}")

            try:
                result[src] = await self.manager.add(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def replace_content(self) -> Tuple[ContentOperationResult, ContentOperationErrors]:  # noqa: E501
        result = {}
        errors = {}

        for src in self.todo['replaced']:
            self.progress.set_description(f"Replacing {src}")

            try:
                result[src] = await self.manager.replace(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def rename_content(self) -> Tuple[ContentOperationResult, ContentOperationErrors]:  # noqa: E501
        result = {}
        errors = {}

        for src, dst in self.todo['renamed']:
            self.progress.set_description(f"Renaming {src}")

            try:
                result[src] = await self.manager.rename(src, dst)
            except (DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidSourceFile) as exc:  # noqa: E501
                errors[src] = exc

            self.progress.update(1)

        return result, errors

    async def delete_content(self) -> Tuple[ContentDeletionResult, ContentOperationErrors]:  # noqa: E501
        result = []
        errors = {}

        for src in self.todo['deleted']:
            self.progress.set_description(f"Deleting {src}")

            try:
                self.manager.delete(src)
                result.append(src)
            except (DatabaseError, HandlerNotFound, InvalidSourceFile) as exc:
                errors[src] = exc

        return result, errors
