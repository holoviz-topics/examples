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
then just replace NAME, DESC, MAINTAINERS and add the dependencies from step 2.

In some cases you may have a notebook that relies on a development
version of a package, or perhaps you wish to refer to a particular git
tag that has not made it into a released version. In this case, you can
add a ``pip`` subsection to your list of dependencies of the form:

.. code:: yaml

   - pip:
     - git+https://github.com/USERNAME/REPO.git@REF#egg=PACKAGE

Where ``USERNAME`` is the GitHub username, ``REPO`` is the name of the
git repository, ``REF`` is a git reference (e.g a git tag or simply
``master`` to point to the very latest version) and ``PACKAGE`` is the
name of the corresponding Python package. This syntax will use pip to
fetch the necessary code, check out the specified git reference, and
install the package.

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

7. Add the project to travis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Once everything is set up add your project to ``.travis.yml`` following
the pattern that the other projects use. There are two places where you will
have to put it. One for testing:

.. code:: yaml

   - <<: *test_project
   env: DIR=bear

And one for building the project for the website:

.. code:: yaml

   - <<: *build_project
   env: DIR=bear

**NOTE:** If your project takes a very long time (~15min) to run or requires very
large data (~3GB), you might want to build the project locally on your machine
and check in the result rather than building on CI. In this case replace
``build_project`` above with ``local_project`` and follow the steps under "Building
a project locally"

Uploading to AE
===============
You can upload and deploy any project in Anaconda Enterprise,
which is the server we use to host our public Python-backed examples:

::

   cd bears
   anaconda-project archive bears.zip

Then in the AE interface select “Create”, then “Upload Project” and navigate
to the zip file. Once your project has been created, you can deploy it.

Building a project for the website
==================================
Most of the projects are built for the website when a special commit
message is passed to Travis CI. The commit message should include the
word "build" and the name of the desired project for example:
``commit -m "Fixing typo [build:bears]"``. If step 7 was done properly,
then this should trigger a Travis CI job that downloads the real data,
sets up the environment, archives the project, then uses nbsite to generate
a thumbnail and evaluated versions of all the notebooks in the project.
Those assets are then stored on the ``evaluated`` branch of the github repo.

After that job completes, another job will start that builds html versions
of all the saved notebooks deploys them to the ``gh-pages`` branch. After that
job has completed, the new content will be visible on the site.

Building a project locally
~~~~~~~~~~~~~~~~~~~~~~~~~~
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
   if ! [ -e  ./doc/$DIR ]; then mkdir ./doc/$DIR; fi
   mv ./tmp/* ./doc/$DIR
   git add ./doc/$DIR
   git commit -m "adding $DIR [build:release]"
   git push

That commit will cause the index page of the website to be regenerated, and
the website to be re-deployed.
