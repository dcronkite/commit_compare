"""
Compare output from multiple runs of git commits

Feature ideas:
* synonyms (e.g., the name of data changes over time)
"""
import click
import datetime
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from loguru import logger

from commit_compare.gittools import GitRepo


@click.command()
@click.argument('repo-url', required=True)
@click.argument('outfile', required=True,)
@click.argument('command', required=True,)
@click.option('--repo-dest', default=None,
              help='Parent directory for cloning; the new directory will be cloned INSIDE this directory.')
@click.option('--pre-command', default=None,
              help='Run before the run command; this might include, e.g., set up a virtual environment.')
@click.option('--id-col', default='id',
              help='Id column to use as reference to join multiple runs together; expected in all datasets.')
@click.option('--start-date', default=None, type=click.DateTime(),
              help='Start date for selecting commits to run.')
@click.option('--end-date', default=None, type=click.DateTime(),
              help='End date for selecting commits to run.')
@click.option('--start-commit', default=None,
              help='Start running with this commit.')
@click.option('--end-commit', default=None,
              help='Stop running after this commit.')
def main(repo_url, outfile, command, *, repo_dest=None, pre_command=None, id_col='id', start_date=None, end_date=None,
         start_commit=None, end_commit=None):
    """

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
    data = {}  # col -> DataFrame (each row
    id_col = 'id'
    repo = GitRepo(repo_url, repo_dest)
    commits = []
    run_command = pre_command + ';' + command if pre_command else command
    run_command = run_command.format(target=repo.repo_path, outfile=outfile)
    for commit in repo.iter_commits(start_date=start_date, end_date=end_date,
                                    start_commit=start_commit, end_commit=end_commit):
        logger.info(commit)
        # run the program
        p = subprocess.Popen(run_command, shell=True, stderr=subprocess.PIPE)
        res = p.communicate()
        if res[1]:  # error occurred
            logger.warning(f'Command failed for commit {commit.hexsha}: \n{res[1]}')
            continue
        # read the output
        df = pd.read_csv(outfile)
        if id_col not in df.columns:
            logger.warning(f'Commit output lacks id column "{id_col}". Skipping commit {commit.hexsha}')
            continue
        commits.append(commit.hexsha)
        for col in (col for col in df.columns if col != id_col):
            col_df = df[[id_col, col]]
            col_df.columns = [id_col, commit.hexsha]
            if col in data:
                data[col] = pd.merge(data[col], col_df, on=id_col, how='outer')
            else:
                data[col] = col_df

    with PdfPages('output.pdf') as pdf_writer:
        list_of_sums = []
        for field, df in data.items():
            cols = [c for c in commits if c in df.columns]
            plt.figure(figsize=(8, 6))
            if df[df.columns[1]].dtypes != 'O':  # is numeric
                list_of_sums.append(df[cols].sum())
                df[cols].plot(kind='box')
            else:
                ndf = pd.DataFrame({
                    col: df[col].value_counts() for col in cols
                })
                ndf.T.plot.bar(stacked=True)
            plt.title(f'{field}')
            plt.savefig(f'{field}.svg')
            pdf_writer.savefig()
            plt.close()

        sum_df = pd.concat(list_of_sums, axis=1, keys=data.keys())
        sum_df.fillna(0, inplace=True)
        sum_df.plot(kind='line')
        plt.savefig(f'sum.svg')
        pdf_writer.savefig()
        plt.close()
        d = pdf_writer.infodict()
        d['Title'] = 'Summary Variables Across Git Commits'
        d['Author'] = ''
        d['CreationDate'] = datetime.datetime.today()


if __name__ == '__main__':
    main()
