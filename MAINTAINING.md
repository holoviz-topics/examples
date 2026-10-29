# Maintaining

This document is intended for the maintainers of this system.
Users and contributors should instead be directed to the website.

## Description

The main parts that constitute this system are:

- this GitHub repository
  - GitHub actions are used to validate, test, build projects, deploy the documentation and publish container images of the projects
  - the `main` branch is the source of all the projects
  - the `evaluated` branch is used to store the evaluated/executed notebooks
- two websites
  - main: https://examples.holoviz.org
  - dev: https://holoviz-dev.github.io/examples/
- an Anaconda Enterprise instance hosted at https://holoviz-dev.anaconda.com/

Each project, also called example, is a [pixi](https://pixi.sh) workspace: its `pixi.toml` and `pixi.lock`
capture the dependencies, data and tasks required to execute the project.

The following steps describe what happens when a contributor updates or submits a project via a Pull Request (`pr_flow.yml`):

1. the project is validated with `scripts/validate_project.py`, which checks that the project is well specified
2. the project is tested, executing its notebooks to check that no error occurs
3. the project is built with `scripts/build_project.py`, its notebooks are executed and uploaded as the `artifacts-<project>` artifact of the run
4. the dev website is built, based on the data found in the `evaluated` branch and the artifacts of the run
5. a container image is built for the projects that define a `dashboard` task

When the Pull Request is merged (`docs.yml`):

1. the artifacts of the latest `pr_flow.yml` run of the Pull Request are committed to the `evaluated` branch
2. the main website is built, based on the data found in the `evaluated` branch

When a commit lands on `main` (`docker.yml`), the container images of the changed projects that define a `dashboard` task
are pushed to `ghcr.io/<repo>/<project>:latest`.

The system has been designed to cope with multiple projects being touched at once by a single Pull Request.

It is also possible to remove projects via a Pull Request, the system should remove the data in the `evaluated` branch.

## Set up admin/contributor environment

Install [pixi](https://pixi.sh). The root `pixi.toml` defines a `docs` environment to build the website;
the scripts in `scripts/` only need Python 3.11 or later.

Each project has its own environment, created the first time a task is run in its directory, e.g.:

```bash
cd attractors
pixi run notebook
```

## Commands

The scripts used by the GitHub actions live in the `scripts/` folder and can be run locally:

- `python scripts/list_projects.py` lists the projects, or the ones changed compared to `origin/main` with `--changed`
- `python scripts/validate_project.py <project>` validates a project
- `python scripts/build_project.py <project>` executes the notebooks of a project into `doc/gallery/<project>/`
- `pixi run docker <build|serve> <project>` builds or serves the container image of a project

Run any of the Python scripts with `--help` to see all their options.

### Build the website

To build the full website, first get the evaluated notebooks from the `evaluated` branch:

```bash
git fetch origin evaluated
git checkout origin/evaluated -- doc/gallery
git reset -q doc/gallery
```

Then optionally run `python scripts/build_project.py <project>` to replace the evaluated notebooks of a project with your local changes, and build the site:

```bash
pixi run -e docs docs-prepare
pixi run -e docs docs-build
```

The website is built in the `builtdocs/` folder.

## GitHub Actions

Scheduled runs:

- all the projects are tested once a month
- all the projects are built once a month (not pushing to `evaluated`)
- the gallery is prepared once a week from the `evaluated` branch, without building or deploying the site

Most of the workflows can be run from GitHub's website. For example, it is possible
to test multiple projects by providing a list of comma-separated projects.

## Monitoring deployments

An AWS Lambda was set up on the HoloViews account to check the deployments and report the output to the `deployments-monitoring` on Discord.
The code of this Lambda is available on this [Gist](https://gist.github.com/maximlt/f2e29eb7e6dbcaa4da4ee7d68636ac55).
