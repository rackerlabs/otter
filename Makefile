CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR}
CQLSH ?= $(shell which cqlsh)
DOCDIR=doc
UNITTESTS ?= ${CODEDIR}
CQLSHARGS ?= localhost 9170
CONTROL_KEYSPACE ?= OTTER
REPLICATION_FACTOR ?= 3
CONTROL_CQL_REPLACEMENT ?= s/@@KEYSPACE@@/$(CONTROL_KEYSPACE)/g;s/@@REPLICATION_FACTOR@@/$(REPLICATION_FACTOR)/g
DEV_CQL_REPLACEMENT ?= s/@@KEYSPACE@@/$(CONTROL_KEYSPACE)/g;s/@@REPLICATION_FACTOR@@/1/g
CONTROL_SETUP    = $(shell ls schema/setup/control_*.cql | sort)
CONTROL_TEARDOWN = $(shell ls schema/teardown/control_*.cql | sort)

test: unit integration

run:
	twistd -n --logger=otter.log.observer_factory_debug otter-api

mockrun:
	twistd -n --logger=otter.log.observer_factory_debug otter-api --mock

env:
	./scripts/bootstrap-virtualenv.sh

lint:
	${PYTHONLINT} ${PYDIRS}

unit:
ifneq ($(JENKINS_URL), )
	trial --random 0 --reporter=subunit ${UNITTESTS} | tee subunit-output.txt
	tail -n +3 subunit-output.txt | subunit2junitxml > test-report.xml
else
	trial --random 0 ${UNITTESTS}
endif

integration:
	@echo "integration test here"

coverage:
	coverage run --source=${CODEDIR} --branch `which trial` ${UNITTESTS} && coverage html -d _trial_coverage --omit="*/test/*"

cleandocs:
	rm -rf _builddoc
	rm -rf htmldoc

docs: cleandocs
	cp -r ${DOCDIR} _builddoc
	sphinx-apidoc -F -T -o _builddoc ${CODEDIR}
	sphinx-build -b html _builddoc htmldoc
	rm -rf _builddoc

schema: FORCE schema-setup schema-teardown

schema-setup:
	echo "-- *** Generated Schema ***" > schema/setup-dev.cql
	echo "-- *** Generated Schema ***" > schema/setup-prod.cql
	for f in $(CONTROL_SETUP); do \
	  sed -e "$(CONTROL_CQL_REPLACEMENT)" $$f >> schema/setup-prod.cql; \
	  sed -e "$(DEV_CQL_REPLACEMENT)" $$f >> schema/setup-dev.cql; \
	done \

schema-teardown:
	echo "-- *** Generated Schema ***" > schema/teardown-dev.cql
	echo "-- *** Generated Schema ***" > schema/teardown-prod.cql
	for f in $(CONTROL_TEARDOWN); do \
	  sed -e "$(CONTROL_CQL_REPLACEMENT)" $$f >> schema/teardown-prod.cql; \
	  sed -e "$(DEV_CQL_REPLACEMENT)" $$f >> schema/teardown-dev.cql; \
	done \

FORCE:

clean: cleandocs
	find . -name '*.pyc' -delete
	find . -name '.coverage' -delete
	find . -name '_trial_coverage' -print0 | xargs rm -rf
	find . -name '_trial_temp' -print0 | xargs rm -rf
	rm -rf dist build *.egg-info
	rm -rf otter-deploy*
	rm -rf schema/setup-*.cql
	rm -rf schema/teardown-*.cql

bundle:
	./scripts/bundle.sh
