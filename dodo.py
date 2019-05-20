import os
from distutils.dir_util import copy_tree
import filecmp

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


name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'attractors'
}

def _prepare_paths(root, name, test_data):
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    test_data = test_data if os.path.isabs(test_data) else os.path.join(root, test_data)
    return {
        'real': os.path.join(root, name, 'data'),
        'test': os.path.join(test_data, name),
    }


def task_small_data_setup():
    """Copy small versions of the data from test_data"""

    def copy_test_data(root='', name='attractors', test_data='test_data'):
        print('Copying test data for {} ...'.format(name))
        paths = _prepare_paths(root, name, test_data)

        if not os.path.exists(paths['test']):
            raise ValueError("Fail: No test_data found for {} in {}".format(name, paths['test']))

        if os.path.exists(paths['real']) and os.listdir(paths['real']):
            matching_files = filecmp.dircmp(paths['test'], paths['real']).same_files
            if os.listdir(paths['real']) != matching_files:
                raise ValueError("Fail: Data files already exist in {}".format(paths['real']))
            else:
                print("Nothing to do: Test data already in {}".format(paths['real']))
                return
        copy_tree(paths['test'], paths['real'])
        print("Done!")

    return {'actions': [copy_test_data], 'params': [name_param]}


def task_small_data_cleanup():
    """Remove test_data from real data path"""

    def remove_test_data(root='', name='attractors', test_data='test_data'):
        print('Removing test data for {} ...'.format(name))
        paths = _prepare_paths(root, name, test_data)

        if not os.path.exists(paths['test']):
            print("Nothing to do: No test_data found for {} in {}".format(name, paths['test']))
            return

        if not os.path.exists(paths['real']):
            print("Nothing to do: No data found in {}".format(paths['real']))
            return

        if not os.listdir(paths['real']):
            print("No data found in {}, just removing empty dir".format(paths['real']))
            os.rmdir(paths['real'])
            return

        matching_files = filecmp.dircmp(paths['test'], paths['real']).same_files
        if os.listdir(paths['real']) != matching_files:
            raise ValueError("Fail: Data files at {} are not identical to test, so they shouldn't be deleted.".format(paths['real']))

        for filename in matching_files:
            os.remove(os.path.join(paths['real'], filename))

        os.rmdir(paths['real'])
        print("Done!")

    return {'actions': [remove_test_data], 'params': [name_param]}
