# Getting started

This website consists of isolated fully described projects, runnable locally
and also deployed as public examples on the [Anaconda Enterprise (AE)](https://www.anaconda.com/products/enterprise) platform, generously maintained by [Anaconda](https://www.anaconda.com).

## Run online

Examples that have online deployments, either as runnable read-only notebooks
or web applications, link these deployments at the top of their page.

## Run locally

All of the examples on this website have a link to download the project as a ZIP file.

To run an example locally, first install [anaconda-project](https://anaconda-project.readthedocs.io).

```bash
conda install anaconda-project=0.11.1
```

Once you unpack the project locally and visit that directory, you can see that each project directory has a text file `anaconda-project.yml` that defines an environment along with predefined commands that can be run in that environment. To run the default command defined in that project, do:

```bash
anaconda-project run
```

Running this command will install the dependencies for the particular project, then execute whatever the first command is. E.g. for a Panel dashboard, the default command could start a server (e.g. it will end with a statement like: `Bokeh app running at: http://localhost:5006/attractors_panel` ). You can then open the given link to see the running dashboard.

If the default command is a dashboard or app but you want to see or edit the individual steps involved, most projects also provide a predefined "notebook" command:

```bash
anaconda-project run notebook
```

Other commands might be defined in the `.yml` file as well, e.g. multiple notebooks, multiple dashboards, or other tasks.  You can also run any command you like in the provided environment, even if it's not defined in the `.yml` already. E.g. to launch a Jupyter notebook server for the entire directory, you can ask `anaconda-project` to run `jupyter notebook`, `jupyter lab`, or any other program:

```bash
anaconda-project run jupyter notebook
```

If you don’t want to use `anaconda-project` at all, you can create a regular
conda environment using:

```bash
conda env create --file anaconda-project.yml
```

Activate the environment (be sure to replace env-name with the real name
of the environment you created):

```bash
conda activate <env-name>
```

Then start a jupyter notebook as usual:

```bash
jupyter notebook
```

**NOTE:** If the notebook depends on data files, you will need to
download them explicitly if you don’t use `anaconda-project`, by
extracting the URLs defined in `anaconda-project.yml` and saving the
file(s) to this directory.
