Making a new project
====================

Once you have a notebook that you think it is ready to be its own
project you can follow these steps to get it set up. For the examples
I’ll use an example project named “bears”:

1. Move the notebook into a new directory with same name
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

   mkdir bears
   mv bears.ipynb ./bears
   cd bears

**NOTE:** If your project includes a file called index.ipynb, on the website,
that will be treated as a special landing page for the whole project. This
can be useful for projects with many notebooks that are best read in a particular
order.

2. Start specifying the package dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It can take a while to be sure you’ve captured every dependency, but I
usually start by using nbrr (``conda install -c conda-forge nbrr``)
which reads the notebooks and looks for dependencies:

.. code:: bash

   nbrr env --directory "." --name bears > anaconda-project.yml

**NOTE:** We tend to add ``nomkl`` to the list of dependencies to speed
up environment build times. But there is no rule that you must do this.
MKL is used for better runtime performance in numpy operations, but since we
use Numba for most of the internal computations it’s not as important
for these particular projects.

3. Create the anaconda-project file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copy template/.projectignore and  template/anaconda-project.yml to your own project,
then just replace NAME, DESC, MAINTAINERS, CREATED, LABELS and add the dependencies
from step 2.

**Labels**
Labels are used to give others a quick sense of what packages a particular project
showcases. They are also used to indicate if a project depends on channels other
than defaults. For example:

.. code:: yaml

   labels:
      - channel_conda-forge
      - datashader
      - panel

**Commands**

Once the dependencies are sorted, make sure to add the appropriate commands.
If your project contains notebooks, then add a ``notebooks`` command:

.. code:: yaml

   commands:
      notebooks:
         notebook: .

If your project also contains servable panel dashboards then suffix them with
"_panel" and add the following to the command dictionary:

.. code:: yaml

   dashboard:
      unix: panel serve *_panel.ipynb
      supports_http_options: true

**NOTE**: If your project contains an index.ipynb which illustrates the best
path through the notebooks, then instead of the notebooks command above, add
the following:

.. code:: yaml

   notebook:
      notebook: index.ipynb

**Depending on unreleased package versions**

In some cases you may have a notebook that relies on a development
version of a package, or perhaps you wish to refer to a particular git
tag that has not made it into a released version. In this case, you can
add a ``pip`` subsection to your list of dependencies of the form:

.. code:: yaml

   - pip:
     - git+https://github.com/ORG/REPO.git@REF#egg=PACKAGE

Where ``ORG`` is the GitHub organization (or username), ``REPO`` is the name of the
git repository, ``REF`` is a git reference (e.g a git tag or simply
``main`` to point to the very latest version) and ``PACKAGE`` is the
name of the corresponding Python package. This syntax will use pip to
fetch the necessary code, check out the specified git reference, and
install the package.

**Special website building options**

If you'd like certain notebooks to be rendered on the website, but not linked
from the main page (perhaps they are linked from other notebooks), then add
the filenames to a list of ``orphans``:

.. code:: yaml

   orphans:
      - appendix.ipynb

If you'd like notebooks to be skipped entirely when building the website, use the
``skip`` option:

.. code:: yaml

   skip:
      - data_prep.ipynb

4. Make sure it works
~~~~~~~~~~~~~~~~~~~~~

::

   anaconda-project run test

You might need to declare extra dependencies or add data downloads (see
bay_trimesh for an example of downloading data).

5. For remote or large data (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unless your data is small enough that it can be processed on every
continuous-integration build, you should make a much smaller version
of the data and put it in
``test_data/bears``. This step allows automated tests to be run in a
practical way, exercising all of the example’s functionality but on a
feasible subset of the data involved.

6. If using intake (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The intake catalog should be at the top level of the project directory
and called “catalog.yml”.

::

   bears
   ├── anaconda-project.yml
   ├── bears.ipynb
   └── catalog.yml

If using the intake cache, point the cache to the data dir in the
project by defining the INTAKE_CACHE_DIR variable in the
anaconda-project file:

.. code:: yaml

   variables:
     INTAKE_CACHE_DIR: data

This way when the user runs the notebook, they will still be able to see
the data from within the project directory:

::

   bears
   ├── anaconda-project.yml
   ├── bears.ipynb
   ├── catalog.yml
   └── data
       └── f890ce4d538240e87ede9d31a6541443
           └── data.csv

Make sure to make a test catalog and put it in ``test_data/catalog.yml``

7. Add thumbnails (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, when the website is built on GitHub Actions, a thumbnail is generated for each
project. The thumbnail is taken from the first image that the notebook produces.
If you'd rather use a different image for a particular notebook: name the image to
match the name of the notebook and include it in a "thumbnails" directory within
your project. This image must be a png and have the extension ".png".

Uploading to AE (admin only)
============================

If you are an examples.pyviz administrator, you can now upload and deploy
the project in Anaconda Enterprise, which is the server we use to host
our public Python-backed examples:

::

   cd bears
   anaconda-project archive bears.zip

Then in the AE interface select “Create”, then “Upload Project” and navigate
to the zip file. Once your project has been created, you can deploy it.

**NOTE:** Dashboard commands should be deployed at <project>.pyviz.demo.anaconda.com
and notebooks command at <project>-notebooks.pyviz.demo.anaconda.com

If you are not an administrator, just submit the PR, and one of the
administrators will launch the project when the PR is merged.

Building a project for the website (admin only)
===============================================

Most of the projects are built for the website automatically when a
special commit message is passed to GitHub Actions. The commit message
should include the word "build" and the name of the desired project, as in:

::

   git commit -m "Fixing typo [build:bears]" files

This should trigger a GitHub Actions job that downloads the real data,
sets up the environment, archives the project, then uses nbsite to
generate a thumbnail and evaluated versions of all the notebooks in
the project.  Those assets are then stored on the ``evaluated`` branch
of the github repo, and the dev version of the website should be
updated.  You can track the progress of this job using the Travis CI
link on the Datashader homepage, and when the job completes you should
be able to see the results at https://pyviz-dev.github.io/examples/ .

If everything looks good, an administrator can then re-build the release version
of the website `website <https://examples.pyviz.org>`_ by pushing
a commit (empty if necessary) that contains the text
``build:website_release``.

::

   git commit --allow-empty -m "[build:website_release]"

The evaluated HTML versions of each notebook will then be deployed on the
``gh-pages`` branch, and should then appear on the public website.


Building a project locally
==========================

In a minority of cases, the project takes so long to build or the data are
so large, that it isn't feasible to build the website version of the project
on Travis CI. In those cases, the project maintainer is responsible for
running the build commands locally and committing the results to the
``evaluated`` branch. To build the project follow these steps:

::

   export DIR=bears
   doit archive_project --name $DIR
   anaconda-project prepare --directory $DIR
   conda activate $DIR/envs/default && pip install pyctdev
   conda install -y -c pyviz/label/dev nbsite sphinx_pyviz_theme selenium phantomjs lxml
   doit build_project --name $DIR

You should end up with a new directory in the doc dir with the same name
as your project. The structure of that directory should be as follows:

::

   doc/bears
   ├── bears.ipynb
   ├── bears.rst
   ├── bears.zip
   └── thumbnails
      └── bears.png

Commit only that doc/bears directory to the ``evaluated`` branch. The easiest way to
do that is by moving it to a temporary directory, checking out the ``evaluated``
branch and then moving it back:

::

   mv ./doc/$DIR ./tmp
   git checkout evaluated
   git pull
   if [ -e  ./doc/$DIR ]; then rm -rf ./doc/$DIR; fi
   mkdir ./doc/$DIR
   mv ./tmp/* ./doc/$DIR
   git add ./doc/$DIR
   git commit -m "adding $DIR"
   git push
