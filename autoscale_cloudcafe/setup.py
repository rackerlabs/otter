"""
Setup file for autoscale_cloudcafe
"""

from setuptools import setup, find_packages

setup(
    name='autoscale_cloudcafe',
    version='0.0.0',
    description='CloudCAFE based automated test repository for Autoscale',
    packages=find_packages(exclude=[]),
    package_data={'': ['LICENSE']},
    package_dir={'autoscale_cloudcafe': 'autoscale_cloudcafe'},
    include_package_data=True,
    license=open('LICENSE').read()
)
