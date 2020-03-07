from io import StringIO
from itertools import chain
from pathlib import Path, PurePath
from random import random

import pytest

from arugifa.cms import exceptions
from arugifa.cms.base.handlers import BaseFileHandler
from arugifa.cms.base.processors import BaseFileProcessor
from arugifa.cms.update import ContentManager


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


# Tests

class TestContentManager:

    '''
    def test_print_diff(self, repository):
        stream = StringIO()
        repository.diff('HEAD~2', quiet=False, output=stream)

        assert stream.getvalue() == dedent("""\
            The following files have been added:
            - added.txt
            - new.txt
            The following files have been modified:
            - modified.txt
            The following files have been renamed:
            - to_rename.txt -> renamed.txt
            The following files have been deleted:
            - deleted.txt
        """)
    '''

    @pytest.fixture(scope='class')
    def handlers(self):
        return {'dummy/*.txt': DummyHandler, 'dummy/*.html': AnotherDummyHandler}

    @pytest.fixture(scope='class')
    def changes(self, repository):
        return repository.diff('HEAD~4')

    @pytest.fixture(scope='class')
    def repository(self, git, tmp_path_factory):
        tmpdir = tmp_path_factory.mktemp(self.__class__.__name__)
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

    @pytest.fixture
    def content(self, db, handlers, repository):
        return ContentManager(repository, handlers)

    # Load changes.

    async def test_load_changes(self, content, repository):
        with content.load_changes('HEAD~4', output=StringIO()) as update:
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

    async def test_load_changes_with_errors(self):
        # Test UpdatePlanFailure and UpdateRunFailure
        raise NotImplementedError

    async def test_load_changes_preview(self, content, repository):
        output = StringIO()

        with content.load_changes('HEAD~4', output=output) as update:
            await update.plan(show_preview=True)

        preview = output.getvalue()

        assert 'dummy/added.html' in preview
        assert 'dummy/added.txt' in preview

        assert 'dummy/modified.html' in preview
        assert 'dummy/modified.txt' in preview

        assert 'dummy/to_rename.html -> dummy/renamed.html' in preview
        assert 'dummy/to_rename.txt -> dummy/renamed.txt' in preview

        assert 'dummy/deleted.html' in preview
        assert 'dummy/deleted.txt' in preview

    async def test_load_changes_report(self, content, repository):
        output = StringIO()

        with content.load_changes('HEAD~4', output=output, show_progress=False) as update:  # noqa: E501
            await update.plan()
            await update.run(show_report=True)

        report = output.getvalue()

        assert 'dummy/added.html' in report
        assert 'dummy/added.txt' in report

        assert 'dummy/modified.html' in report
        assert 'dummy/modified.txt' in report

        assert 'dummy/to_rename.html' in report
        assert 'dummy/to_rename.txt' in report

        assert 'dummy/deleted.html' in report
        assert 'dummy/deleted.txt' in report

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
    def test_runner(self):
        raise NotImplementedError
