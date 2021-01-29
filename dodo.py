import os
import glob
from distutils.dir_util import copy_tree
import filecmp
import shutil

if "PYCTDEV_ECOSYSTEM" not in os.environ:
    os.environ["PYCTDEV_ECOSYSTEM"] = "conda"

try:
    from pyctdev import *  # noqa: api
except:
    print('No pyctdev found')

DEFAULT_EXCLUDE = ['doc', 'envs', 'test_data', 'builtdocs', 'template', *glob.glob( '.*'), *glob.glob( '_*')]

def task_ecosystem_setup():
    """Set up conda with updated version, and yes set to always"""
    return {'actions': [
        "conda config --set always_yes True",
        "conda update conda",
        "conda install anaconda-project=0.8.3",
    ]}


name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'all'
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

def all_project_names(root):
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    return [f for f in next(os.walk('.'))[1] if f not in DEFAULT_EXCLUDE]

def task_small_data_setup():
    """Copy small versions of the data from test_data"""

    def copy_test_data(root='', name='all', test_data='test_data', cat_filename='catalog.yml'):
        if name == 'all':
            print('Setting up test data for all the projects')
            for name in all_project_names(root):
                copy_test_data(root, name, test_data, cat_filename)
            return

        print('Setting up test data for {}:'.format(name))

        paths = _prepare_paths(root, name, test_data, cat_filename)
        has_catalog = os.path.exists(paths['cat_real'])

        if not os.path.exists(paths['test']) or not os.listdir(paths['test']):
            if has_catalog:
                raise ValueError("Fail: {} has no test_data".format(name))
            else:
                print("  Nothing to do: Test data not found for {}".format(name))
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

    def remove_test_data(root='', name='all', test_data='test_data',
                         cat_filename='catalog.yml'):

        if name == 'all':
            print('Cleaning up test data for all the projects')
            for name in all_project_names(root):
                remove_test_data(root, name, test_data, cat_filename)
            return

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

def task_archive_project():
    """Archive project with given name, assumes anaconda-project is in env"""

    def archive_project(root='', name='all'):
        import subprocess
        from shutil import copyfile
        from yaml import safe_load, safe_dump

        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            print(f'Archving {project}...')
            readme_path = os.path.join(project, 'README.md')
            if not os.path.exists(readme_path):
                copyfile('README.md', readme_path)

            # stripping extra fields out of anaconda_project to make them more legible
            path = os.path.join(project, 'anaconda-project.yml')
            tmp_path = f'{project}_anaconda-project.yml'
            copyfile(path, tmp_path)
            with open(path, 'r') as f:
                spec = safe_load(f)

            # special fields that anaconda-project doesn't know about
            spec.pop('labels', '')
            spec.pop('maintainers', '')
            spec.pop('created', '')
            spec.pop('skip', '')
            spec.pop('orphans', '')
            spec.pop('user_fields', '')

            # commands and envs that users don't need
            spec['commands'].pop('test', '')
            spec['commands'].pop('lint', '')
            spec['env_specs'].pop('test', '')

            # get rid of any empty fields
            spec = {k: v for k, v in spec.items() if bool(v)}

            with open(path, 'w') as f:
                safe_dump(spec, f, default_flow_style=False, sort_keys=False)

            doc_path = os.path.join('doc', project)
            if not os.path.exists(doc_path):
                os.mkdir(doc_path)

            subprocess.run(["anaconda-project", "archive", "--directory", f"{project}", f"doc/{project}/{project}.zip"])
            copyfile(tmp_path, path)
            os.remove(tmp_path)

    return {'actions': [archive_project], 'params': [name_param]}

def task_build_project():
    """Build project with given name, assumes you are in an environment with required dependencies"""

    def move_thumbnails(name):
        from shutil import copyfile
        src_dir = os.path.join(name, 'thumbnails')
        dst_dir = os.path.join('doc', name, 'thumbnails')
        if os.path.exists(src_dir):
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            for item in os.listdir(src_dir):
                src = os.path.join(src_dir, item)
                dst = os.path.join(dst_dir, item)
                copyfile(src, dst)

    return {'actions': [
        move_thumbnails,
        "DIR=%(name)s nbsite build --examples .",
    ], 'params': [name_param]}

def task_build_website():
    """Build website, assumes you are in an environment with required dependencies and have build projects"""

    def make_assets():
        from shutil import copyfile
        if not os.path.exists('assets'):
            os.mkdir('assets')
        for name in all_project_names(''):
            archived_project = os.path.join('doc', name, f'{name}.zip')
            if os.path.exists(archived_project):
                dst = os.path.join('assets',  f'{name}.zip')
                copyfile(archived_project, dst)
            assets_dir = os.path.join(name, 'assets')
            if os.path.exists(assets_dir):
                for item in os.listdir(assets_dir):
                    src = os.path.join(assets_dir, item)
                    dst = os.path.join('assets', item)
                    copyfile(src, dst)

    return {'actions': [
        make_assets,
        "rm doc/*/*.rst",
        "nbsite build --examples .",
    ]}

def task_index_symlinks():
    "Create relative symlinks to provide short, convenient project URLS"

    def generate_index_symlinks():
        cwd = os.getcwd()
        for name in all_project_names(''):
            project_path = os.path.abspath(os.path.join('.', 'builtdocs', name))
            try:
                os.chdir(project_path)
                listing = os.listdir(project_path)
                if 'index.html' not in listing:
                    os.symlink('./%s.html' % name, './index.html')
                    print('Created symlink for %s' % name)
                os.chdir(cwd)
            except Exception as e:
                print(str(e))
        os.chdir(cwd)
    return {'actions':[generate_index_symlinks]}


redirect_template = """
<!DOCTYPE html>
<html>
   <head>
      <title>{name} redirect</title>
      <meta http-equiv = "refresh" content = "0; url = https://examples.pyviz.org/{name}/{name}.html" />
   </head>
</html>
"""


def task_index_redirects():
    """
    Create redirect pages to provide short, convenient project URLS.
    Should behave the same as task_index_symlinks but can be used where
    symlinks are not suitable.

    """
    def write_redirect(name):
        with open('./index.html', 'w') as f:
            contents = redirect_template.format(name=name)
            f.write(contents)
            print('Created relative HTML redirect for %s' % name)

    def generate_index_redirect():
        cwd = os.getcwd()
        for name in all_project_names(''):
            project_path = os.path.abspath(os.path.join('.', 'builtdocs', name))
            try:
                os.chdir(project_path)
                listing = os.listdir(project_path)
                if 'index.html' not in listing:
                    write_redirect(name)
                os.chdir(cwd)
            except Exception as e:
                print(str(e))
        os.chdir(cwd)
    return {'actions':[generate_index_redirect]}


def task_changes_in_dir():
    def changes_in_dir(name, filepath='.diff'):
        if not dir_is_project(name):
            return False
        with open(filepath) as f:
            paths = f.readlines()
        dirs = list(set(os.path.dirname(path) for path in paths))
        return name in dirs

    def dir_is_project(name):
        return os.path.exists(os.path.join(name, 'anaconda-project.yml'))

    return {'actions': [changes_in_dir], 'params': [name_param]}

def task_test_project():
    return {'actions': [
        ("if ! anaconda-project list-downloads --directory %(name)s | grep -q 'No downloads'; then\n"
        "  if ! [ -d %(name)s/data ]; then\n"
        "    echo 'FAIL needs data and no test data found' && exit 1;\n"
        "  fi;\n"
        "fi\n"),
        "anaconda-project run --directory %(name)s lint",
        "anaconda-project run --directory %(name)s test",
    ], 'params': [name_param]}

def task_project_in_travis():
    def project_in_travis(name, travis_file='.travis.yml'):
        with open(travis_file) as f:
            contents = f.read()
        if contents.count(name) != 2:
            raise ValueError("Fail: Don't forget to include {} in {} test "
                             "and build sections.".format(name, travis_file))
        print("Success: {} is included in {}".format(name, travis_file))
        return

    return {'actions': [project_in_travis], 'params': [name_param]}
