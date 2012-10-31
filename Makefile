TOP=$(shell pwd)
CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR}
DOCDIR=doc

test:	unit integration

run:
	PYTHONPATH=".:${PYTHONPATH}" twistd -n web --resource-script=${CODEDIR}/server.rpy

lint:
	${PYTHONLINT} ${PYDIRS}

unit:
	PYTHONPATH=".:${PYTHONPATH}" trial --random 0 ${CODEDIR}/test

integration:
	echo "integration test here"

coverage:
	PYTHONPATH=".:${PYTHONPATH}" coverage run --source=${CODEDIR} --branch `which trial` ${CODEDIR}/test && coverage html -d _trial_coverage --omit="${CODEDIR}/test/*"

cleandocs:
	rm -rf _builddoc
	rm -rf htmldoc

docs: cleandocs
	cp -r ${DOCDIR} _builddoc
	sphinx-apidoc -F -T -o _builddoc ${CODEDIR}
	PYTHONPATH=".:${PYTHONPATH}" sphinx-build -b html _builddoc htmldoc
	rm -rf _builddoc
