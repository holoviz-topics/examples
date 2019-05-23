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
        "conda install anaconda-project 'tornado<5.0' pyyaml",
    ]}


name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'attractors'
}

def _prepare_paths(root, name, test_data, filename='catalog.yml'):
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    test_data = test_data if os.path.isabs(test_data) else os.path.join(root, test_data)
    test_path = os.path.join(test_data, name)
    project_path = os.path.join(root, name)
    return {
        'project': project_path,
        'real': os.path.join(project_path, 'data'),
        'test': test_path,
        'cat_real': os.path.join(project_path, filename),
        'cat_test': os.path.join(test_path, filename),
        'cat_tmp': os.path.join(project_path, 'tmp_' + filename),
    }

def _has_download(path, filename='anaconda-project.yml'):
    import yaml
    with open(os.path.join(path, filename), 'r') as f:
        text = yaml.load(f, Loader=yaml.FullLoader)
        return bool(text.get('downloads', {}))

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

    def copy_test_data(root='', name='attractors', test_data='test_data', cat_filename='catalog.yml'):
        print('Setting up test data for {}:'.format(name))

        paths = _prepare_paths(root, name, test_data, cat_filename)
        has_catalog = os.path.exists(paths['cat_real'])
        has_download = _has_download(paths['project'])

        if not os.path.exists(paths['test']) or not os.listdir(paths['test']):
            if has_catalog or has_download:
                raise ValueError("Fail: {} has no test_data".format(name))
            else:
                print("  Nothing to do: Test data not needed for {}".format(name))
                print("Done!")
                return

        if has_catalog and not os.path.exists(paths['cat_test']):
            raise ValueError("Fail: {} contains intake catalog, but "
                             "no catalog found in test_data".format(name))

        if has_catalog:
            print('* Copying intake catalog ...')

            # move real catalog file to tmp if tmp doesn't exist
            if os.path.exists(paths['cat_tmp']):
                raise ValueError("Fail: Temp file already exists - try 'doit small_data_cleanup'")
            os.rename(paths['cat_real'], paths['cat_tmp'])

            # move test catalog to project directory
            shutil.copyfile(paths['cat_test'], paths['cat_real'])
            print('  Intake catalog successfully copied')

        print('* Copying test data ...')
        if os.path.exists(paths['real']) and os.listdir(paths['real']):
            matching_files = filecmp.dircmp(paths['test'], paths['real']).same_files
            if os.listdir(paths['real']) != matching_files:
                raise ValueError("Fail: Data files already exist in {}".format(paths['real']))
            else:
                print("  Nothing to do: Test data already in {}".format(paths['real']))
        else:
            copy_tree(paths['test'], paths['real'])
            print('  Test data sucessfully copied')

        print("Done!")

    return {'actions': [copy_test_data], 'params': [name_param]}


def task_small_data_cleanup():
    """Remove test_data from real data path"""

    def remove_test_data(root='', name='attractors', test_data='test_data',
                         cat_filename='catalog.yml'):
        print('Cleaning up test data for {}:'.format(name))
        paths = _prepare_paths(root, name, test_data, cat_filename)

        if os.path.exists(paths['cat_real']):
            print("* Replacing intake catalog ...")

            if not os.path.exists(paths['cat_tmp']):
                print("  Nothing to do: No temp file found. Use git status to "
                      "check that you have the real catalog at {}".format(paths['cat_real']))
            else:
                os.remove(paths['cat_real'])
                os.rename(paths['cat_tmp'], paths['cat_real'])
                print('  Intake catalog successfully cleaned')

        print('* Removing test data ...')

        if not os.path.exists(paths['test']):
            print("  Nothing to do: No test_data found for {} in {}".format(name, paths['test']))
        elif not os.path.exists(paths['real']):
            print("  Nothing to do: No data found in {}".format(paths['real']))
        elif not os.listdir(paths['real']):
            os.rmdir(paths['real'])
            print("  No data found in {}, just removed empty dir".format(paths['real']))
        elif not is_same(paths['test'], paths['real']):
            raise ValueError("Fail: Data files at {} are not identical to test, "
                             "so they shouldn't be deleted.".format(paths['real']))
        else:
            shutil.rmtree(paths['real'])
            print('  Test data successfully removed')

        print("Done!")

    return {'actions': [remove_test_data], 'params': [name_param]}
