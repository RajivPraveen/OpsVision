.PHONY: help seed serve report export test

help:
	@echo "make seed    Build the sample database"
	@echo "make serve   Start the dashboard on port 8000"
	@echo "make report  Write the weekly executive report"
	@echo "make export  Write CSV files for spreadsheets"
	@echo "make test    Run the project checks"

seed:
	python3 -m opsvision seed

serve:
	python3 -m opsvision serve

report:
	python3 -m opsvision report

export:
	python3 -m opsvision export

test:
	python3 -m unittest discover -s tests -v

