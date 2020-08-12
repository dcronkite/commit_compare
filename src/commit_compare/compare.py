"""
Compare output from multiple runs of git commits

Feature ideas:
* synonyms (e.g., the name of data changes over time)
"""
import datetime
from loguru import logger

from commit_compare.gittools import GitRepo


def main():
    repo = GitRepo('https://github.com/dcronkite/pytheas', r'D:\wksp\test_pytheas')
    for commit in repo.iter_commits(start_date=datetime.datetime(2020, 7, 15), end_date=datetime.datetime(2020, 7, 16)):
        logger.info(commit)


if __name__ == '__main__':
    main()
