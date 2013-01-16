""" Hash key related library code """
import random

""" Cribbed off of the way ELE works """


def generate_random_str(len):
    """ Generate a random string of size len """
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    out_str = ""
    for i in xrange(len):
        out_str += random.choice(chars)
    return out_str
