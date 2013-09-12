CODEDIR=otter
TESTDIR1=autoscale_cloudroast/test_repo
TESTDIR2=autoscale_cloudcafe/autoscale
SCRIPTSDIR=scripts
PYTHONLINT=${SCRIPTSDIR}/python-lint.py
PYDIRS=${CODEDIR} ${SCRIPTSDIR} autoscale_cloudcafe autoscale_cloudroast
CQLSH ?= $(shell which cqlsh)
DOCDIR=doc
UNITTESTS ?= ${CODEDIR}
CASSANDRA_HOST ?= localhost
export CASSANDRA_HOST
CASSANDRA_PORT ?= 9160
export CASSANDRA_PORT
CONTROL_KEYSPACE ?= OTTER
REPLICATION_FACTOR ?= 3
CLOUDCAFE ?= $(shell which cafe-runner)

test: unit integration

run:
	twistd -n --logger=otter.log.observer_factory_debug otter-api

run_docker: rewrite_config run

rewrite_config:
	./scripts/rewrite_config.py

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
ifneq ($(JENKINS_URL), )
ifneq ($(CLOUDCAFE), )
	cafe-runner autoscale dev -p functional --parallel
else
	@echo "Waiting on preprod node before running tests here."
endif
else
	@echo "Cloudcafe is not set up as desired, so can't run those tests."
endif

coverage:
	coverage run --source=${CODEDIR} --branch `which trial` ${UNITTESTS} && coverage html -d _trial_coverage --omit="*/test/*"

cleandocs:
	rm -rf _builddoc
	rm -rf htmldoc

docs: cleandocs
	cp -r ${DOCDIR} _builddoc
	sphinx-apidoc -F -T -o _builddoc ${CODEDIR}
	sphinx-apidoc -F -T -o _builddoc ${TESTDIR2}
	sphinx-apidoc -F -T -o _builddoc ${TESTDIR1}
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

migrate-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/migrations --outfile schema/migrations-dev.cql --replication 1 --keyspace ${CONTROL_KEYSPACE} --host ${CASSANDRA_HOST} --port ${CASSANDRA_PORT}

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
	rm -rf otter*deploy*
	rm -rf schema/setup-*.cql
	rm -rf schema/migrations-*.cql
	rm -rf schema/teardown-*.cql

bundle:
	./scripts/bundle.sh
