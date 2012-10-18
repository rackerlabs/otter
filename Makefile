CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR}

test:	unit integration

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

apidocs:
	sphinx-apidoc -F -o _apidocs otter && sphinx-build -b html _apidocs _apidocs/html
