from itertools import chain
from pathlib import Path, PurePath
from random import random
from textwrap import dedent

import pytest
from arugifa.toolbox.test.helpers import this_string

from arugifa.cms import exceptions
from arugifa.cms.base.handlers import BaseFileHandler
from arugifa.cms.base.processors import BaseFileProcessor
from arugifa.cms.exceptions import HandlerChangeForbidden
from arugifa.cms.update import ContentManager, ContentUpdateRunner


# Fixtures

class DummyProcessor(BaseFileProcessor):
    pass


class DummyHandler(BaseFileHandler):
    model = None
    processor = DummyProcessor

    async def insert(self):
        return self.source_file.path.name

    async def update(self):
        return self.source_file.path.name

    async def rename(self, target):
        pass

    async def delete(self):
        return self.source_file.path.name


class AnotherDummyHandler(DummyHandler):
    pass


@pytest.fixture(scope='module')
def handlers():
    return {'*.txt': DummyHandler, '*.html': AnotherDummyHandler}


@pytest.fixture(scope='module')
def repository(git, tmp_path_factory):
    tmpdir = tmp_path_factory.mktemp(__name__)

    # Initialize repository.
    repo = git.init(tmpdir)

    to_rename = [
        repo.path / 'to_rename.html',
        repo.path / 'to_rename.txt',
    ]

    to_modify = [
        repo.path / 'modified.html',
        repo.path / 'modified.txt',
    ]

    to_delete = [
        repo.path / 'deleted.html',
        repo.path / 'deleted.txt',
    ]

    for source_file in chain(to_rename, to_modify, to_delete):
        source_file.write_text(f"{random()}")

    repo.add(*to_rename, *to_modify, *to_delete)
    repo.commit('HEAD~4')

    # Add files.
    added = [
        repo.path / 'added.html',
        repo.path / 'added.txt',
    ]

    for source_file in added:
        source_file.write_text(f"{random()}")

    repo.add(*added)
    repo.commit('HEAD~3')

    # Rename files.
    repo.move(to_rename[0], 'renamed.html')
    repo.move(to_rename[1], 'renamed.txt')
    repo.commit('HEAD~2')

    # Modify files.
    with to_modify[0].open('a') as f1, to_modify[1].open('a') as f2:
        f1.write('modification')
        f2.write('modification')

    repo.add(*to_modify)
    repo.commit('HEAD~1')

    # Delete files.
    repo.remove(*to_delete)
    repo.commit('HEAD')

    return repo


@pytest.fixture(scope='module')
def diff(repository):
    return repository.diff('HEAD~4')


@pytest.fixture(scope='module')
def content(handlers, repository):
    return ContentManager(repository, handlers)


# Tests

class TestContentManager:

    # Load changes.

    async def test_load_changes(self, content):
        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()
            actual = await update.run()

        expected = {
            'added': {
                Path('added.html'): 'added.html',
                Path('added.txt'): 'added.txt',
            },
            'modified': {
                Path('modified.html'): 'modified.html',
                Path('modified.txt'): 'modified.txt',
            },
            'renamed': {
                Path('to_rename.html'): 'renamed.html',
                Path('to_rename.txt'): 'renamed.txt',
            },
            'deleted': [
                Path('deleted.html'),
                Path('deleted.txt'),
            ],
        }
        assert actual == expected

    # Add source file.

    async def test_add_source_file(self, content):
        source_file = Path('add.txt')
        assert await content.add(source_file) == 'add.txt'

    async def test_add_source_file_with_missing_handler(self, content):
        source_file = Path('handler.md')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.add(source_file)

    async def test_add_source_file_not_versioned(self, content):
        source_file = Path('/tmp/add.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.add(source_file)

    # Modify source file.

    async def test_modify_source_file(self, content):
        source_file = Path('modify.txt')
        assert await content.modify(source_file) == 'modify.txt'

    async def test_modify_source_file_with_missing_handler(self, content):
        source_file = Path('handler.md')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.modify(source_file)

    async def test_modify_source_file_not_versioned(self, content):
        source_file = Path('/tmp/modify.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.modify(source_file)

    # Rename source file.

    async def test_rename_source_file(self, content):
        src = PurePath('src.txt')
        dst = Path('dst.txt')
        assert await content.rename(src, dst) == 'dst.txt'

    async def test_rename_source_file_with_missing_handler(self, content):
        src = PurePath('src.md')
        dst = Path('dst.md')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.rename(src, dst)

    async def test_rename_source_file_not_versioned(self, content):
        src = PurePath('/tmp/src.txt')
        dst = Path('/tmp/dst.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.rename(src, dst)

    async def test_rename_source_file_with_different_handler(self, content):
        src = PurePath('src.txt')
        dst = Path('dst.html')

        with pytest.raises(exceptions.HandlerChangeForbidden):
            await content.rename(src, dst)

    # Delete source file.

    async def test_delete_source_file(self, content):
        source_file = PurePath('delete.txt')
        assert await content.delete(source_file) == 'delete.txt'

    async def test_delete_source_file_with_missing_handler(self, content):
        source_file = Path('handler.md')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.delete(source_file)

    async def test_delete_source_file_not_versioned(self, content):
        source_file = Path('/tmp/modify.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.delete(source_file)

    # Get handler.

    def test_get_handler_with_absolute_path(self, content):
        source_file = content.repository.path / 'handler.txt'
        handler = content.get_handler(source_file)
        assert isinstance(handler, content.handlers['*.txt'])

    def test_get_handler_with_relative_path(self, content):
        source_file = PurePath('handler.txt')
        handler = content.get_handler(source_file)
        assert isinstance(handler, content.handlers['*.txt'])

    def test_get_missing_handler(self, content):
        source_file = PurePath('handler.md')

        with pytest.raises(exceptions.HandlerNotFound):
            content.get_handler(source_file)

    def test_get_not_versioned_file_handler(self, content):
        source = PurePath('/tmp/not_versioned.html')

        with pytest.raises(exceptions.FileNotVersioned):
            content.get_handler(source)


class TestContentUpdateRunner:
    # Planify update.

    async def test_plan_update(self, content, diff):
        with content.load_changes('HEAD~4') as update:
            actual = await update.plan()

        expected = {
            'to_add': diff['added'],
            'to_modify': diff['modified'],
            'to_rename': diff['renamed'],
            'to_delete': diff['deleted'],
        }

        assert actual == expected

    async def test_preview(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()

        preview = dedent("""
            files added to database:
            added.html
            added.txt
            files renamed in database:
            to_rename.html -> renamed.html
            to_rename.txt -> renamed.txt
            files modified in database:
            modified.html
            modified.txt
            files deleted from database:
            deleted.html
            deleted.txt
        """)

        assert this_string(update.preview, contains=preview)

    async def test_git_error_during_planning(self, content):
        with content.load_changes('INVALID_COMMIT') as update:
            with pytest.raises(exceptions.ContentUpdatePlanFailure) as excinfo:
                await update.plan()

        report = "'INVALID_COMMIT' did not resolve"
        assert this_string(str(excinfo.value), contains=report)

    # Run update.

    async def test_run_update(self, content):
        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()
            actual = await update.run()

        expected = {
            'added': {
                Path('added.html'): 'added.html',
                Path('added.txt'): 'added.txt',
            },
            'modified': {
                Path('modified.html'): 'modified.html',
                Path('modified.txt'): 'modified.txt',
            },
            'renamed': {
                PurePath('to_rename.html'): 'renamed.html',
                PurePath('to_rename.txt'): 'renamed.txt',
            },
            'deleted': [
                PurePath('deleted.html'),
                PurePath('deleted.txt'),
            ],
        }

        assert actual == expected

    async def test_errors_during_update_run(self, diff, repository):
        content = ContentManager(repository, {})  # No handlers

        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()

            with pytest.raises(exceptions.ContentUpdateRunFailure) as excinfo:
                await update.run()

        report = dedent("""
            errors processing source files:
            added.html: no handler
            added.txt: no handler
            modified.html: no handler
            modified.txt: no handler
            to_rename.html: no handler
            to_rename.txt: no handler
            deleted.html: no handler
            deleted.txt: no handler
        """)

        assert this_string(str(excinfo.value), contains=report)

    async def test_report(self, content):
        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()
            await update.run()

        assert 'added.html' in update.report
        assert 'added.txt' in update.report

        assert 'modified.html' in update.report
        assert 'modified.txt' in update.report

        assert 'to_rename.html' in update.report
        assert 'to_rename.txt' in update.report

        assert 'deleted.html' in update.report
        assert 'deleted.txt' in update.report

    # Add content.

    async def test_add_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.add_content()

        expected = {
            Path('added.html'): 'added.html',
            Path('added.txt'): 'added.txt',
        }

        assert (actual, errors) == (expected, {})

    # Modify content.

    async def test_modify_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.modify_content()

        expected = {
            Path('modified.html'): 'modified.html',
            Path('modified.txt'): 'modified.txt',
        }

        assert (actual, errors) == (expected, {})

    # Rename content.

    async def test_rename_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.rename_content()

        expected = {
            PurePath('to_rename.html'): 'renamed.html',
            PurePath('to_rename.txt'): 'renamed.txt',
        }

        assert (actual, errors) == (expected, {})

    async def test_handler_change_errors_are_caught(self, git, handlers, tmp_path):
        # Fixtures
        repo = git.init(tmp_path)

        to_rename = [
            repo.path / 'to_rename.html',
            repo.path / 'to_rename.txt',
        ]

        for source_file in to_rename:
            source_file.write_text(f"{random()}")

        repo.add(*to_rename)
        repo.commit('HEAD~1')

        repo.move(to_rename[0], 'renamed.txt')
        repo.move(to_rename[1], 'renamed.html')
        repo.commit('HEAD')

        content = ContentManager(repo, handlers)

        # Test
        with content.load_changes('HEAD~1') as update:
            await update.plan()
            result, actual = await update.rename_content()

        # Assertions
        expected = {
            PurePath('to_rename.html'): HandlerChangeForbidden(AnotherDummyHandler, DummyHandler),  # noqa: E501
            PurePath('to_rename.txt'): HandlerChangeForbidden(DummyHandler, AnotherDummyHandler),  # noqa: E501
        }

        assert len(result) == 0
        assert actual == expected

    # Delete content.

    async def test_delete_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.delete_content()

        expected = [
            PurePath('deleted.html'),
            PurePath('deleted.txt'),
        ]

        assert (actual, errors) == (expected, {})

    # Add/modify/rename/delete content.

    @pytest.mark.parametrize('method, path', [
        (ContentUpdateRunner.add_content, Path('added')),
        (ContentUpdateRunner.modify_content, Path('modified')),
        (ContentUpdateRunner.rename_content, PurePath('to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('deleted')),
    ])
    async def test_database_errors_are_caught(self, method, path, repository):
        # Fixtures
        exc = exceptions.DatabaseError(Exception("Database offline"))

        class BrokenHandler(BaseFileHandler):
            processor = DummyProcessor

            async def insert(self):
                raise exc

            async def update(self):
                raise exc

            async def rename(self, target):
                raise exc

            async def delete(self):
                raise exc

        handlers = {'*.*': BrokenHandler}
        content = ContentManager(repository, handlers)

        # Test
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            result, actual = await method(update)

        # Assertions
        expected = {
            path.with_suffix('.html'): exc,
            path.with_suffix('.txt'): exc,
        }

        assert len(result) == 0
        assert actual == expected

    @pytest.mark.parametrize('method, path', [
        (ContentUpdateRunner.add_content, Path('added')),
        (ContentUpdateRunner.modify_content, Path('modified')),
        (ContentUpdateRunner.rename_content, PurePath('to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('deleted')),
    ])
    async def test_handler_not_found_errors_are_caught(self, method, path, repository):
        # Fixtures
        content = ContentManager(repository, {})  # No handlers

        # Test
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            result, actual = await method(update)

        # Assertions
        expected = {
            path.with_suffix('.html'): exceptions.HandlerNotFound(),
            path.with_suffix('.txt'): exceptions.HandlerNotFound(),
        }

        assert len(result) == 0
        assert actual == expected

    @pytest.mark.parametrize('method, path', [
        (ContentUpdateRunner.add_content, Path('added')),
        (ContentUpdateRunner.modify_content, Path('modified')),
        (ContentUpdateRunner.rename_content, PurePath('to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('deleted')),
    ])
    async def test_invalid_file_errors_are_caught(self, method, path, repository):
        # Fixtures
        exc = exceptions.InvalidFile([exceptions.FilePathScanningError("Invalid name")])

        class BrokenHandler(BaseFileHandler):
            processor = DummyProcessor

            async def insert(self):
                raise exc

            async def update(self):
                raise exc

            async def rename(self, target):
                raise exc

            async def delete(self):
                raise exc

        handlers = {'*.*': BrokenHandler}
        content = ContentManager(repository, handlers)

        # Test
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            result, actual = await method(update)

        # Assertions
        expected = {
            path.with_suffix('.html'): exc,
            path.with_suffix('.txt'): exc,
        }

        assert len(result) == 0
        assert actual == expected
