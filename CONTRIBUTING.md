# How to Contribute

## Licensing

Otter is licensed under the Apache License version 2.0 (see the LICENSE file
for more information). All contributors must agree to license their
contributions according to those terms.

## Issues

We do use the GitHub issue tracker, and it's nice to submit an issue requesting
a change ahead of time, but not mandatory. It's particularly useful when some
discussion about a change would be useful.

## Making Changes

Here's are requirements for making a PR:

- Code must be unit tested.
- run "make lint" and "trial otter" before submitting your PR
- If a PR introduces a user-visible feature or change:
  - It must have end-user documentation. Usually this is done by a dedicated
    technical writer. Make sure it's clear when a change needs documentation.
    This can be done by creating an issue requesting documentation.
  - It must have integration tests. This is also usually done by a dedicated
    quality engineer. Make sure it's clear when a change needs tests. This can
    be done by creating an issue requesting tests.
  - An author may also feel free to submit end-user docs and functional tests
    for their own changes.

## Review Process

- At least one review is required per Pull Request.
- If a PR does not have the "in progress" label, it is considered up for
  review. If an author realizes a PR needs more work (usually after a reviewer
  has made a bunch of comments), they may add the "in progress" label.
- Any party may request an additional reviewer, at which point the PR must not
  be merged until the additional review is done.
- additional reviewers can be named explicitly or anonymous. e.g.:
  - author says "@manishtomar or @cyli: you know about Cassandra code, so can
    one of you review this?"
  - First reviewer says "LGTM, but I'm not very confident. Can someone else
    please review this?"
- If a reviewer gives a "LGTM" with caveat, such as "LGTM, after you (fix this
  docstring typo)/(perform this trivial refactor)", then the author can merge
  the branch immediately after making the change (and only that change).
- If the PR has a "LGTM" but it conflicts with master, any party may merge
  it forward, give it a sanity check, and merge it.

