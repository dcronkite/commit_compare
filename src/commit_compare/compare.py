"""
Compare output from multiple runs of git commits

Feature ideas:
* synonyms (e.g., the name of data changes over time)
"""
import os

import click
import datetime
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from loguru import logger
from pandas.errors import EmptyDataError

from commit_compare.gittools import GitRepo


def save_figure(pdf_writer, field, axis, *, title=None):
    fig = axis.get_figure()
    fig.set_size_inches(10, 7.5)
    plt.title(title if title else f'{field}')
    plt.tight_layout()
    plt.savefig(f'{field}.svg', bbox_inches='tight')
    pdf_writer.savefig(bbox_inches='tight')
    plt.close('all')


def run_commands(pre_command, pre_command_no_pip, env, *commands):
    failed = []
    for cmd in commands:
        p = subprocess.Popen(f'{pre_command};{cmd}',
                             shell=True, stderr=subprocess.PIPE, env=env)
        res = p.communicate()
        err = res[1].decode('utf8')
        if 'You are using pip' in err:  # request to upgrade when using pip
            err = ''
        if 'requirements.txt' in err:
            logger.info('Requirements.txt file not found.')
            p = subprocess.Popen(f'{pre_command_no_pip};{cmd}',
                                 shell=True, stderr=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 env=env)
            res = p.communicate()
            err = res[1].decode('utf8')
        if 'errno' in err.lower() or 'error:' in err.lower():
            failed.append(err)
        else:
            return None
    return '; '.join(failed)


@click.command()
@click.argument('repo-url', required=True)
@click.argument('outfile', required=True, )
@click.argument('command', required=True, )
@click.option('--repo-dest', default=None,
              help='Parent directory for cloning; the new directory will be cloned INSIDE this directory.')
@click.option('--pre-command', default='',
              help='Run before the run command; this might include, e.g., set up a virtual environment.')
@click.option('--id-col', default='id',
              help='Id column to use as reference to join multiple runs together; expected in all datasets.')
@click.option('--ignore-col', multiple=True,
              help='Ignore these columns, do no analysis. Do not include `id_col`.')
@click.option('--start-date', default=None, type=click.DateTime(),
              help='Start date for selecting commits to run.')
@click.option('--end-date', default=None, type=click.DateTime(),
              help='End date for selecting commits to run.')
@click.option('--start-commit', default=None,
              help='Start running with this commit.')
@click.option('--end-commit', default=None,
              help='Stop running after this commit.')
@click.option('--relative-pythonpath', default='',
              help='Cloned root will automatically be added to PYTHONPATH, use this to add, e.g., "src" to the path.')
@click.option('--venv', default=None,
              help='Initialize virtual environment with selected python interpreter')
@click.option('--alt-commands', multiple=True,
              help='Alternate run commands')
def main(repo_url, outfile, command, *, repo_dest=None, pre_command='', id_col='id', start_date=None, end_date=None,
         start_commit=None, end_commit=None, relative_pythonpath='', venv=None, alt_commands=None, ignore_col=None):
    """

    :param venv:
    :param relative_pythonpath:
    :param repo_url: Git repository to clone.
    :param outfile: Output csv file to be compared against previous/subsequent runs.
    :param command: Run command: use {target} to get the repository path and {outfile} for the supplied output file
    :param repo_dest:
    :param pre_command:
    :param id_col:
    :param start_date:
    :param end_date:
    :param start_commit:
    :param end_commit:
    :return:
    """
    ignore_col = ignore_col or []
    data = {}  # col -> DataFrame (each row is a commit)
    commits = []
    repo = GitRepo(repo_url, repo_dest)
    pre_command = pre_command.format(target=repo.repo_path, outfile=outfile)
    pre_command_no_pip = ''
    run_command = command.format(target=repo.repo_path, outfile=outfile)
    alt_commands = [c.format(target=repo.repo_path, outfile=outfile) for c in alt_commands or []]
    if venv:
        p = subprocess.Popen(f'{venv} -m venv {repo.repo_path / ".venv"}', shell=True)
        p.communicate()
        pip_install = f'pip install -r {repo.repo_path / "requirements.txt"}'
        if os.name == 'nt':
            venv_command = repo.repo_path / '.venv' / 'Scripts' / 'activate.bat'
        else:
            venv_command = f"source {repo.repo_path / '.venv' / 'bin' / 'activate'}"
        pre_command_no_pip = f'{pre_command};{venv_command}'.strip(';')
        pre_command = f'{pre_command};{venv_command};{pip_install}'.strip(';')
    _env = {
        'PYTHONPATH': str(repo.repo_path / relative_pythonpath)
    }
    env = os.environ.copy()
    env.update(_env)
    for commit in repo.iter_commits(start_date=start_date, end_date=end_date,
                                    start_commit=start_commit, end_commit=end_commit):
        logger.info(f'Starting commit: {commit}')
        # TODO: INSERT INTO
        errors = run_commands(pre_command, pre_command_no_pip, env, run_command, *alt_commands)
        if errors:
            logger.warning(f'Command failed for commit {commit.hexsha}: \n{errors}')
            continue
        # read the output
        try:
            df = pd.read_csv(outfile)
        except EmptyDataError as e:
            logger.warning(e)
            continue
        if id_col not in df.columns:
            logger.warning(f'Commit output lacks id column "{id_col}". Skipping commit {commit.hexsha}')
            continue
        commits.append(commit.hexsha[:8])
        for col in (col for col in df.columns if col != id_col and col not in ignore_col):
            col_df = df[[id_col, col]]
            col_df.columns = [id_col, commit.hexsha[:8]]
            if col in data:
                data[col] = pd.merge(data[col], col_df, on=id_col, how='outer')
            else:
                data[col] = col_df

    with PdfPages('output.pdf') as pdf_writer:
        list_of_sums = []
        n_fields = len(data)
        for i, (field, df) in enumerate(data.items()):
            logger.info(f'Running: {field} ({i+1}/{n_fields})')
            cols = [c for c in commits if c in df.columns]
            if df[df.columns[1]].dtypes not in ['O', 'bool']:  # is numeric
                list_of_sums.append(df[cols].sum())
                save_figure(pdf_writer, field, df[cols].plot(kind='box'))
            else:  # is enum-like string
                ndf = pd.DataFrame({
                    col: df[col].value_counts() for col in cols
                })
                save_figure(pdf_writer, field, ndf.T.plot.bar(stacked=True))
                ddf = pd.DataFrame({
                    f'{cols[i]}-{cols[i + 1]}': df.groupby(cols[i:i + 2]).count()[id_col]
                    for i in range(len(cols) - 1)
                })
                equal_index = []
                inequal_index = []
                for v1, v2 in ddf.index:
                    if v1 == v2:
                        equal_index.append((v1, v2))
                    else:
                        inequal_index.append((v1, v2))
                ddf = ddf.reindex(equal_index + inequal_index)  # place no changes at the front
                ax = ddf.T.plot.bar(stacked=False, subplots=False)
                save_figure(pdf_writer, f'{field}_num_changes', ax, title=f'Number of Changes by Value: {field}')

        sum_df = pd.concat(list_of_sums, axis=1, keys=data.keys())
        sum_df.fillna(0, inplace=True)
        save_figure(pdf_writer, 'sum', sum_df.plot(kind='line'), title='Summary')
        plt.close('all')
        d = pdf_writer.infodict()
        d['Title'] = 'Summary Variables Across Git Commits'
        d['Author'] = ''
        d['CreationDate'] = datetime.datetime.today()


if __name__ == '__main__':
    main()
