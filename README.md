# PyViz Topics Examples

Domain-specific narrative examples using multiple PyViz projects.
Isolated fully described projects, runnable locally and deployable
to Anaconda Enterprise. Each project is expected to have an author,
a created-date, and a canonical URL that can be sent around to send
someone to this particular project.

# Running Locally

To run an example locally install anaconda-project and run the
command defined in the anaconda-project file:

```bash
conda install anaconda-project tornado<5.0
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
