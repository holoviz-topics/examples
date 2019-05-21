import os
from distutils.dir_util import copy_tree
import filecmp
import shutil

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

# From https://stackoverflow.com/a/24860799/4021797
class dircmp(filecmp.dircmp):
    """
    Compare the content of dir1 and dir2. In contrast with filecmp.dircmp, this
    subclass compares the content of files with the same path.
    """
    def phase3(self):
        """
        Find out differences between common files.
        Ensure we are using content comparison with shallow=False.
        """
        fcomp = filecmp.cmpfiles(self.left, self.right, self.common_files,
                                 shallow=False)
        self.same_files, self.diff_files, self.funny_files = fcomp

def is_same(dir1, dir2):
    """
    Compare two directory trees content.
    Return False if they differ, True is they are the same.
    """
    compared = dircmp(dir1, dir2)
    if (compared.left_only or compared.right_only or compared.diff_files
        or compared.funny_files):
        return False
    for subdir in compared.common_dirs:
        if not is_same(os.path.join(dir1, subdir), os.path.join(dir2, subdir)):
            return False
    return True


def task_small_data_setup():
    """Copy small versions of the data from test_data"""

    def copy_test_data(root='', name='attractors', test_data='test_data'):
        print('Copying test data for {} ...'.format(name))
        paths = _prepare_paths(root, name, test_data)

        if not os.path.exists(paths['test']):
            print("Warning: No test_data found for {} in {}".format(name, paths['test']))
            return

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

        if not is_same(paths['test'], paths['real']):
            raise ValueError("Fail: Data files at {} are not identical to test, so they shouldn't be deleted.".format(paths['real']))

        shutil.rmtree(paths['real'])
        print("Done!")

    return {'actions': [remove_test_data], 'params': [name_param]}
