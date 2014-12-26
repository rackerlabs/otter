# Rackspace Autoscale

*There Otter be an Otter scaling system.*

![Otter Cups](https://i.chzbgr.com/completestore/12/8/19/AjXtHogT4UqgJwDJsq7igA2.gif)

This codebase is not able to be deployed independently. The code is
open source as a reference, but requires dependencies not available
within this repository.

Talk with us! Join us in:

irc.freenode.net #stretch-dev

Otter Dev Hall of Fame (alphabetical):

- cyli
- lvh
- manisht
- radix
- wirehead

Honorary Otters:

- glyph

Emeritus otters:

- dreid
- fsargent
- oubiwann
- rockstar

## `make` targets

In alphabetical order.  You probably will only need a select few of these.

- `make bundle` builds a "bundle" appropriate for deployment (Ubuntu only).  For Jenkins and Chef use only.
- `make cleandocs` removes customer-facing documentation without removing other artifacts.
- `make clean` removes all build-time artifacts, leaving the repository in a distributable state.
- `make clear-dev-schema` first removes any existing development schema, then re-installs a fresh schema.
- `make coverage` performs coverage analysis.
- `make docs` builds customer-facing documentation.
- `make env` creates and switches into the Python virtualenv environment.  It'll also pip-install development requirements.
- `make env-precheck` makes sure you have enough pre-existing infrastructure to be able to run `make env` to begin with.
- `make integration` runs integration tests.
- `make lint` performs a lint (PEP8, et. al.) check on the source code.
- `make load-dev-schema` will attempt to load the development schema into Cassandra.
- `make migrate-dev-schema` will attempt to update the development schema on an existing Cassandra instance.
- `make run` starts up an instance of the Otter API.
- `make schema` generates the CQL files corresponding to setting up and tearing down Otter's Cassandra schema.  Equivalent to running `make schema-setup schema-teardown` manually.
- `make schema-setup` generates the setup CQL files.
- `make schema-teardown` generates the teardown CQL files.
- `make teardown-dev-schema` will attempt to remove a development schema from an existing Cassandra instance.
- `make test` runs both unit and integration tests.
- `make unit` runs unit tests.
