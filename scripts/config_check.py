"""
Script that checks that no config file has a plaintext password.

Also explicitly forbids checking in config.json.
"""

import json
import subprocess

changed_files = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only"]).split('\n')


def look_for_password(dictionary):
    """
    Check for dangerous plaintext passwords.

    Search through a dictionary to see if there is a password value that
    is not "REPLACE_WITH_REAL_PASSWORD" or a username value that is not
    "REPLACE_WITH_REAL_USERNAME".
    """
    for key, val in dictionary.iteritems():
        if key.lower().strip() == "password":
            if val != "REPLACE_WITH_REAL_PASSWORD":
                raise Exception('Password values should always be '
                                '"REPLACE_WITH_REAL_PASSWORD"')
        if key.lower().strip() == "username":
            if val != "REPLACE_WITH_REAL_USERNAME":
                raise Exception('Password values should always be '
                                '"REPLACE_WITH_REAL_USERNAME"')

        if isinstance(val, dict):
            look_for_password(val)


for f in changed_files:
    if f.lower() == 'config.json':
        raise Exception("DO NOT commit 'config.json'")

    if f.endswith(".json"):
        with open(f) as fp:
            look_for_password(json.load(fp))
