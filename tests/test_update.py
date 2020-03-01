from pathlib import Path, PurePath
from random import random

import pytest

from arugifa.cms import exceptions
from arugifa.cms.handlers import BaseFileHandler
from arugifa.cms.processors import BaseFileProcessor
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


class AnotherDummyHandler(BaseFileHandler):
    processor = DummyProcessor

    async def insert(self):
        return self.source_file.path.name

    async def update(self):
        return self.source_file.path.name

    async def rename(self, target):
        pass

    async def delete(self):
        return self.source_file.path.name


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
        (tmpdir / 'dummy').mkdir()

        # Initialize repository.
        repo = git.init(tmpdir)

        to_rename = repo.path / 'dummy/to_rename.txt'
        to_rename.write_text(f"{random()}")

        to_modify = repo.path / 'dummy/modified.txt'
        to_modify.write_text(f"{random()}")

        to_delete = repo.path / 'dummy/deleted.txt'
        to_delete.write_text(f"{random()}")

        repo.add(to_rename, to_modify, to_delete)
        repo.commit('HEAD~4')

        # Add documents.
        added = repo.path / 'dummy/added.txt'
        added.write_text(f"{random()}")

        repo.add(added)
        repo.commit('HEAD~3')

        # Rename documents.
        repo.move(to_rename, repo.path / 'dummy/renamed.txt')
        repo.commit('HEAD~2')

        # Modify documents.
        with to_modify.open('a') as f:
            f.write('modification')

        repo.add(to_modify)
        repo.commit('HEAD~1')

        # Delete documents.
        repo.remove(to_delete)
        repo.commit('HEAD')

        return repo

    @pytest.fixture
    def content(self, db, handlers, repository):
        return ContentManager(repository, handlers, db)

    # Update content.

    # TODO: Update at least 2 different kinds of documents (02/2019)
    # Because that's how the content manager is intended to behave...
    async def test_update_content(self, content, db, repository):
        with content.load_changes('HEAD~4') as update:
            await update.plan()
            actual = await update.run()

        expected = {
            'added': {
                repository.path / 'dummy/added.txt': 'added',
            },
            'modified': {
                repository.path / 'dummy/modified.txt': 'modified',
            },
            'renamed': {
                repository.path / 'dummy/renamed.txt': 'renamed',
            },
            'deleted': {
                repository.path / 'dummy/deleted.txt': 'deleted',
            },
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

    # Rename documents.

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

    # Delete documents.

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

    def test_get_handler(self, content):
        source = content.directory / 'blog/2019/article.html'
        handler = content.get_handler(source)
        assert handler.__class__ is content.handlers['blog']

    def test_get_handler_with_relative_path(self, content):
        source = PurePath('blog/article.html')
        handler = content.get_handler(source)
        assert handler.__class__ is content.handlers['blog']

    def test_get_missing_handler(self, content):
        source = content.directory / 'reviews/article.html'

        with pytest.raises(exceptions.HandlerNotFound):
            content.get_handler(source)

    def test_document_not_stored_in_content_directory(self, content):
        source = PurePath('/void/article.html')

        with pytest.raises(exceptions.InvalidDocumentLocation):
            content.get_handler(source)

    def test_document_not_categorized(self, content):
        source = content.directory / 'article.html'

        with pytest.raises(exceptions.DocumentNotCategorized):
            content.get_handler(source)


class TestContentUpdateRunner:
    def test_runner(self):
        raise NotImplementedError
