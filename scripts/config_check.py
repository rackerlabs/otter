"""
Script that checks that no config file has a plaintext password.

Also explicitly forbids checking in config.json.
"""

import json
import re
import subprocess

changed_files = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only"]).split('\n')


def look_for_password_in_json(dictionary):
    """
    Check for dangerous plaintext passwords.

    Search through a dictionary to see if there is a password value that
    is not "REPLACE_WITH_REAL_PASSWORD" or a username value that is not
    "REPLACE_WITH_REAL_USERNAME".

    :param dict dictionary: The decoded JSON structure to verify.
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
            look_for_password_in_json(val)


def look_for_passwords_in_shell_script(lines):
    """
    Check for dangerous plaintext passwords in a text file organized by lines.
    Essentially performs a grep for USERNAME= and PASSWORD= and makes sure they
    have well-known standard values REPLACE_WITH_REAL_USERNAME, etc.

    :param list lines: A list of lines in the script file.
    """

    un_template = 'REPLACE_WITH_REAL_USERNAME'
    pw_template = 'REPLACE_WITH_REAL_TEMPLATE'
    re_username = re.compile("USERNAME=")
    re_password = re.compile("PASSWORD=")
    re_username_value = re.compile(un_template)
    re_password_value = re.compile(pw_template)

    usernames = [l for l in lines if re_username.search(l)]
    real_uns = [l for l in usernames if not re_username_value.search(l)]
    passwords = [l for l in lines if re_password.search(l)]
    real_pws = [l for l in passwords if not re_password_value.search(l)]

    if len(real_uns) > 0:
        raise Exception(
            "Usernames should always be %s" % un_template
        )

    if len(real_pws) > 0:
        raise Exception(
            "Passwords should always be %s" % pw_template
        )


for f in changed_files:
    if f.lower() in ['config.json', 'config.sh']:
        raise Exception("DO NOT commit '%s'" % f.lower())

    if f.endswith(".json"):
        try:
            with open(f) as fp:
                look_for_password_in_json(json.load(fp))
        except Exception, e:
            raise Exception("File %s: %s" % (f, e.args[0]))

    if f.endswith(".sh"):
        try:
            with open(f) as fp:
                look_for_passwords_in_shell_script(fp.readlines())
        except Exception, e:
            raise Exception("File %s: %s" % (f, e.args[0]))
