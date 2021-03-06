import shutil
import tempfile
from pathlib import Path
from loguru import logger

from git import Repo, GitCommandError


class GitRepo:

    def __init__(self, git_url, repo_file=None, branch='master'):
        self.git_url = git_url
        self._cleanup = None
        if not repo_file:
            self._cleanup = tempfile.TemporaryDirectory()
            repo_file = self._cleanup.name
        for i in range(100):
            self.repo_path = Path(repo_file) / f'{Path(self.git_url).name}_{i}'
            try:
                self.repo = Repo.clone_from(self.git_url, self.repo_path, branch=branch)
            except GitCommandError:
                logger.warning(f'Clone destination directory already exists {self.repo_path}, will try a different name.')
                continue
            logger.info(f'Cloning to {self.repo_path}')
            break

    def iter_commits(self, *, start_date=None, end_date=None, start_commit=None, end_commit=None):
        found_start_commit = False
        for commit in sorted(self.repo.iter_commits(), key=lambda c: c.committed_datetime):
            if start_date and commit.committed_datetime < start_date.replace(tzinfo=commit.committed_datetime.tzinfo):
                continue
            elif end_date and commit.committed_datetime > end_date.replace(tzinfo=commit.committed_datetime.tzinfo):
                break
            elif start_commit and not found_start_commit:
                if commit.hexsha.startswith(start_commit):
                    found_start_commit = True
                else:
                    continue
            elif end_commit and found_start_commit and commit.hexsha.startswith(end_commit):
                break
            self.repo.git.checkout(commit)
            yield commit

    def __del__(self):
        if self._cleanup:
            self._cleanup.cleanup()
        else:
            try:
                shutil.rmtree(self.repo_path)
            except PermissionError:
                logger.exception(f'Failed to remove new repository due to permission issues.'
                                 f' You may need to manually remove {self.repo_path}')
