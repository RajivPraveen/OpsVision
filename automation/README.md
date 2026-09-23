# GitHub Actions templates

These workflow files are ready to enable when the repository has a credential with permission to add or change GitHub Actions workflows.

To enable them, copy both YAML files into a .github/workflows/ folder at the repository root and push that change:

~~~bash
mkdir -p .github/workflows
cp automation/github-actions/*.yml .github/workflows/
~~~

- **ci.yml** installs the app, runs its checks, and builds sample data, a report, and CSV exports on pushes and pull requests.
- **weekly-report.yml** builds a report from fictional sample data every Monday and keeps it as a downloadable workflow artifact. It can also be run manually.

The weekly template is a demonstration. To report real operations data, replace its sample-data step with a reviewed data load and set up appropriate access controls before sending or publishing anything.
