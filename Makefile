.PHONY: install lint type test cov docs examples serve check lock lock-upgrade fuzz

install:  # exactly the locked versions (requirements/dev.txt)
	pip install --require-hashes -r requirements/dev.txt
	pip install --no-deps -e .

lock:  # after changing dependencies in pyproject.toml
	sh scripts/lock.sh

lock-upgrade:  # move every locked dependency to its newest allowed version
	sh scripts/lock.sh --upgrade

lint:
	ruff check src tests scripts

type:
	mypy

test:
	pytest

cov:
	pytest --cov=dora_roi --cov-report=term --cov-report=html --cov-fail-under=85

docs:
	python -m dora_roi.docs

examples:
	roi sample examples/alpenrand-sample.xlsx
	roi template examples/roi-blank-template.xlsx
	roi validate examples/alpenrand-sample.xlsx -f json -o examples/reports/validation-report.json --fail-on never
	roi validate examples/alpenrand-sample.xlsx -f md -o examples/reports/validation-report.md --fail-on never
	roi report examples/alpenrand-sample.xlsx -o examples/reports/executive-summary.html \
		--validation-report examples/reports/validation-report.html --prepared-by "GRC Advisory (sample)"

serve:
	roi serve

check: lint type cov
