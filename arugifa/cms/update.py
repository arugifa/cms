"""Entry point to manage all content of my website.

Mainly base classes to be inherited by website's components.
"""

import re
from collections import OrderedDict
from contextlib import contextmanager
from itertools import chain
from pathlib import Path, PurePath
from typing import Iterable, Tuple, Union

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

    async def add(self, content: Iterable[Path]) -> UpdateStep:
        """:raise UpdateNotPlanned: ..."""
        step = UpdateStep(result={}, errors={})

        for src in content:
            self.progress.set_description(f"Adding {src}")

            try:
                handler = self.get_handler(src)
                step.result[src] = await handler.insert()
            except (DatabaseError, HandlerNotFound, InvalidFile) as exc:
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def modify(self, content: Iterable[Path]) -> UpdateStep:
        step = UpdateStep(result={}, errors={})

        for src in content:
            self.progress.set_description(f"Modifying {src}")

            try:
                handler = self.get_handler(src)
                step.result[src] = await handler.update()
            except (DatabaseError, HandlerNotFound, InvalidFile) as exc:
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def rename(self, content: Iterable[Tuple[PurePath, Path]]) -> UpdateStep:
        step = UpdateStep(result={}, errors={})

        for src, dst in content:
            self.progress.set_description(f"Renaming {src}")

            try:
                src_handler = self.get_handler(src)
                dst_handler = self.get_handler(dst)

                if src_handler.__class__ is not dst_handler.__class__:
                    step.errors[src] = HandlerChangeForbidden(src, dst)
                else:
                    # Can raise DatabaseError, FileNotAddedYet, InvalidFile.
                    await src_handler.rename(dst)
                    step.result[src] = await dst_handler.update()
            except (DatabaseError, HandlerChangeForbidden, HandlerNotFound, InvalidFile) as exc:  # noqa: E501
                step.errors[src] = exc

            self.progress.update(1)

        return step

    async def delete(self, content: Iterable[PurePath]) -> UpdateStep:
        step = UpdateStep(result=[], errors={})

        for src in content:
            self.progress.set_description(f"Deleting {src}")

            try:
                handler = self.get_handler(src)
                await handler.delete()
            except (DatabaseError, HandlerNotFound, InvalidFile) as exc:
                step.errors[src] = exc
            else:
                step.result.append(src)

        return step

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

        for glob_pattern, handler in self.manager.handlers.items():
            # Replace sub-directory wildcards:
            # <DIR>/**/*.<EXTENSION> -> <DIR>/.+/*.<EXTENSION>
            regex = re.sub(r'\*\*', r'.+', glob_pattern)

            # Replace file name wildcards:
            # <DIR>/**/*.<EXTENSION> -> <DIR>/**/.+\.<EXTENSION>
            regex = regex = re.sub(r'\*\.(.+)', r'.+\.\1', regex)

            if re.match(regex, str(relative_path)):
                return handler(self.manager.repository.path / relative_path)
        else:
            raise HandlerNotFound


class ContentUpdateRunner(BaseUpdateRunner):

    def __init__(self, manager: ContentManager, commit: str, **kwargs):
        self.commit = commit
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
        todo, errors = self.sort_todo()

        if any(errors):
            raise exceptions.ContentUpdateRunFailure(errors)

        result = {}
        count = sum(1 for _ in chain(*todo.values()))

        with self.progress_bar(total=count):
            # Can raise UpdateNotPlanned:
            result['added'], errors['added'] = await self.manager.add(todo['to_add'])
            result['modified'], errors['modified'] = await self.manager.modify(todo['to_modify'])  # noqa: E501
            result['renamed'], errors['renamed'] = await self.manager.rename(todo['to_rename'])  # noqa: E501
            result['deleted'], errors['deleted'] = await self.manager.delete(todo['to_delete'])  # noqa: E501

        if any(errors.values()):
            all_errors = {
                **errors['added'], **errors['modified'],
                **errors['renamed'], **errors['deleted'],
            }
            raise exceptions.ContentUpdateRunFailure(all_errors)

        return result

    # Helpers

    def sort_todo(self) -> UpdateStep:
        step = UpdateStep(result={}, errors={})

        def get_handler(action, result, source_file):
            try:
                handler = self.manager.get_handler(source_file)
                result[handler].append(source_file)
            except HandlerNotFound:
                step.errors[source_file] = HandlerNotFound
            except AttributeError:
                result[handler] = [source_file]

        for action, files in self.todo.items():
            result = OrderedDict.fromkeys(self.manager.handlers.values())

            for source_file in files:
                if isinstance(source_file, tuple):
                    get_handler(action, result, source_file[0])
                    get_handler(action, result, source_file[1])
                else:
                    get_handler(action, result, source_file)

            step.result[action] = list(chain(*result.values()))

        return step
