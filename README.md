# PyViz Topics Examples

This project contains self-contained, typically domain-specific 
examples illustrating how to use one or more PyViz tools to 
explore data or understand a topic. Each project is fully
reproducible by downloading and running it locally, and can also
be deployed automatically using an Anaconda Enterprise server.

# Running Locally

To run an example locally first download it from https://examples.pyviz.org,
unzip it, and cd into it. Then install 
[anaconda-project](https://anaconda-project.readthedocs.io) and
run the command defined in the anaconda-project.yml file:

```bash
conda install anaconda-project=0.8.3
anaconda-project run
```

### Don't want to use anaconda-project?
anaconda-project is a handy way to automate a project, but if you 
don't want to use it, you can create a regular conda environment using:

```bash
conda env create --file anaconda-project.yml
```

Then activate the environment (be sure to replace env-name with the 
real name of the environment you created):

```bash
conda activate <env-name>
```

Then start a jupyter notebook as usual:

```bash
jupyter notebook
```

**NOTE:** If the notebook depends on data files, you will need to
download them explicitly if you don't use anaconda-project, by
extracting the URLs defined in anaconda-project.yml and saving
the file(s) to the appropriate location in this directory.

# Uploading to AE

In addition to running examples locally you can upload and share them
using Anaconda Enterprise, which is the platform we use for publishing
the public deployments. If you've already installed anaconda-project,
then for an example named "bears" just do:

```
cd bears
anaconda-project archive bears.zip
```

Then in the AE interface select "Create", "Upload Project" and navigate
to the zip file. Once your project has been created, you can deploy it.

# Running on Binder

To experiment in a running environment, you can use binder:

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/pyviz-topics/examples/master)

Since the data involved is sometimes rather large, full datasets
are not available on binder, but small versions of the datasets
are included in the environment so that you can test things out.
