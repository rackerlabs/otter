SCRIPTSDIR=./scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=otter scripts

test:	lint unit integration

run:
	PYTHONPATH=. twistd -n web --resource-script=otter/server.rpy

lint:
	${PYTHONLINT} ${PYDIRS}

unit:
	PYTHONPATH=. trial otter/test

integration:
	echo "integration test here"

coverage:
	PYTHONPATH=. coverage run --branch `which trial` otter/test && coverage html -d _trial_coverage
