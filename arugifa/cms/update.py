"""Entry point to manage all content of my website.

Mainly base classes to be inherited by website's components.
"""

import re
from collections import OrderedDict
from contextlib import contextmanager
from functools import partial
from itertools import chain
from pathlib import Path, PurePath
from typing import Union

from arugifa.cms import exceptions, templates
from arugifa.cms.exceptions import (
    DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidFile)
from arugifa.cms.git import GitRepository
from arugifa.cms.handlers import BaseFileHandler
from arugifa.cms.typing import ContentHandlers, ContentUpdateResult, ContentUpdateTodo
from arugifa.toolbox.update import UpdateStep
from arugifa.toolbox.update.base import BaseUpdateRunner


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
    def load_changes(self, since: str, **kwargs) -> 'ContentUpdateRunner':
        yield ContentUpdateRunner(self, since, **kwargs)

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
                return handler(self.repository.path / relative_path)
        else:
            raise HandlerNotFound


class ContentUpdateRunner(BaseUpdateRunner):

    def __init__(self, manager: ContentManager, commit: str, **kwargs):
        self.commit = commit
        self._sorted_todo = None
        BaseUpdateRunner.__init__(self, manager, **kwargs)

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
        """
        :raise ContentUpdateRunFailure: ...
        :raise UpdateNotPlanned: ...
        """
        todo, missing_handlers = self.sort_todo()  # Can raise UpdateNotPlanned

        if any(missing_handlers):
            raise exceptions.ContentUpdateRunFailure(missing_handlers)

        result, errors = ({}, {})
        count = sum(1 for _ in chain(*todo.values()))

        with self.progress_bar(total=count):
            result['added'], errors['added'] = await self.add_content()
            result['modified'], errors['modified'] = await self.modify_content()
            result['renamed'], errors['renamed'] = await self.rename_content()
            result['deleted'], errors['deleted'] = await self.delete_content()

        if any(errors.values()):
            all_errors = {
                **errors['added'], **errors['modified'],
                **errors['renamed'], **errors['deleted'],
            }
            raise exceptions.ContentUpdateRunFailure(all_errors)

        return result

    # Helpers

    async def add_content(self) -> UpdateStep:
        """:raise UpdateNotPlanned: ..."""
        handlers, errors = self.sort_todo()  # Can raise UpdateNotPlanned
        step = UpdateStep(result={}, errors=errors)

        for handler in handlers['to_add']:
            src = handler.source_file.path.relative_to(self.manager.repository.path)
            self.progress.set_description(f"Adding {src}")

            try:
                step.result[src] = await handler.insert()
            except (DatabaseError, InvalidFile) as exc:
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def modify_content(self) -> UpdateStep:
        handlers, errors = self.sort_todo()  # Can raise UpdateNotPlanned
        step = UpdateStep(result={}, errors=errors)

        for handler in handlers['to_modify']:
            src = handler.source_file.path.relative_to(self.manager.repository.path)
            self.progress.set_description(f"Modifying {src}")

            try:
                step.result[src] = await handler.update()
            except (DatabaseError, InvalidFile) as exc:
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def rename_content(self) -> UpdateStep:  # noqa: E501
        handlers, errors = self.sort_todo()  # Can raise UpdateNotPlanned
        step = UpdateStep(result={}, errors=errors)

        for src_handler, dst_handler in handlers['to_rename']:
            src = src_handler.source_file.path.relative_to(self.manager.repository.path)  # noqa: E501
            dst = dst_handler.source_file.path.relative_to(self.manager.repository.path)  # noqa: E501
            self.progress.set_description(f"Renaming {src}")

            try:
                if src_handler.__class__ is not dst_handler.__class__:
                    step.errors[src] = HandlerChangeForbidden
                else:
                    # Can raise DatabaseError, FileNotAddedYet, InvalidFile.
                    await src_handler.rename(dst)
                    step.result[src] = await dst_handler.update()
            except (DatabaseError, InvalidFile) as exc:
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def delete_content(self) -> UpdateStep:
        handlers, errors = self.sort_todo()  # Can raise UpdateNotPlanned
        step = UpdateStep(result={}, errors=errors)

        # Can raise UpdateNotPlanned
        for handler in handlers['to_delete']:
            src = handler.source_file.path.relative_to(self.manager.repository.path)
            self.progress.set_description(f"Deleting {src}")

            try:
                await handler.delete()
            except (DatabaseError, InvalidFile) as exc:
                step.errors[src] = exc
            else:
                step.result.append(src)

        return step

    # TODO: Add tests (05/2020)
    def sort_todo(self) -> UpdateStep:
        if not self._sorted_todo:
            step = UpdateStep(result={}, errors={})

            def get_handler(handlers, source_file):
                try:
                    return self.manager.get_handler(source_file)
                except HandlerNotFound:
                    step.errors[source_file] = HandlerNotFound

            for action, files in self.todo.items():
                handlers = OrderedDict()

                for handler in self.manager.handlers.values():
                    if isinstance(handler, partial):
                        handlers[handler.func] = []
                    else:
                        handlers[handler] = []

                for source_file in files:
                    if isinstance(source_file, tuple):
                        src_handler = get_handler(handlers, source_file[0])
                        dst_handler = get_handler(handlers, source_file[1])
                        handlers[dst_handler.__class__].append((src_handler, dst_handler))  # noqa: E501
                    else:
                        handler = get_handler(handlers, source_file)
                        handlers[handler.__class__].append(handler)

                step.result[action] = list(chain(*handlers.values()))

            self._sorted_todo = step

        return self._sorted_todo

