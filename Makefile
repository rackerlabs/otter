CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR}
CQLSH ?= $(shell which cqlsh)
DOCDIR=doc
UNITTESTS ?= ${CODEDIR}/test
CQLSHARGS ?= localhost 9170
CONTROL_KEYSPACE ?= OTTER
CONTROL_CQL_REPLACEMENT ?= s/@@KEYSPACE@@/$(CONTROL_KEYSPACE)/g
CONTROL_SETUP    = $(shell ls schema/setup/control_*.cql | sort)
CONTROL_TEARDOWN = $(shell ls schema/teardown/control_*.cql | sort)

test:	unit integration

run:
	PYTHONPATH=".:${PYTHONPATH}" twistd -n web --resource-script=${CODEDIR}/server.rpy

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

schema: FORCE schema-setup schema-teardown

schema-setup:
	echo "-- *** Generated Schema ***" > schema/setup.cql
	for f in $(CONTROL_SETUP); do \
	  sed -e "$(CONTROL_CQL_REPLACEMENT)" $$f >> schema/setup.cql; \
	done \

schema-teardown:
	echo "-- *** Generated Schema ***" > schema/teardown.cql
	for f in $(CONTROL_TEARDOWN); do \
	  sed -e "$(CONTROL_CQL_REPLACEMENT)" $$f >> schema/teardown.cql; \
	done \

FORCE:

clean: cleandocs
	find . -name '*.pyc' -delete
	find . -name '.coverage' -delete
	find . -name '_trial_coverage' -print0 | xargs rm -rf
	find . -name '_trial_temp' -print0 | xargs rm -rf
	rm -rf dist build *.egg-info
	rm -rf otter-deploy*
	rm schema/setup.cql
	rm schema/teardown.cql

bundle:
	./scripts/bundle.sh
