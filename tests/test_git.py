from pathlib import Path, PurePath
from random import random

import git.cmd
import pytest

from arugifa.cms import exceptions
from arugifa.cms.git import GitRepository
from arugifa.toolbox.test.helpers import this_exc, this_string


class TestGitRepository:

    @pytest.fixture
    def repository(self, git, tmp_path):
        """Return a Git repository, with some files and commit history.

        Also testing implicitely :meth:`website.utils.git.GitRepository.add` and
        :meth:`website.utils.git.GitRepository.commit`.
        """
        return git.init(tmp_path)

    @pytest.fixture
    def initial(self, repository):
        readme = repository.path / 'README.txt'
        readme.touch()

        repository.add(readme)
        repository.commit("Initial commit")

    @pytest.fixture
    def history(self, initial, repository):
        # Populate repository with non-empty files,
        # otherwise Git can be lost with file names later on.
        to_modify = repository.path / 'modified.txt'
        to_modify.write_text(f'{random()}')

        to_delete = repository.path / 'deleted.txt'
        to_delete.write_text(f'{random()}')

        to_rename = repository.path / 'to_rename.txt'
        to_rename.write_text(f'{random()}')

        repository.add(to_modify, to_delete, to_rename)
        repository.commit("HEAD~2")

        # Proceed to some changes.
        repository.remove(to_delete)
        repository.move(to_rename, 'renamed.txt')

        to_modify.write_text(f'{random()}')

        added = repository.path / 'added.txt'
        added.write_text(f'{random()}')

        repository.add()
        repository.commit("HEAD~1")

        # Make one last commit,
        # to be able to compare not subsequent commits.
        new = repository.path / 'new.txt'
        new.write_text(f'{random()}')

        repository.add(new)
        repository.commit("HEAD")

    # Init repository.

    def test_init_repository(self, git, tmp_path):
        git.init(tmp_path)
        repo = GitRepository(tmp_path)
        assert repo.path == tmp_path

    def test_git_directory_missing(self, tmp_path):
        with pytest.raises(exceptions.GitRepositoryNotFound):
            GitRepository(tmp_path / 'nothing')

    def test_repository_not_initialized(self, tmp_path):
        with pytest.raises(exceptions.GitRepositoryNotFound):
            GitRepository(tmp_path)

    # Git init.

    def test_git_init(self, git, tmp_path):
        repo = git.init(tmp_path)
        assert repo.path == tmp_path

    def test_cli_error_during_git_init(self, monkeypatch, tmp_path):
        monkeypatch.setattr(git.cmd.Git, 'GIT_PYTHON_GIT_EXECUTABLE', 'gitogi')

        with pytest.raises(exceptions.GitCLIError) as excinfo:
            GitRepository.init(tmp_path)

        assert this_exc(excinfo, contains="gitogi not found")

    # Git add.

    def test_add_single_file(self, initial, repository):
        # Fixtures
        to_add = repository.path / 'added.txt'
        to_add.touch()

        # Test
        repository.add(to_add)
        repository.commit('HEAD')

        # Assertions
        diff = {
            'added': [Path('added.txt')],
            'deleted': [],
            'modified': [],
            'renamed': [],
        }

        assert repository.diff('HEAD~1') == diff

    def test_add_multiple_files(self, initial, repository):
        # Fixtures
        to_add = [
            repository.path / 'added.html',
            repository.path / 'added.txt',
        ]

        for source_file in to_add:
            source_file.touch()

        # Test
        repository.add(*to_add)
        repository.commit('HEAD')

        # Assertions
        diff = {
            'added': [Path('added.html'), Path('added.txt')],
            'deleted': [],
            'modified': [],
            'renamed': [],
        }

        assert repository.diff('HEAD~1') == diff

    def test_add_all_files(self, initial, repository):
        # Fixtures
        modified = repository.path / 'modified.txt'
        modified.write_text(f'{random()}')

        to_rename = repository.path / 'to_rename.txt'
        to_rename.write_text(f'{random()}')

        deleted = repository.path / 'deleted.txt'
        deleted.write_text(f'{random()}')

        repository.add()
        repository.commit('HEAD~1')

        # Test
        added = repository.path / 'added.txt'
        added.write_text(f'{random()}')

        renamed = repository.path / 'renamed.txt'
        to_rename.rename(renamed)

        modified.write_text(f'{random()}')
        deleted.unlink()

        repository.add()
        repository.commit('HEAD')

        # Assertions
        diff = {
            'added': [Path('added.txt')],
            'deleted': [PurePath('deleted.txt')],
            'modified': [Path('modified.txt')],
            'renamed': [(PurePath('to_rename.txt'), Path('renamed.txt'))],
        }

        assert repository.diff('HEAD~1') == diff

    # Git diff.

    def test_diff_between_two_specific_commits(self, history, repository):
        diff = {
            'added': [Path('added.txt')],
            'deleted': [Path('deleted.txt')],
            'modified': [Path('modified.txt')],
            'renamed': [(Path('to_rename.txt'), Path('renamed.txt'))],
        }
        assert repository.diff('HEAD~2', 'HEAD~1') == diff

    def test_diff_from_one_specific_commit_to_head(self, history, repository):
        diff = {
            'added': [Path('added.txt'), Path('new.txt')],
            'deleted': [Path('deleted.txt')],
            'modified': [Path('modified.txt')],
            'renamed': [(Path('to_rename.txt'), Path('renamed.txt'))],
        }
        assert repository.diff('HEAD~2') == diff

    def test_diff_with_changes_lost_between_not_subsequent_commits(self, history, repository):  # noqa: E501
        diff = {
            'added': [
                Path('added.txt'),
                Path('modified.txt'),
                Path('new.txt'),
                Path('renamed.txt'),
            ],
            'deleted': [],
            'modified': [],
            'renamed': [],
        }
        assert repository.diff('HEAD~3') == diff

    # Git move.

    def test_git_move(self, initial, repository):
        to_rename = repository.path / 'to_rename.txt'
        to_rename.write_text(f'{random()}')

        repository.add(to_rename)
        repository.commit('HEAD~1')

        # Test
        repository.move(to_rename, 'renamed.txt')
        repository.commit('HEAD')

        # Assertions
        diff = {
            'added': [],
            'deleted': [],
            'modified': [],
            'renamed': [(Path('to_rename.txt'), PurePath('renamed.txt'))],
        }
        assert repository.diff('HEAD~1') == diff

    # Git remove.

    def test_git_remove(self, initial, repository):
        deleted = repository.path / 'deleted.txt'
        deleted.write_text(f'{random()}')

        repository.add(deleted)
        repository.commit('HEAD~1')

        # Test
        repository.remove(deleted)
        repository.commit('HEAD')

        # Assertions
        diff = {
            'added': [],
            'deleted': [PurePath('deleted.txt')],
            'modified': [],
            'renamed': [],
        }
        assert repository.diff('HEAD~1') == diff
        assert not deleted.exists()
