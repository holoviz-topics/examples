# PyViz Topics Examples

Examples of using Python data-visualization tools to explore or
illustrate particular types of data, research topics, or domain areas.
This site is meant to complement the library-specific examples
available from each tool's own site, and is thus particularly
appropriate for examples that use multiple tools, require large
datasets or specialized environments, or otherwise benefit from being
encapsulated here in a self-contained form that can be pointed to from
specific projects or domain-specific pages.

Each project here is meant to be isolated, fully described, runnable
locally, and deployable in running form on `examples.pyviz.org`. Each
project is expected to have an author, a created-date, and a canonical
URL that can be sent around to point someone to this particular
project.

# Running Locally

To run any of these examples locally, first download it from
https://examples.pyviz.org, unzip it, and cd into the resulting
directory. Then install
[anaconda-project](https://github.com/Anaconda-Platform/anaconda-project)
and run the command defined in the anaconda-project.yml file:

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

In addition to running examples locally, you can upload and share them
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

Since the data involved is sometimes rather large, full datasets are
not always available on binder, but at least a small version of the
dataset should always be included in the environment so that you can
test things out.
