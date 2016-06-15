# How to Contribute

## Licensing

Otter is licensed under the Apache License version 2.0 (see the LICENSE file
for more information). All contributors must agree to license their
contributions according to those terms.

## Issues

We do use the GitHub issue tracker, and it's nice to submit an issue requesting
a change ahead of time, but not mandatory. It's particularly useful when some
discussion about a change would be useful.

## Pull Requests

Code must be unit tested. run "make lint" and "trial otter" before submitting
your PR.

If a PR introduces a user-visible feature or change, it must have end-user
documentation and integration tests. Usually these are done by dedicated
technical writers and quality engineers. Make sure it's clear when a change
needs these things. This can be done by creating issues requesting docs and
integration tests.

An author may also feel free to submit end-user docs and functional tests for
their own changes. For details about contributing the docs, see the [API docs readme](https://github.com/rackerlabs/otter/blob/master/api-docs/rst/dev-guide/README.md).

## Review Process

- At least one review is required per Pull Request, before it can be merged.
- If a PR does not have the "in progress" label, it is considered up for
  review. If an author realizes a PR needs more work (usually after a reviewer
  has made some comments), they may add the "in progress" label.
- Reviewers should assign the PR to themselves. This helps prevent multiple
  parties reviewing concurrently and finding mostly the same
  problems. Reviewers should unassign themselves when they're done.
- Reviewers may merge PRs immediately after the final review if no changes are
  necessary.
- Any party may request an additional reviewer, at which point the PR must not
  be merged until the additional review is done.
- Additional reviewers can be named explicitly or anonymously. e.g.:
  - author says "@manishtomar or @cyli: you know about Cassandra code, so can
    one of you review this?"
  - First reviewer says "LGTM, but I'm not very confident. Can someone else
    please review this?"
- If a reviewer gives a "LGTM" with a caveat, such as "LGTM, after you (fix
  this docstring typo)/(perform this trivial refactor)", then the author can
  merge the branch immediately after making the change (and only that change).
- If the PR has a "LGTM" but it conflicts with master, any party may merge
  it forward, give it a sanity check, and merge it.
- If conversation on a PR comes up between multiple parties, anyone who wishes
  to merge the PR must make a *reasonable* attempt at confirming consensus
  before merging.
- If any core contributor is outright opposed to a PR, it must not be merged
  until consensus is reached.
