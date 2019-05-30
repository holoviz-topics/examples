***************
Getting Started
***************

This website consists of isolated fully described projects, runnable locally
and deployable to Anaconda Enterprise.

Download a Project
==================
All of the examples on this website have a link to download the project.
A list of all the downloads can also be found on the `downloads page
<downloads>`_.

Once you have downloaded a project you can run it locally or on AE.

Run Locally
===========

To run an example locally install anaconda-project and run the command
defined in the anaconda-project file:

.. code:: bash

   conda install anaconda-project tornado<5.0
   anaconda-project run

Don’t want to use anaconda-project?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you don’t want to use anaconda-project, you can create a regular
conda environment using:

.. code:: bash

   conda env create --file anaconda-project.yml

Activate the environment (be sure to replace env-name with the real name
of the environment you created):

.. code:: bash

   conda activate <env-name>

Then start a jupyter notebook as usual:

.. code:: bash

   jupyter notebook

**NOTE:** If the notebook depends on data files, you will need to
download them explicitly if you don’t use anaconda-project, by
extracting the URLs defined in anaconda-project.yml and saving the
file(s) to this directory.

Run on AE
=========
In addition to running examples locally you can upload and share them
using Anaconda Enterprise, which is the platform we use for publishing
our public deployments. If you’ve already installed anaconda-project,
then for an example named “bears” just do:

::

   cd bears
   anaconda-project archive bears.zip

Then in the AE interface select “Create”, “Upload Project” and navigate
to the zip file. Once your project has been created, you can deploy it.

.. toctree::
    :hidden:
    :maxdepth: 2

    Home <gallery>
    Getting Started <self>
    Developer Guide <developer_guide>
    Downloads <downloads>
    About <about>
