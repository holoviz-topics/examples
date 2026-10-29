# Contributing

You can contribute to this website either by submitting a new project
or by updating an existing one.

The steps to contribute are described on this page further down. For an easy introduction to how to contribute, you  can watch this 16-minute video:

<div align="right" style="margin-right:10% margin-left:10%;">
    <iframe width="100%" height="400" src="https://www.youtube.com/embed/r-9MF0sx_nA" title="Holoviz examples: Contribute to the examples website" frameborder="0" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
</div>

Before you submit any contribution however, you should create an `Issue` in the [project repository](https://github.com/holoviz-topics/examples) 
detailing the changes you want to make to an existing example,
or the details of the new example you want to create.

## Setup

We **strongly recommend** you to set up the managing environment to be able
to validate and test a project locally, before submitting it to
this repository:

### Fork and Clone the repository

Create a fork of the repository and then clone your own fork via:

```bash
 git clone git@github.com:<YourUsername>/holoviz-topics-examples.git
```

### Install pixi

Install [pixi](https://pixi.sh), which manages the environment of every project.
The repository scripts used below only need Python 3.11 or later.

Then add the repository as your `origin` with the following commands:

<strong>SSH</strong>

```bash
git remote add origin git@github.com:holoviz-topics/examples.git
```

<strong>HTTPS</strong>

```bash
git remote add origin https://github.com/holoviz-topics/examples.git
```

(add-a-project)=
## Add a project

Once you have an example (one or more notebook(s)) that you think is ready to be
shared on this website follow these steps to set it up correctly.

### 1. Create the project directory

Its name must be all lower-case, only including underscore as
special characters. This name is important as you will have to
re-use it as-is in multiple places.

### 2. Use the template

Copy the template project file `template/pixi.toml` to your project and set
`name` in its `[workspace]` table to your project directory name.
You will use this file as a basis to build your own project.
You can further explore the `template` example folder, which houses a fully executable project.

### 3. Move your notebook(s) to your project directory

If your project has a single notebook it must share the same name
as your project directory. If your project has more than one notebooks,
it must have an `index.ipynb` notebook that will link to your other notebooks.
Every displayed notebook must start with a 1st level heading, e.g. `# A title`.

Your project may have notebooks that are not meant to be displayed on the website,
such as pre-processing notebooks. See the `notebooks_to_skip` option in `[tool.metadata]` to declare them:

```toml
[tool.metadata]
notebooks_to_skip = ["data_prep.ipynb"]
```

Your notebooks should be committed **without output**. The system will be in charge
of executing your notebooks based on your project characteristics, to
build the documentation.

In some cases it is impossible for the system to execute your notebooks. This
happens for instance if your notebooks are too long to run, require too much
data, require special hardware, etc. In those cases, you should instead commit
your notebooks *with output* and set `skip_notebooks_evaluation` to `true`
in `[tool.metadata]`.

### 4. List the dependencies

Add to the `[dependencies]` table of your `pixi.toml` file the dependencies required to run
your notebook(s) and application(s), e.g. with `pixi add <package>` from your project directory.
The recommended practice is to pin all your dependencies using either `>=` (for easier updates) or `==`.

### 5. Manage the data

There are multiple ways to manage the data required to run a project:

- the project does not ingest any data, as it either generates it on the fly
or as it just provides written indications on how to get it: set `no_data_ingestion`
to `true` in `[tool.metadata]`
- the project needs to download some data, you have two options:
   - define a `download` task that saves the data in the `data/` subfolder and declares it in `outputs`,
   and make the `notebook`, `dashboard` and `test` tasks depend on it. See `template/pixi.toml` for an example.
   - or, create an Intake catalog and load it in your notebooks, the catalog must be named
   `catalog.yml` and be at the root of your project
- the project relies on some very light data, then it can be committed to the repository
as is. It must be stored in a `data/` subfolder of your project

When using an Intake catalog, point the cache to the data dir in the
project by defining the `INTAKE_CACHE_DIR` variable in the
`pixi.toml` file:

```toml
[activation.env]
INTAKE_CACHE_DIR = "data"
```

This way when the user runs the notebook, they will still be able to see
the data from within the project directory.

If your data changes, bump `data_version` in `[tool.metadata]` so the CI downloads it again
instead of using its cached copy.

### 6. Testing

Your project will be automatically tested by the system:

- the code of the notebooks will be linted with `ruff check`, run by `pre-commit`
- the notebooks will be executed with `nbval` by the `test` task of the `test` environment, the tests failing if an error occurs during their execution

If you project has some special testing needs, you can change the `test` task in the
`[feature.test.tasks]` table of your `pixi.toml` file. You can also declare testing dependencies
in the `[feature.test.dependencies]` table.

### 7. Complete the project metadata

Fill in the `[tool.metadata]` table of your `pixi.toml` file, which is used to display your project on the website:

- `created`: the date the project was created, as `YYYY-MM-DD`
- `maintainers`: the GitHub handles of the project maintainers
- `categories`: one or more of the categories of the website, e.g. `Geospatial`
- `labels`: the main libraries used in the project
- `description`: a short description of the project
- `title` (optional): the project title, by default derived from the project name

If your project has a Panel dashboard, add a `dashboard` task serving it with
`panel serve --rest-session-info --session-history -1 <notebook>`.

### 8. Add a thumbnail

Create a nice but lightweight PNG thumbnail (maximum size of 1MB) with an aspect ratio between 0.9 and 1.5.
Name it as your project if you have only one notebook or as `index.png` if you have multiple notebooks,
and save it in the `thumbnails` subfolder of your project.

### 9. Locking

You must lock your project to capture the full set of dependencies that are required to execute it.

From your project directory, run:

```bash
pixi lock
```

and commit the resulting `pixi.lock` file.

### 10. Make sure it works

If you have declared tasks run them to check that they work as expected,
as this is what the users of your project will ultimately use. From your project directory, run:

```bash
pixi run <taskname>
```

(build-the-site-locally)=
### 11. Build the site locally

Build the site locally to make sure it looks the way you expect when it is eventually deployed.

The scripts below only consider the files tracked by git, so first commit your project
(or at least `git add` it). Then, from the root directory:

1. Run:
      ```bash
      python scripts/build_project.py <projectname>
      ```

This command executes the notebooks of your project into `./doc/gallery/<projectname>`.

2. Run:
      ```bash
      pixi run -e docs docs-prepare
      pixi run -e docs docs-build
      ```

These commands copy the other files needed to build the docs (thumbnails, archive, assets, etc.) into `./doc/gallery/<projectname>`, and build the docs with Sphinx.

3. Open the built site on your web browser via: `./builtdocs/index.html`

4. Clean up this process by removing the `./doc/gallery/` and `./builtdocs/` folders.

### 12. Validate and test

After viewing the built site, you should run locally the steps that are going to be run on the CI.

Start by validating that your project is well specified by running, from the root directory:

```bash
python scripts/validate_project.py <projectname>
```

Update your project until you have no validation *warning* left.

Now you will test your project by running, from your project directory:

```bash
pixi run -e test test
```

Update your project until the tests pass.

Finally, lint the notebooks by running `pre-commit run --all-files` from the root directory.

### 13. Open a Pull Request

Open a Pull Request that adds your project to the repository. The CI
will take care of validating, testing and building it. If these steps
succeed the developer website will be built and you will be able to check
a rendered version of your project at https://holoviz-dev.github.io/examples/.

When the review of your Pull Request is completed and it is merged, the CI
will then take care of updating the main site.

## Update a project

To update an existing project, follow these simple steps.

### 1. Choose the project

Navigate to the selected project directory and execute the following command:

``` bash
pixi run notebook
```

This command opens the project notebook(s) in your web browser.
Run `pixi task list` to see the other tasks of the project.

Remember to commit the updated notebooks **without output.**

### 2. Finalize the update

To complete the process, follow the steps outlined in [Step 11](#build-the-site-locally) in the [Add a project](#add-a-project) section and continue until Step 13 which completes the process.
