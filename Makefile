CODEDIR=otter
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR} autoscale_cloudcafe autoscale_cloudroast
CQLSH ?= $(shell which cqlsh)
DOCDIR=doc
UNITTESTS ?= ${CODEDIR}
CASSANDRA_HOST ?= localhost
CASSANDRA_PORT ?= 9160
CONTROL_KEYSPACE ?= OTTER
REPLICATION_FACTOR ?= 3
CLOUDCAFE ?= $(shell which shell cafe-runner)

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
ifneq ($(and $(CLOUDCAFE),$(JENKINS_URL)), )
	cafe-runner autoscale prod -p functional --parallel
else ifneq ($(CLOUDCAFE), )
	cafe-runner autoscale dev -p functional --parallel
else
	@echo "Are you on the VM?  cloudcafe is not set up as desired."
	@echo "So can't run integration tests."
endif

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
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup --ban-unsafe --outfile schema/setup-dev.cql --replication 1 --keyspace ${CONTROL_KEYSPACE}  --dry-run
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup --ban-unsafe --outfile schema/setup-prod.cql --replication ${REPLICATION_FACTOR} --keyspace ${CONTROL_KEYSPACE}  --dry-run

schema-teardown:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown --outfile schema/teardown-dev.cql --replication 1 --keyspace ${CONTROL_KEYSPACE}  --dry-run
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown --outfile schema/teardown-prod.cql --replication ${REPLICATION_FACTOR} --keyspace ${CONTROL_KEYSPACE}  --dry-run

load-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup --ban-unsafe --outfile schema/setup-dev.cql --replication 1 --keyspace ${CONTROL_KEYSPACE} --host ${CASSANDRA_HOST} --port ${CASSANDRA_PORT}

teardown-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown --outfile schema/teardown-dev.cql --replication 1 --keyspace ${CONTROL_KEYSPACE} --host ${CASSANDRA_HOST} --port ${CASSANDRA_PORT}

clear-dev-schema: FORCE teardown-dev-schema load-dev-schema

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
