**********
User Guide
**********

This website consists of isolated fully described projects, runnable locally
and also deployed as public examples using Anaconda Enterprise (AE).

Download a Project
==================
All of the examples on this website have a link to download the project.
Once you have downloaded a project you can run it locally or on AE.

Run Locally
===========

To run an example locally first install anaconda-project.

.. code:: bash
   
   conda install anaconda-project=0.8.3

Each project folder has a file `anaconda-project.yml`, which can be run as a command.

.. code:: bash

   anaconda-project run

Running this command will will install the dependencies for the particular project and start a Bokeh server (e.g. it will end with the statement : `Bokeh app running at: http://localhost:5006/attractors_panel` ). This link can be used to see how the dashboard for the particular example works. 

**Note**: This approach will not provide an environment where you can change the code in the notebook to see what each bit is doing.

If instead you would like to run a notebook, then do:

.. code:: bash

   anaconda-project run notebook

Don’t want to use anaconda-project or want to modify the code to see how it works?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
