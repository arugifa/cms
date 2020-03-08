from itertools import chain
from pathlib import Path, PurePath
from random import random

import pytest
from arugifa.toolbox.test import this_string

from arugifa.cms import exceptions
from arugifa.cms.base.handlers import BaseFileHandler
from arugifa.cms.base.processors import BaseFileProcessor
from arugifa.cms.exceptions import HandlerNotFound
from arugifa.cms.update import ContentManager, ContentUpdateRunner


# Fixtures

class DummyProcessor(BaseFileProcessor):
    pass


class DummyHandler(BaseFileHandler):
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
    return {'dummy/*.txt': DummyHandler, 'dummy/*.html': AnotherDummyHandler}


@pytest.fixture(scope='module')
def repository(git, tmp_path_factory):
    tmpdir = tmp_path_factory.mktemp(__name__)
    Path(tmpdir / 'dummy').mkdir()

    # Initialize repository.
    repo = git.init(tmpdir)

    to_rename = [
        repo.path / 'dummy/to_rename.txt',
        repo.path / 'dummy/to_rename.html',
    ]

    to_modify = [
        repo.path / 'dummy/modified.txt',
        repo.path / 'dummy/modified.html',
    ]

    to_delete = [
        repo.path / 'dummy/deleted.txt',
        repo.path / 'dummy/deleted.html',
    ]

    for source_file in chain(to_rename, to_modify, to_delete):
        source_file.write_text(f"{random()}")

    repo.add(*to_rename, *to_modify, *to_delete)
    repo.commit('HEAD~4')

    # Add documents.
    added = [
        repo.path / 'dummy/added.txt',
        repo.path / 'dummy/added.html',
    ]

    for source_file in added:
        source_file.write_text(f"{random()}")

    repo.add(*added)
    repo.commit('HEAD~3')

    # Rename documents.
    repo.move(to_rename[0], repo.path / 'dummy/renamed.txt')
    repo.move(to_rename[1], repo.path / 'dummy/renamed.html')
    repo.commit('HEAD~2')

    # Modify documents.
    with to_modify[0].open('a') as f1, to_modify[1].open('a') as f2:
        f1.write('modification')
        f2.write('modification')

    repo.add(*to_modify)
    repo.commit('HEAD~1')

    # Delete documents.
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
                Path('dummy/added.html'): 'added.html',
                Path('dummy/added.txt'): 'added.txt',
            },
            'modified': {
                Path('dummy/modified.html'): 'modified.html',
                Path('dummy/modified.txt'): 'modified.txt',
            },
            'renamed': {
                Path('dummy/to_rename.html'): 'renamed.html',
                Path('dummy/to_rename.txt'): 'renamed.txt',
            },
            'deleted': [
                Path('dummy/deleted.html'),
                Path('dummy/deleted.txt'),
            ],
        }
        assert actual == expected

    # Add source file.

    async def test_add_source_file(self, content):
        source_file = Path('dummy/add.txt')
        assert await content.add(source_file) == 'add.txt'

    async def test_add_source_file_with_missing_handler(self, content):
        source_file = Path('missing/handler.txt')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.add(source_file)

    async def test_add_source_file_not_versioned(self, content):
        source_file = Path('/tmp/add.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.add(source_file)

    # Modify source file.

    async def test_modify_source_file(self, content):
        source_file = Path('dummy/modify.txt')
        assert await content.modify(source_file) == 'modify.txt'

    async def test_modify_source_file_with_missing_handler(self, content):
        source_file = Path('missing/handler.txt')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.modify(source_file)

    async def test_modify_source_file_not_versioned(self, content):
        source_file = Path('/tmp/modify.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.modify(source_file)

    # Rename source file.

    async def test_rename_source_file(self, content):
        src = PurePath('dummy/src.txt')
        dst = Path('dummy/dst.txt')
        assert await content.rename(src, dst) == 'dst.txt'

    async def test_rename_source_file_with_missing_handler(self, content):
        src = PurePath('missing/src.txt')
        dst = Path('missing/dst.txt')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.rename(src, dst)

    async def test_rename_source_file_not_versioned(self, content):
        src = PurePath('/tmp/src.txt')
        dst = Path('/tmp/dst.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.rename(src, dst)

    async def test_rename_source_file_with_different_handler(self, content):
        src = PurePath('dummy/src.txt')
        dst = Path('dummy/dst.html')

        with pytest.raises(exceptions.HandlerChangeForbidden):
            await content.rename(src, dst)

    # Delete source file.

    async def test_delete_source_file(self, content):
        source_file = PurePath('dummy/delete.txt')
        assert await content.delete(source_file) == 'delete.txt'

    async def test_delete_source_file_with_missing_handler(self, content):
        source_file = Path('missing/handler.txt')

        with pytest.raises(exceptions.HandlerNotFound):
            await content.delete(source_file)

    async def test_delete_source_file_not_versioned(self, content):
        source_file = Path('/tmp/modify.txt')

        with pytest.raises(exceptions.FileNotVersioned):
            await content.delete(source_file)

    # Get handler.

    def test_get_handler_with_absolute_path(self, content):
        source_file = content.repository.path / 'dummy/handler.txt'
        handler = content.get_handler(source_file)
        assert isinstance(handler, content.handlers['dummy/*.txt'])

    def test_get_handler_with_relative_path(self, content):
        source_file = PurePath('dummy/handler.txt')
        handler = content.get_handler(source_file)
        assert isinstance(handler, content.handlers['dummy/*.txt'])

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

        assert 'dummy/added.html' in update.preview
        assert 'dummy/added.txt' in update.preview

        assert 'dummy/modified.html' in update.preview
        assert 'dummy/modified.txt' in update.preview

        assert 'dummy/to_rename.html -> dummy/renamed.html' in update.preview
        assert 'dummy/to_rename.txt -> dummy/renamed.txt' in update.preview

        assert 'dummy/deleted.html' in update.preview
        assert 'dummy/deleted.txt' in update.preview

    async def test_git_error_during_planning(self, content):
        with content.load_changes('INVALID_COMMIT') as update:
            with pytest.raises(exceptions.ContentUpdatePlanFailure) as excinfo:
                await update.plan()

        assert this_string(
            str(excinfo.value),
            contains="INVALID_COMMIT did not resolve",
        )

    # Run update.

    async def test_run_update(self, content):
        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()
            actual = await update.run()

        expected = {
            'added': {
                Path('dummy/added.html'): 'added.html',
                Path('dummy/added.txt'): 'added.txt',
            },
            'modified': {
                Path('dummy/modified.html'): 'modified.html',
                Path('dummy/modified.txt'): 'modified.txt',
            },
            'renamed': {
                PurePath('dummy/to_rename.html'): 'renamed.html',
                PurePath('dummy/to_rename.txt'): 'renamed.txt',
            },
            'deleted': [
                PurePath('dummy/deleted.html'),
                PurePath('dummy/deleted.txt'),
            ],
        }

        assert actual == expected

    async def test_errors_during_update_run(self, diff, repository):
        content = ContentManager(repository, {})  # No handlers

        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()

            with pytest.raises(exceptions.ContentUpdateRunFailure) as excinfo:
                await update.run()

        expected = {
            diff['added'][0]: HandlerNotFound(diff['added'][0]),
            diff['added'][1]: HandlerNotFound(diff['added'][1]),
            diff['modified'][0]: HandlerNotFound(diff['modified'][0]),
            diff['modified'][1]: HandlerNotFound(diff['modified'][1]),
            diff['renamed'][0][0]: HandlerNotFound(diff['renamed'][0][0]),
            diff['renamed'][1][0]: HandlerNotFound(diff['renamed'][1][0]),
            diff['deleted'][0]: HandlerNotFound(diff['deleted'][0]),
            diff['deleted'][1]: HandlerNotFound(diff['deleted'][1]),
        }

        assert excinfo.value.errors == expected
        raise NotImplementedError("check report failure, not exceptions.errors")

    async def test_report(self, content):
        with content.load_changes('HEAD~4', show_progress=False) as update:
            await update.plan()
            await update.run()

        assert 'dummy/added.html' in update.report
        assert 'dummy/added.txt' in update.report

        assert 'dummy/modified.html' in update.report
        assert 'dummy/modified.txt' in update.report

        assert 'dummy/to_rename.html' in update.report
        assert 'dummy/to_rename.txt' in update.report

        assert 'dummy/deleted.html' in update.report
        assert 'dummy/deleted.txt' in update.report

    # Add content.

    async def test_add_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.add_content()

        expected = {
            Path('dummy/added.html'): 'added.html',
            Path('dummy/added.txt'): 'added.txt',
        }

        assert (actual, errors) == (expected, {})

    # Modify content.

    async def test_modify_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.modify_content()

        expected = {
            Path('dummy/modified.html'): 'modified.html',
            Path('dummy/modified.txt'): 'modified.txt',
        }

        assert (actual, errors) == (expected, {})

    # Rename content.

    async def test_rename_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.rename_content()

        expected = {
            PurePath('dummy/to_rename.html'): 'renamed.html',
            PurePath('dummy/to_rename.txt'): 'renamed.txt',
        }

        assert (actual, errors) == (expected, {})

    async def test_handler_change_errors_are_caught(self, repository):
        raise NotImplementedError

    # Delete content.

    async def test_delete_content(self, content):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual, errors = await update.delete_content()

        expected = [
            PurePath('dummy/deleted.html'),
            PurePath('dummy/deleted.txt'),
        ]

        assert (actual, errors) == (expected, {})

    # Add/modify/rename/delete content.

    @pytest.mark.parametrize('method, path', [
        (ContentUpdateRunner.add_content, Path('dummy/added')),
        (ContentUpdateRunner.modify_content, Path('dummy/modified')),
        (ContentUpdateRunner.rename_content, PurePath('dummy/to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('dummy/deleted')),
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

        handlers = {'dummy/*.*': BrokenHandler}
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
        (ContentUpdateRunner.add_content, Path('dummy/added')),
        (ContentUpdateRunner.modify_content, Path('dummy/modified')),
        (ContentUpdateRunner.rename_content, PurePath('dummy/to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('dummy/deleted')),
    ])
    async def test_handler_not_found_errors_are_caught(self, method, path, repository):
        # Fixtures
        def exc(suffix):
            return exceptions.HandlerNotFound(path.with_suffix(suffix))

        content = ContentManager(repository, {})  # No handlers

        # Test
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            result, actual = await method(update)

        # Assertions
        expected = {
            path.with_suffix('.html'): exc('.html'),
            path.with_suffix('.txt'): exc('.txt'),
        }

        assert len(result) == 0
        assert actual == expected

    @pytest.mark.parametrize('method, path', [
        (ContentUpdateRunner.add_content, Path('dummy/added')),
        (ContentUpdateRunner.modify_content, Path('dummy/modified')),
        (ContentUpdateRunner.rename_content, PurePath('dummy/to_rename')),
        (ContentUpdateRunner.delete_content, PurePath('dummy/deleted')),
    ])
    async def test_invalid_file_errors_are_caught(self, method, path, repository):
        # Fixtures
        def exc(suffix):
            return exceptions.InvalidFile(path.with_suffix(suffix), [])

        class BrokenHandler(BaseFileHandler):
            processor = DummyProcessor

            async def insert(self):
                raise exceptions.InvalidFile(self.source_file.path, [])

            async def update(self):
                raise exceptions.InvalidFile(self.source_file.path, [])

            async def rename(self, target):
                raise exceptions.InvalidFile(self.source_file.path, [])

            async def delete(self):
                raise exceptions.InvalidFile(self.source_file.path, [])

        handlers = {'dummy/*.*': BrokenHandler}
        content = ContentManager(repository, handlers)

        # Test
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            result, actual = await method(update)

        # Assertions
        expected = {
            path.with_suffix('.html'): exc('.html'),
            path.with_suffix('.txt'): exc('.txt'),
        }

        assert len(result) == 0
        assert actual == expected
