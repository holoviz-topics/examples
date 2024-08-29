# Contributing

You can contribute to this website either by submitting a new project
or by updating an existing one.

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

### Create the development environment

From the top level of your cloned directory, run:

```bash
conda env create --file envs/environment.yml
conda activate examples-gallery-manage
```

Then add the repository as your `origin` with the following commands:

<strong>SSH</strong>

```bash
git remote add origin git@github.com:holoviz-topics/examples.git
```

<strong>HTTPS</strong>

```bash
git remote add origin https://github.com/holoviz-topics/examples.git
```

## Add a project

Once you have an example (one or more notebook(s)) that you think is ready to be
shared on this website follow these steps to set it up correctly.

### 1. Create the project directory

Its name must be all lower-case, only including underscore as
special characters. This name is important as you will have to
re-use it as-is in multiple places.

### 2. Use the template

Copy the template project from `template/anaconda-project.yml` to your project.
You will use this file as a basis to build your own project.
You can further explore the `template` example folder, which houses a fully executable and deployable project.

```{note}
Do not forget to clean up the notes left in the template project file
once you are done updating it for your own project.
```

### 3. Move your notebook(s) to your project directory

If your project has a single notebook it must share the same name
as your project directory. If your project has more than one notebooks,
it must have an `index.ipynb` notebook that will link to your other notebooks.

Your project may have notebooks that are not meant to be displayed on the website,
such as pre-processing notebooks. See the `skip` option to declare them:

```yaml
skip:
   - data_prep.ipynb
```

Your notebooks should be committed **without output**. The system will be in charge
of executing your notebooks based on your project characteristics, to
build the documentation.

In some cases it is impossible for the system to execute your notebooks. This
happens for instance if your notebooks are too long to run, require too much
data, require special hardware, etc. In those cases, you should instead commit
your notebooks *with output* and set `skip_notebooks_evaluation` to `true`.

### 4. List the dependencies

Add to your `anaconda-project.yml` file the dependencies required to run
your notebook(s) and application(s). The recommended practice is to pin
all your dependencies using either `>=` (for easier updates) or `==`.

### 5. Manage the data

There are multiple ways to manage the data required to run a project:

- the project does not ingest any data, as it either generates it on the fly
or as it just provides written indications on how to get it: set `no_data_ingestion`
to `true` in the `anaconda-project.yml`
- the project needs to download some data, you have two options:
   - fill in the `downloads` section of the `anaconda-project.yml` file.
   - or, create an Intake catalog and load it in your notebooks, the catalog must be named
   `catalog.yml` and be at the root of your project
- the project relies on some very light data, then it can be committed to the repository
as is. It must be stored in a `data/` subfolder of your project


When using an Intake catalog, point the cache to the data dir in the
project by defining the `INTAKE_CACHE_DIR` variable in the
`anaconda-project.yml` file:

```yaml
variables:
  INTAKE_CACHE_DIR: data
```

This way when the user runs the notebook, they will still be able to see
the data from within the project directory

### 6. Testing

Your project will be automatically tested by the system:

- the notebooks will be linted with `flake8`. If you deem that the linter is too strict, you
can add some more rules to ignore to the `pyproject.toml` configuration file
- the notebooks will be remotely executed with `nbval`, the tests failing if an error occurs during their execution

If you project has some special testing needs, you can implement your own testing command by
adding a `test` command to the `anaconda-project.yml` file. You will presumably also need to
declare testing dependencies, you can do so by extending the default dependencies.

Projects that download data must provide a test dataset that is a reduced version of their full
dataset, which should be small enough to be committed to the repository. These datasets must be
saved in the `test_data` folder in a folder named as the project. When the system will test your project,
it will move your test data to the right place, i.e. your datasets to the `data/` subfolder and
will replace your Intake catalog. This step allows automated tests to be run in a practical way,
exercising all of the example's functionality but on a feasible subset of the data involved.

### 7. Complete the anaconda-project file

Follow the instructions provided in the `template/anaconda-project.yml` file.

### 8. Add a thumbnail

Create a nice but lightweight PNG thumbnail (maximum size of 1MB) with an aspect ratio between 0.9 and 1.5.
Name it as your project if you have only one notebook or as `index.png` if you have multiple notebooks,
and save it in the `thumbnails` subfolder of your project.

### 9. Locking

You must lock your project to capture the full set of dependencies that are required to execute it.

From your root directory, Run:

```bash
doit lock:<projectname>
```
replacing `<projectname>` with your project name.

```{note}
All `doit` commands must be run from the root directory.
```

### 10. Make sure it works

If you have declared commands run them to check that they work as expected,
as this is what the users of your project will ultimately use. Run:

```bash
anaconda-project run <commandname>
```

### 11. Add a project category

In order for your new project to appear on the homepage, you need to add a category tag to the `tags.yml` file in the docs directory.

You can do that by going to the `docs/tags.yml` file and then add your category as follows:

```yaml
<project_name>:
   category: [<allowed tag1>, <allowed tag2>]
```

The list of allowed tags are:

- Featured
- Geospatial
- Finance
- Economics
- Mathematics
- Cybersecurity
- Networks
- Neuroscience
- Other Sciences
- Sports

For example, if your new project is named '*earth_maps*', you can add it to the `tags.yml` file as:

```yaml
earth_maps:
   category: [Geospatial]
```

### 12. Build the site locally

Build the site locally to make sure it looks the way you expect when it is eventually deployed.

To do this:

1. Run the project notebook(s), don't clear their output.

2. Run:
      ```bash
      doit doc_one --name <projectname>
      ```

This command copies the notebooks in `./doc/gallery/<projectname>` along with other files needed to build the docs (thumbnails, archive, assets, etc.), and builds the docs with Sphinx.

3. Open the built site on your web browser via: `./builtdocs/index.html`

4. Clean up this process by running `doit clean doc_one` and then commit the notebook(s) **without output.**

### 13. Validate, test, and build

After viewing the built site, you should run locally the steps that are going to be run on the CI.

Start by validating that your project is well specified by running

```bash
doit validate:<projectname>
```

Update your project until you have no validation *warning* left.

Run `doit clean --clean-dep validate:<projectname>` to clean up that step.

Now you will test your project by running:

```bash
doit test:<projectname>
```

Update your project until the tests pass.

Run `doit clean --clean-dep test:<projectname>` to clean up that step.

If you built the site locally without any errors, you can skip this final build step. However, the command to run it for debugging purposes is:

```bash
doit build:<projectname>
```

After validating and testing the project, this step should succeeed.

Run `doit clean --clean-dep build:<projectname>` to clean up that step.

### 14. Open a Pull Request

Open a Pull Request that adds your project to the repository. The CI
will take care of validating, testing and building it. If these steps
succeed the developer website will be built and you will be able to check
a rendered version of your project at https://holoviz-dev.github.io/examples/.

When the review of your Pull Request is completed and it is merged, the CI
will then take care of updating the main site. If you declared deployments,
the CI will also take care of automatically starting them.

## Update a project

To update an existing project, follow these simple steps.

### 1. Choose the project

Navigate to the selected project directory and execute the following command:

``` bash
anaconda-project run notebook
```

This command opens the project notebook in your web browser. If there are multiple notebooks in the project, run:

```bash
anaconda-project run <notebook name>
```

Replace `<notebook name>` with the desired notebook's name.

Remember to commit the updated notebooks **without output.**

### 2. Finalize the update

To complete the process, follow the steps outlined in [Step 12](#12-build-the-site-locally) in the [Add a project](#add-a-project) section and continue until Step 13 which completes the process.
