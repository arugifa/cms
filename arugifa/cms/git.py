"""Manage a Git repository, where is stored the website's content."""

import hashlib
import inspect
from pathlib import Path, PurePath
from typing import Dict, Iterable, Union

import git.exc
from git import Repo

from arugifa.cms import exceptions


class GitRepository:
    """Simple wrapper around :class:`git.Repo` to provide a nicer API.

    This is especially true for :meth:`Repo.diff`, but a couple of other methods have
    also been rewritten:

    - to simulate how Git is used on the command-line,
    - and decouple tests from code implementation
      (so the tests don't depend directly on :mod:`git`).

    Only implements ``git add``, ``git commit``, ``git diff`` and ``git init``, as they
    are the only commands we need in order to manage website's content and track changes.

    :param path:
        repository's path.
    :raise ~.RepositoryNotFound:
        if no repository exists at ``path``.
    """  # noqa: E501

    def __init__(self, path: Path):
        try:
            self._repo = Repo(path)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            raise exceptions.GitRepositoryNotFound(path)

        self.path = Path(path)

    @classmethod
    def init(cls, directory: Union[str, Path]) -> 'GitRepository':
        """Create a new repository, located at ``directory``.

        :raise PermissionError: ...
        :raise GitCLIError: ...
        """
        try:
            Repo.init(str(directory), mkdir=True)  # Can raise PermissionError
        except git.exc.CommandError as exc:
            raise exceptions.GitCLIError(exc)

        return cls(directory)

    def add(self, *files: Path) -> None:
        """Add files to the repository's index.

        By default, adds all untracked files and unstaged changes to the index.

        :raise OSError: ...
        """
        if files:
            self._repo.index.add(map(str, files))  # Can raise OSError
        else:
            # Add all untracked files (i.e., new or renamed files).
            self._repo.index.add(self._repo.untracked_files)  # Can raise OSError

            # Add all changes not staged for commit.
            for change in self._repo.index.diff(None):  # Can raise OSError
                try:
                    # Added or modified files.
                    self._repo.index.add([change.a_blob.path])  # Can raise OSError
                except FileNotFoundError:
                    # Deleted or renamed files.
                    self._repo.index.remove([change.a_blob.path])  # Can raise OSError

    def commit(self, message: str) -> str:
        """Commit files added to the repository's index.

        :param message: commit message.
        :raise OSError: ...
        :return: the commit's hash.
        """
        commit = self._repo.index.commit(message)  # Can raise OSError
        return hashlib.sha1(commit.binsha).hexdigest()

    def diff(self, since: str, until: str = 'HEAD') -> Dict[str, Iterable[Path]]:
        """Return changes between two commits.

        :param since: hash of the reference commit.
        :param until: hash of the commit to compare to.

        :raise OSError: ...
        :return: ``added``, ``modified``, ``renamed`` and ``deleted`` files.
        """
        try:
            diff = self._repo.commit(since).diff(until)  # Can raise OSError
        except git.exc.BadName as exc:
            raise exceptions.GitUnknownCommit(exc)

        pretty_diff = {
            'added': sorted(
                Path(d.b_blob.path)
                for d in diff.iter_change_type('A')
            ),
            'modified': sorted(
                Path(d.b_blob.path)
                for d in diff.iter_change_type('M')
            ),
            'renamed': sorted(
                (PurePath(d.a_blob.path), Path(d.b_blob.path))
                for d in diff.iter_change_type('R')
            ),
            'deleted': sorted(
                PurePath(d.a_blob.path)
                for d in diff.iter_change_type('D')
            ),
        }

        return pretty_diff

    def move(self, src: Path, dst: str) -> None:
        self._repo.index.move([str(src), dst])  # Can raise OSError

    def remove(self, *files: Path) -> None:
        self._repo.index.remove(map(str, files), working_tree=True)  # Can raise OSError
