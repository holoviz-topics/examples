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
MKL is used for better runtime performance in numpy operations, since we
use Numba for most of the internal computations it’s not as important.

3. Create the anaconda-project file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copy anaconda-project_template.yml to your own project, then just
replace NAME, DESC, MAINTAINERS and add the dependencies from step 2.

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
fetch the necessary code, checkout the specified git reference and
install the package.

4. Make sure it works
~~~~~~~~~~~~~~~~~~~~~

::

   anaconda-project run test

You might need to declare extra dependencies or add data downloads (see
bay_trimesh for an example of downloading data).

5. For remote or large data (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Make a smaller version of the data and put it in
``test_data/<project>``. This step allows automated tests to be run in a
practical way, exercising all of the example’s functionality but on a
feasible subset of the data involved.

6. If using intake (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The intake catalog should be at the top level of the project directory
and called “catalog.yml”.

::

   . bears
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

   . bears
   ├── anaconda-project.yml
   ├── bears.ipynb
   ├── catalog.yml
   └── data
       └── f890ce4d538240e87ede9d31a6541443
           └── data.csv

Make sure to make a test catalog and put it in ``test_data/catalog.yml``

7. Add the project to travis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Once everything is setup add your project to ``.travis.yml`` following
the pattern that the other projects use.

8. Upload to AE (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~
Once you have sucessfully created the new project, you can upload and
deploy it in Anaconda Enterprise:

::

   cd bears
   anaconda-project archive bears.zip

Then in the AE interface select “Create”, “Upload Project” and navigate
to the zip file. Once your project has been created, you can deploy it.
