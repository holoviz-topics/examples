# PyViz Topics Examples

Domain-specific narrative examples using multiple PyViz projects.
Isolated fully described projects, runnable locally and deployable
to Anaconda Enterprise. Each project is expected to have an author,
a created-date, and a canonical URL that can be sent around to send
someone to this particular project.

# Running Locally

To run an example locally first download it from https://examples.pyviz.org,
unzip it, and cd into it. Then install anaconda-project and
run the command defined in the anaconda-project file:

```bash
conda install anaconda-project=0.8.3
anaconda-project run
```

### Don't want to use anaconda-project?
If you don't want to use anaconda-project, you can create a regular
conda environment using:

```bash
conda env create --file anaconda-project.yml
```

Activate the environment (be sure to replace env-name with the real
name of the environment you created):

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
the file(s) to this directory.

# Uploading to AE

In addition to running examples locally you can upload and share them
using Anaconda Enterprise, which is the platform we use for publishing
our public deployments. If you've already installed anaconda-project,
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

Since the data involved is sometime rather large, full datasets
are not available on binder, but small versions of the datasets
are included in the environment so that you can test things out.
