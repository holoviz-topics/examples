# Getting started

This website consists of isolated fully described projects, runnable locally
and also deployed as public examples on the [Anaconda Enterprise (AE)](https://www.anaconda.com/products/enterprise) platform, generously maintained by [Anaconda](https://www.anaconda.com).

## Run online

Examples that have an online deployment of their web application link it
at the top of their page.

## Run locally

All of the examples on this website have a link to download the project as a ZIP file.

To run an example locally, first install [pixi](https://pixi.sh).

Once you unpack the project locally and visit that directory, you can see that each project directory has a `pixi.toml` file that defines an environment along with predefined tasks that can be run in that environment, and a `pixi.lock` file that pins the exact versions of the dependencies. To open the notebooks of the project, do:

```bash
pixi run notebook
```

Running this command will install the dependencies for the particular project, download the data the notebooks need, and start Jupyter.

Projects that include a Panel dashboard also provide a `dashboard` task, which starts a server (e.g. it will end with a statement like: `Bokeh app running at: http://localhost:5006/attractors_panel`). You can then open the given link to see the running dashboard:

```bash
pixi run dashboard
```

Other tasks might be defined in `pixi.toml` as well, e.g. multiple notebooks, multiple dashboards, or other tasks. To list them, run:

```bash
pixi task list
```

You can also run any command you like in the provided environment, even if it's not defined in `pixi.toml` already. E.g. to launch a Jupyter notebook server for the entire directory, you can run `jupyter notebook`, or any other program installed in the environment:

```bash
pixi run jupyter notebook
```

To work in the environment from your shell, activate it with:

```bash
pixi shell
```

**NOTE:** If the notebook depends on data files and you start Jupyter without the `notebook` task, run `pixi run download` first to fetch them.
