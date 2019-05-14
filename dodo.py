import os

if "PYCTDEV_ECOSYSTEM" not in os.environ:
    os.environ["PYCTDEV_ECOSYSTEM"] = "conda"

from pyctdev import *  # noqa: api


def task_ecosystem_setup():
    """Set up conda with updated version, and yes set to always"""
    return {'actions': [
        "conda config --set always_yes True",
        "conda update conda",
        "conda install anaconda-project 'tornado<5.0'",
    ]}


def task_lint():
    """Generic lint command starting from within example directory"""
    return {'actions': [
        'anaconda-project prepare',
        'conda activate ./envs/default',
        'conda install -c pyviz nbsmoke pytest',
        'pytest --nbsmoke-lint -k *.ipynb --ignore envs',
    ]}


def task_test():
    """Generic lint command starting from within example directory"""
    return {'actions': [
        'anaconda-project prepare',
        'conda activate ./envs/default',
        'conda install -c pyviz nbsmoke pytest',
        'pytest --nbsmoke-run -k *.ipynb --ignore envs',
    ]}
