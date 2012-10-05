SCRIPTSDIR=./scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint

run:
	PYTHONPATH=../ twistd -n web --resource-script=server.rpy 

lint:
	${PYTHONLINT} otter

test:
	echo "yay"