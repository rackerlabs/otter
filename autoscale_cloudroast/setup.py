"""
Setup file for test_repo
"""

from setuptools import setup, find_packages

setup(
    name='test_repo',
    version='0.0.0',
    description='CloudCAFE based automated test repository for Autoscale',
    packages=find_packages(exclude=[]),
    package_data={'': ['LICENSE']},
    package_dir={'test_repo': 'test_repo'},
    include_package_data=True,
    license=open('LICENSE').read()
)
