"""
Compare output from multiple runs of git commits

Feature ideas:
* synonyms (e.g., the name of data changes over time)
"""
import os
import pathlib

import click
import datetime
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from loguru import logger
from pandas.errors import EmptyDataError

from commit_compare.gittools import GitRepo


def save_figure(pdf_writer, field, axis, output_directory, *, title=None):
    fig = axis.get_figure()
    fig.set_size_inches(10, 7.5)
    plt.title(title if title else f'{field}')
    plt.tight_layout()
    plt.savefig(output_directory / f'{field}.svg', bbox_inches='tight')
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
@click.option('--branch', default='master',
              help='Branch to use.')
@click.option('--alt-commands', multiple=True,
              help='Alternate run commands')
@click.option('--select-commits', multiple=True,
              help='Only process selected commits.')
@click.option('--output-directory', default=pathlib.Path('.'),
              type=click.Path(file_okay=False, path_type=pathlib.Path),
              help='Directory to output data (images/pdf)')
def main(repo_url, outfile, command, *, repo_dest=None, pre_command='', id_col='id', start_date=None, end_date=None,
         start_commit=None, end_commit=None, relative_pythonpath='', venv=None, branch='master',
         alt_commands=None, ignore_col=None, select_commits=None, output_directory=pathlib.Path('.')):
    """

    :param output_directory: Directory to output data (images/pdf)
    :param branch: git branch to checkout; all versions must be in same branch
    :param alt_commands: alternative commands to try (e.g., if an older version used a different api)
    :param ignore_col: ignore specified columns
    :param select_commits: only run these particular commits
    :param venv: Initialize virtual environment with selected python interpreter
    :param relative_pythonpath:
    :param repo_url: Git repository to clone.
    :param outfile: Output csv file to be compared against previous/subsequent runs.
    :param command: Run command: use {target} to get the repository path and {outfile} for the supplied output file
    :param repo_dest: Parent directory for cloning; the new directory will be cloned INSIDE this directory.
    :param pre_command: Run before the run command; this might include, e.g., set up a virtual environment.
    :param id_col: Column to use for joining data, etc.
    :param start_date: earliest date to start running/comparing commits
    :param end_date: latest date before stopping running/comparing commits
    :param start_commit: start with this commit and run all commits after
    :param end_commit: end with this commit (assumes that running commits before)
    :return:
    """
    ignore_col = ignore_col or []
    output_directory.mkdir(exist_ok=True)
    logger.add(output_directory / 'commit_compare_{time}.log')
    data = {}  # col -> DataFrame (each row is a commit)
    commits = []
    repo = GitRepo(repo_url, repo_dest, branch=branch)
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
                                    start_commit=start_commit, end_commit=end_commit,
                                    select_commits=select_commits):
        logger.info(f'Starting commit: {commit}')
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

    with PdfPages(output_directory / 'output.pdf') as pdf_writer:
        list_of_sums = []
        n_fields = len(data)
        for i, (field, df) in enumerate(data.items()):
            logger.info(f'Building chart for: {field} ({i + 1}/{n_fields})')
            cols = [c for c in commits if c in df.columns]
            # TODO: find the first non-empty row and check dtype
            if df[df.columns[1]].dtypes not in ['O', 'bool'] and df[df.columns[-1]].dtypes not in ['O', 'bool']:
                # is numeric
                list_of_sums.append(df[cols].sum())
                save_figure(pdf_writer, f'{field}_box', df[cols].plot(kind='box'), output_directory=output_directory,
                            title=f'Boxplot for {field}')
                try:
                    save_figure(pdf_writer, f'{field}_line', df[cols].sum().plot(kind='line'),
                                output_directory=output_directory, title=f'Line for {field}')
                except Exception as e:
                    logger.exception(e)
                    logger.warning(f'Skipping field due to error {e}')
            else:  # is enum-like string
                ndf = pd.DataFrame({
                    col: df[col].value_counts() for col in cols
                })
                save_figure(pdf_writer, field, ndf.T.plot.bar(stacked=True), output_directory=output_directory)
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
                save_figure(pdf_writer, f'{field}_num_changes', ddf.T.plot.bar(stacked=False, subplots=False),
                            output_directory=output_directory,
                            title=f'Number of Changes by Value: {field}')

        if not list_of_sums:
            logger.warning('No data collected during this process.')
        else:
            sum_df = pd.concat(list_of_sums, axis=1, keys=data.keys())
            sum_df.fillna(0, inplace=True)
            save_figure(pdf_writer, 'sum', sum_df.plot(kind='line'), output_directory=output_directory, title='Summary')
            plt.close('all')
            d = pdf_writer.infodict()
            d['Title'] = 'Summary Variables Across Git Commits'
            d['Author'] = ''
            d['CreationDate'] = datetime.datetime.today()


if __name__ == '__main__':
    main()
