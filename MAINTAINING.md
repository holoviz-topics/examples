# Maintaining

This document is intended for the maintainers of this system.
Users and contributors should instead be directed to the website.

## Description

The main parts that constitute this system are:

- this GitHub repository
  - GitHub actions are used to validate, test, build projects, and deploy the documentation and the projects to Anaconda Enterprise
  - the `main` branch is the source of all the projects
  - the `evaluated` branch is used to store the evaluated/executed notebooks
- two websites
  - main: https://examples.holoviz.org
  - dev: https://holoviz-dev.github.io/examples/
- an Anaconda Enterprise instance hosted at https://holoviz-dev.anaconda.com/

Each project, also called example, is an [anaconda-project](https://anaconda-project.readthedocs.io/),
capturing the dependencies, data and commands required to execute the project.

The following steps describe what happens when a contributor updates or submits a project via a Pull Request:

1. the project is validated, going through a number of custom "linters" that check that the project is well specificed
2. the project is tested, executing its notebooks to check that no error occurs
3. the project is built, its notebooks are executed and pushed to a temporary branch names `tmp_evaluated_fghgf_<branchname>`
4. the dev website is built, based on the data found in the `evaluated` and the `tmp_evaluated_fghgf_<branchname>` branches

When the Pull Request is merged:

1. the content from the `tmp_evaluated_fghgf_<branchname>` branch is merged into the `evaluated` branch
2. the `tmp_evaluated_fghgf_<branchname>` branch is deleted
3. the main website is built, based on the data found in the `evaluated` branch
4. the project that has been added/updated is deployed to Anaconda Enterprise, if it declares any deployment

The system has been designed to cope with multiple projects being touched at once by a single Pull Request.

It is also possible to remove projects via a Pull Request, the system should remove the data in the `evaluated` branch
and remove the projects on Anaconda Enterprise.

## Set up admin/contributor environment

Install conda and run this to install the dependencies required to manage the system
(pick the file in the `envs/` folder that matches with your platform):

```bash
conda create -n examples-gallery-manage --file envs/environment-osx-arm64.lock
conda activate examples-gallery-manage
```

Alternatively, you could install the latest dependencies with this command:

```bash
conda env create --file envs/environment.yml
```

## Update admin/contributor environment

1. Update manually `envs/environment.yml`, if needed
2. Install `conda-lock` in your environment (dedicated one preferably, or `base`)
3. Run `cd envs` and `bash lock.yml`

## Commands

The `doit` task runner is used to implement many tasks required to maintain the system.
These tasks are implemented in Python and can be found in the `dodo.py` file.

Run `doit list` to list all the commands available.

### Build the website

To build the full website, run `doit doc_full`. This might take a little while as this involve multiple steps, such as building the archived projects, or checking out locally the `evaluated` branch to retrieve the evaluated notebooks. Once executed, running `doit doc_build_website` is enough to re-build the site only.

## GitHub Actions

Scheduled runs:
- all the projects are tested once a month
- all the projects are built once a month (not pushing to `evaluated`)
- the docs are built once a week (not pushing to either dev of main)
- the `template` project is re-deployed to Anaconda Enterprise once a week

Most of the workflows can be run from GitHub's website. For example, it is possible
to test multiple projects by providing a list of comma-separated projects.

## Uploading to Anaconda Enterprise (AE)

Some projects may not be automatically deployable to AE.
These projects will need to be manually added to AE and their deployment(s)
will need to be manually started.

```bash
cd <project>
# To make sure you don't bundle any extra file
git clean -fxd .
anaconda-project archive <project>.zip
```

Then connect to AE with the `holoviz-examples` user and from the AE interface,
select “Create”, then “Upload Project” and navigate
to the zip file. Once your project has been created, you can deploy it.

The endpoints should be:

- notebook: `<projectname>-notebook.holoviz-demo.anaconda.com`
- dashboard: `<projectname>.holoviz-demo.anaconda.com`

where `<projectname>` is the project name, with underscores turned
into hyphens.


## Monitoring deployments

An AWS Lambda was set up on the HoloViews account to check the deployments and report the output to the `deployments-monitoring` on Discord.
The code of this Lambda is available on this [Gist](https://gist.github.com/maximlt/f2e29eb7e6dbcaa4da4ee7d68636ac55).
The command `doit ae5_monitor_deployment` (based on similar code) is available to check the status of the deployment of 
one or all the projects.
