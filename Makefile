CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR}
DOCDIR=doc
UNITTESTS ?= ${CODEDIR}/test

test:	unit integration

run:
	PYTHONPATH=".:${PYTHONPATH}" twistd -n web --resource-script=${CODEDIR}/server.rpy

env:
	./scripts/bootstrap-virtualenv.sh

lint:
	${PYTHONLINT} ${PYDIRS}

unit:
	PYTHONPATH=".:${PYTHONPATH}" trial --random 0 ${UNITTESTS}

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

clean: cleandocs
	find . -name '*.pyc' -delete
	find . -name '.coverage' -delete
	find . -name '_trial_coverage' -print0 | xargs rm -rf
	find . -name '_trial_temp' -print0 | xargs rm -rf
	rm -rf dist build *.egg-info
	rm -rf otter-deploy*

bundle:
	./scripts/bundle.sh
