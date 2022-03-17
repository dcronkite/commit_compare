import datetime
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
        dt = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.repo_path = Path(repo_file) / f'{Path(self.git_url).name}_{dt}'
        self.repo = Repo.clone_from(self.git_url, self.repo_path, branch=branch)
        logger.info(f'Cloning to {self.repo_path}')

    def iter_commits(self, *, start_date=None, end_date=None, start_commit=None, end_commit=None,
                     select_commits=None):
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
            elif select_commits:
                if not self._commit_hexsha_in(commit, select_commits):
                    continue
            self.repo.git.checkout(commit)
            yield commit

    def _commit_hexsha_in(self, commit, select_commits):
        for c in select_commits:
            if commit.hexsha.startswith(c):
                return True

    def __del__(self):
        if self._cleanup:
            self._cleanup.cleanup()
        else:
            try:
                shutil.rmtree(self.repo_path)
            except PermissionError:
                logger.exception(f'Failed to remove new repository due to permission issues.'
                                 f' You may need to manually remove {self.repo_path}')
