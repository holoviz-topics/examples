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

# Making a new project

Once you have a notebook that you think it is ready to be its own project
you can follow these steps to get it set up. For the examples I'll use
an example project named "bears":

### 1. Move the notebook into a new directory with same name

```bash
mkdir bears
mv bears.ipynb ./bears
cd bears
```

### 2. Start specifying the package dependencies

It can take a while to be sure you've captured every dependency, but I
usually start by using nbrr (`conda install -c conda-forge nbrr `) which
reads the notebooks and looks for dependencies:

```bash
nbrr env --directory "." --name bears > anaconda-project.yml
```

**NOTE:** We tend to add `nomkl` to the list of dependencies to speed up
environment build times. But there is no rule that you must do this.
MKL is used for better runtime performance in numpy operations, since we
use Numba for most of the internal computations it's not as important.

### 3. Create the anaconda-project file

Copy anaconda-project_template.yml to your own project, then just
replace NAME, DESC, MAINTAINERS and add the dependencies from step 2.

In some cases you may have a notebook that relies on a development
version of a package, or perhaps you wish to refer to a particular git
tag that has not made it into a released version. In this case, you can
add a `pip` subsection to your list of dependencies of the form:

```yaml
- pip:
  - git+https://github.com/USERNAME/REPO.git@REF#egg=PACKAGE
```

Where `USERNAME` is the GitHub username, `REPO` is the name of the git
repository, `REF` is a git reference (e.g a git tag or simply `master`
to point to the very latest version) and `PACKAGE` is the name of the
corresponding Python package. This syntax will use pip to fetch the
necessary code, checkout the specified git reference and install the
package.

### 4. Make sure it works

```
anaconda-project run test
```

You might need to declare extra dependencies or add data
downloads (see bay_trimesh for an example of downloading data).

### 5. For remote or large data

Make a smaller version of the data and put it in `test_data/<project>`. This
step allows automated tests to be run in a practical way, exercising all
of the example's functionality but on a feasible subset of the data involved.

### 6. If using intake

The intake catalog should be at the top level of the project directory and
called "catalog.yml".

```
. bears
├── anaconda-project.yml
├── bears.ipynb
└── catalog.yml
```

If using the intake cache, point the cache to the data dir in the project
by defining the INTAKE_CACHE_DIR variable in the anaconda-project file:

```yaml
variables:
  INTAKE_CACHE_DIR: data
```

This way when the user runs the notebook, they will still be able to see
the data from within the project directory:

```
. bears
├── anaconda-project.yml
├── bears.ipynb
├── catalog.yml
└── data
    └── f890ce4d538240e87ede9d31a6541443
        └── data.csv
```

Make sure to make a test catalog and put it in `test_data/<project>/catalog.yml`.
The sources in this catalog should have the same keys as the sources in the
real catalog, but they can point to smaller local versions of the data. That
data should also be in `test_data/<project>/` but referred to as if it were
inside a data directory.

```
test_data
└── bears
    ├── catalog.yml
    └── fake_local_data.csv
```

```yaml
sources:
  bears:
    description: Test data in a test catalog
    driver: csv
    args:
      urlpath: '{{ CATALOG_DIR }}/data/fake_local_data.csv'
```

# How test data work
Before running the tests on CI, we call `doit small_data_setup --name <name>`.
This command injects small versions of the data (from test_data) into the
project declared in the name argument. If intake is being used then the
test_catalog is swapped for the real intake catalog. To set everything
back to normal after running the tests, call `doit small_data_cleanup --name <name>`.
