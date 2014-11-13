#!/usr/bin/env python

"""env-precheck checks to see if we have the minimum set of requirements needed
to build Otter's environment via "make env".
"""

import subprocess
import sys


def _run_process(exe):
    """_run_process invokes the supplied command (list of strings, as required
    by the subprocess module).  It accumulates each output line (including
    stderr, but that's unimportant for our purposes) and returns the results.
    It also returns the result code.  Result is a tuple, (result-code,
    [output]).
    """
    p = subprocess.Popen(exe, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    while(True):
        # Subprocess.poll() returns None while subprocess is running
        retcode = p.poll()
        lines.append(p.stdout.readline())
        if(retcode is not None):
            return (retcode, lines)


def _command_exists(cmd):
    """Yields true iff the command completes successfully and returns a zero
    result code.
    """
    return _run_process(["which", cmd])[0] == 0


def _find_file(f):
    """Yields true iff the file can be found somewhere on the /usr filesystem.
    If the file exists and yet things break, it's most likely due to a path
    setting that is misconfigured.
    """
    return len(_run_process(["find", "/usr", "-iname", f])[1]) > 0


def can_execute(cmd, how):
    """can_execute checks to see of the supplied command (cmd) is in the
    user's $PATH.  If not, report a strategy to help the user install it
    easily.
    """
    broken = False
    sys.stdout.write("Looking to see if you have %s installed... " % (cmd))
    if _command_exists(cmd):
        print "Yes"
    else:
        print "No\n"
        print "Please install %s before continuing." % (cmd)
        print "( %s )\n" % (how)
        broken = True
    return broken


def check_file(f, inpkg):
    """check_file looks to see if a file exists somewhere under /usr
    (see _find_file).  If not found, report a diagnostic that includes
    a convenient way to install the file.
    """
    broken = False
    print ("\nLooking for %s.  This can potentially take a few"
           "minutes... " % (f))
    if _find_file(f):
        print "Found!"
    else:
        print "Not found!\n"
        print ("You'll likely want to install the %s (Ubuntu, Debian, etc.) or"
               "similar package." % (inpkg))
        print "( sudo apt-get install %s )\n" % (inpkg)
        broken = True
    return broken


def main():
    """Check to see if we have the minimum set of requirements needed to
    build Otter's environment via "make env".
    """
    if not any([
        (can_execute("pip",
                     "http://pip.readthedocs.org/en/latest/installing.html")),
        (can_execute("virtualenv", "sudo pip install virtualenv")),
        (check_file("Python.h", "libpython-dev")),
    ]):
        print "\nLooks like you're good to go to run \"make env\"."
        sys.exit(0)

    # If we're here, something somewhere went wrong.
    sys.exit(1)

if __name__ == '__main__':
    main()
