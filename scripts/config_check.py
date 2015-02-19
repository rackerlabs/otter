"""
Script that checks that no config file has a plaintext password.

Also explicitly forbids checking in config.json.
"""

import json
import re
import subprocess

changed_files = subprocess.check_output(
    ["git", "diff", "--cached", "--name-only"]).split('\n')

USERNAME_TEMPLATE = 'REPLACE_WITH_REAL_USERNAME'
PASSWORD_TEMPLATE = 'REPLACE_WITH_REAL_PASSWORD'


def throw_exception(attribute, setting):
    """
    Raises an Exception with the appropriate error message.

    :param str attribute: Either Username or Password.
    :param str setting: The intended setting for the given attribute.
    """
    raise Exception('%s values should always be %s' % (attribute, setting))


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
            if val != PASSWORD_TEMPLATE:
                throw_exception("Passwords", PASSWORD_TEMPLATE)
        if key.lower().strip() == "username":
            if val != USERNAME_TEMPLATE:
                throw_exception("Usernames", USERNAME_TEMPLATE)

        if isinstance(val, dict):
            look_for_password_in_json(val)


def look_for_passwords_in_shell_script(lines):
    """
    Check for dangerous plaintext passwords in a text file organized by lines.
    Essentially performs a grep for USERNAME= and PASSWORD= and makes sure they
    have well-known standard values REPLACE_WITH_REAL_USERNAME, etc.

    :param list lines: A list of lines in the script file.
    """

    re_username = re.compile("USERNAME=")
    re_password = re.compile("PASSWORD=")
    re_username_value = re.compile(USERNAME_TEMPLATE)
    re_password_value = re.compile(PASSWORD_TEMPLATE)

    usernames = [l for l in lines if re_username.search(l)]
    real_uns = [l for l in usernames if not re_username_value.search(l)]
    passwords = [l for l in lines if re_password.search(l)]
    real_pws = [l for l in passwords if not re_password_value.search(l)]

    if len(real_uns) > 0:
        throw_exception("Usernames", USERNAME_TEMPLATE)

    if len(real_pws) > 0:
        throw_exception("Passwords", PASSWORD_TEMPLATE)


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
