============
Git Workflow
============

New features, bugfixes, etc. should be worked on in separate branches.  Before they can be merged into
master, a pull request should be openned on the branch, and the code reviewed.  Only after the code
passes review should it be merged into master.

#. Pull requests should be the smallest change that makes sense.  If a feature/task/bugfix touches a
   lot of files,  possible it should be split up into multiple pull requests that are based upon each
   other.

#. Commit messages should be informative as to the changes being made.  A message like "Fix linting
   errors" would be good, whereas a commit messages like "lint" or "error" would be vague and
   unspecific.

#. NEVER squash merges.  Always use the github merge button to merge a branch into master.

#. Address review comments in additional commits in the branch.  This makes it easier for the reviewer
   to see which comments have been addressed, and to look at changes since the last review.  This
   project currently has no restrictions on the number of commits that can be merged into master.

#. ``git push --force`` should be used carefully and probably sparingly (if a rebase must happen on a
   branch, for instance), and never to master. Merging from master is an acceptable alternative to
   rebasing.

#. Please use ``git config push.default current`` (or alternatively ``git config --global push.default
   current``), so that if a branch argument is left off of ``git push``, by default it pushes the
   current branch to the remote branch of the same name.
