SCRIPTSDIR=./scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=otter scripts

test:	lint unit integration

run:
	PYTHONPATH=../ twistd -n web --resource-script=server.rpy 

lint:
	${PYTHONLINT} ${PYDIRS}

unit:
	echo "unit test here"

integration:
	echo "integration test here"