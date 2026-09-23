# Working on OpsVision

## Local setup

Python 3.9 or newer is enough to run the source directly:

~~~bash
python3 -m opsvision seed
python3 -m opsvision serve
~~~

To test the installed command in an isolated environment:

~~~bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
opsvision serve
~~~

The package includes the dashboard files and database layout. The generated database, reports, and CSV exports are written in the folder where you run the command.

## Check a change

~~~bash
python3 -m unittest discover -s tests -v
python3 -m opsvision seed
python3 -m opsvision report
python3 -m opsvision export
~~~

The tests check the eight-point delivery example, that its reason and segment breakdowns add up, that the sample produces the expected types of alerts, that the report contains its sections, that database links are valid, and that exported CSVs can be loaded back without changing the service result.

Ready-to-enable [GitHub Actions templates](../automation/README.md) can run these checks on pushes and pull requests across supported Python versions. A separate Monday template builds a report from the sample data.

## Updating a screenshot

Screenshots in images/ show the sample data. To refresh one, rebuild the sample database, run the local dashboard, capture the page at a wide desktop size, and replace the matching image. Check that the pictured date range and values still match the sample, and keep the image text readable at GitHub README width.

## Important boundaries

- The included records are fictional; never present them as a company result.
- The reason chart uses recorded order reasons, not proof from an experiment.
- The local server does not have user accounts. Add access controls before connecting it to confidential operations data.
- The scheduled sample report is an artifact in GitHub Actions. Sending a report to people requires a separate, reviewed delivery step.
