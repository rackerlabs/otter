CODEDIR=otter
TESTDIR1=autoscale_cloudroast/test_repo
TESTDIR2=autoscale_cloudcafe/autoscale
SCRIPTSDIR=scripts
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

mkfile_dir := $(shell dirname "$(MAKEFILE_LIST)")

.PHONY: targets env-precheck docbook

targets:
	@cat README.md

hooks:
	cp ${mkfile_dir}/scripts/config_check.py ${mkfile_dir}/.git/hooks
	echo "#!/bin/bash" > ${mkfile_dir}/.git/hooks/pre-commit
	echo "python .git/hooks/config_check.py" >> ${mkfile_dir}/.git/hooks/pre-commit
	chmod a+x ${mkfile_dir}/.git/hooks/pre-commit

env-precheck:
	./scripts/env-precheck.py

test: unit integration

run:
	twistd -n --logger=otter.log.observer_factory_debug otter-api

env:
	./scripts/bootstrap-virtualenv.sh

lint: listoutdated lint-code

lint-code: flake8diff
	pyflakes ${PYDIRS}

listoutdated:
	pip list --outdated --allow-external=cafe,cloudcafe

# concatenate both environment variables together - if both are unset, the
# concatenation will be empty
ifneq ($(JENKINS_URL)$(TRAVIS_PULL_REQUEST), )
# On Jenkins or Travis, HEAD will be a Github-created merge commit. Hence,
# diffing against HEAD^1 gives you the diff introduced by the PR, which is what
# we're trying to test.
DIFF_TARGET = HEAD^1
else
# On not-Jenkins, we find the current branch's branch-off point from master,
# and diff against that.
DIFF_TARGET = $(shell git merge-base master HEAD)
endif

flake8diff:
	git diff --patch --no-prefix ${DIFF_TARGET} | flake8 --diff

flake8full:
	flake8 ${PYDIRS}

TRIAL_OPTIONS=--random 0
TRIAL_OPTIONS_UNIT=${TRIAL_OPTIONS} --jobs 4

unit:
ifneq ($(JENKINS_URL), )
	trial ${TRIAL_OPTIONS_UNIT} --reporter=subunit ${UNITTESTS} \
		| subunit-1to2 | tee subunit-output.txt
	tail -n +4 subunit-output.txt | subunit2junitxml > test-report.xml
else
	trial ${TRIAL_OPTIONS_UNIT} ${UNITTESTS}
endif

integration:
ifneq ($(JENKINS_URL), )
ifneq ($(CLOUDCAFE), )
	cafe-runner autoscale dev -p functional --parallel
else
	@echo "Environment variable CLOUDCAFE appears to not be set; is it installed"
	@echo "correctly and are you on the correct environment?"
	@echo "Invoke `make envcheck' to double-check your environment compatibility."
endif
else
	@echo "Cloudcafe is not set up as desired, so can't run integration tests:"
	@echo "- Missing JENKINS_URL environment setting."
endif

coverage:
	coverage run --source=${CODEDIR} --branch `which trial` \
	    ${TRIAL_OPTIONS} ${UNITTESTS}

coverage-html: coverage
	coverage html -d _trial_coverage --omit="*/test/*"

cleandocs:
	rm -rf _builddoc
	rm -rf htmldoc
	rm -rf docbook/target

docs: sphinxdocs docbook

sphinxdocs:
	cp -r ${DOCDIR} _builddoc
	sphinx-apidoc -F -T -o _builddoc ${CODEDIR}
	sphinx-apidoc -F -T -o _builddoc ${TESTDIR2}
	sphinx-apidoc -F -T -o _builddoc ${TESTDIR1}
	sphinx-build -b html _builddoc htmldoc

docbook:
ifneq ($(shell git diff --name-only ${DIFF_TARGET} -- docbook), )
	cd docbook; mvn -q compile
else
	echo "Skipping, nothing changed between working tree and diff target"
endif

schema: FORCE schema-setup schema-teardown

schema-setup:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup \
		--ban-unsafe \
		--outfile schema/setup-dev.cql \
		--replication 1 \
		--keyspace ${CONTROL_KEYSPACE} \
		--dry-run
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup \
		--ban-unsafe \
		--outfile schema/setup-prod.cql \
		--replication ${REPLICATION_FACTOR} \
		--keyspace ${CONTROL_KEYSPACE} \
		--dry-run

schema-teardown:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown \
		--outfile schema/teardown-dev.cql \
		--replication 1 \
		--keyspace ${CONTROL_KEYSPACE}  \
		--dry-run
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown \
		--outfile schema/teardown-prod.cql \
		--replication ${REPLICATION_FACTOR} \
		--keyspace ${CONTROL_KEYSPACE}  \
		--dry-run

load-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/setup \
		--ban-unsafe \
		--outfile schema/setup-dev.cql \
		--replication 1 \
		--keyspace ${CONTROL_KEYSPACE} \
		--host ${CASSANDRA_HOST} \
		--port ${CASSANDRA_PORT}

migrate-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/migrations \
		--outfile schema/migrations-dev.cql \
		--replication 1 \
		--keyspace ${CONTROL_KEYSPACE} \
		--host ${CASSANDRA_HOST} \
		--port ${CASSANDRA_PORT}

teardown-dev-schema:
	PATH=${SCRIPTSDIR}:${PATH} load_cql.py schema/teardown \
		--outfile schema/teardown-dev.cql \
		--replication 1 \
		--keyspace ${CONTROL_KEYSPACE} \
		--host ${CASSANDRA_HOST} \
		--port ${CASSANDRA_PORT}

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
