.PHONY: install lint type test cov docs examples serve check

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests

type:
	mypy

test:
	pytest

cov:
	pytest --cov=dora_roi --cov-report=term --cov-report=html --cov-fail-under=90

docs:
	python -m dora_roi.docs

examples:
	roi sample examples/alpenrand-sample.xlsx --assessments examples/alpenrand-assessments.json \
		--incidents examples/alpenrand-incidents.json --contract-document examples/sample-contract.docx
	roi template examples/roi-blank-template.xlsx
	roi validate examples/alpenrand-sample.xlsx -f json -o examples/reports/validation-report.json --fail-on never
	roi validate examples/alpenrand-sample.xlsx -f md -o examples/reports/validation-report.md --fail-on never
	roi report examples/alpenrand-sample.xlsx -o examples/reports/executive-summary.html \
		--validation-report examples/reports/validation-report.html --prepared-by "GRC Advisory (sample)"
	roi contracts assess examples/alpenrand-sample.xlsx --assessments examples/alpenrand-assessments.json \
		-o examples/reports/art30-remediation-plan.html --client "Alpenrand Group"
	roi contracts assess examples/alpenrand-sample.xlsx --assessments examples/alpenrand-assessments.json \
		-o examples/reports/art30-remediation-plan.xlsx --client "Alpenrand Group"
	roi incidents summary examples/alpenrand-incidents.json --register examples/alpenrand-sample.xlsx \
		-o examples/reports/incident-summary.html --client "Alpenrand Group"
	roi finma examples/alpenrand-sample.xlsx --assessments examples/alpenrand-assessments.json \
		--incidents examples/alpenrand-incidents.json -f json -o examples/reports/finma-mapping.json
	roi readiness examples/alpenrand-sample.xlsx --assessments examples/alpenrand-assessments.json \
		--incidents examples/alpenrand-incidents.json -o examples/reports/dora-readiness.html \
		--client "Alpenrand Group" --prepared-by "GRC Advisory (sample)"

serve:
	roi serve

check: lint type cov
