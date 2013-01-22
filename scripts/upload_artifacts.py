"""
Upload a specified artifact to cloudfiles
"""

import os
import sys
from libcloud.storage.types import Provider, ContainerDoesNotExistError
from libcloud.storage.providers import get_driver

RS_USERNAME = os.environ['RACKSPACE_USERNAME']
RS_API_KEY = os.environ['RACKSPACE_API_KEY']
container_name = os.environ.get('CONTAINER_NAME') or 'otter_artifacts'

driver = get_driver(Provider.CLOUDFILES_US)(RS_USERNAME, RS_API_KEY)

# Create a container if it doesn't already exist
try:
    container = driver.get_container(container_name=container_name)
except ContainerDoesNotExistError:
    container = driver.create_container(container_name=container_name)
    driver.enable_container_cdn(container=container)

for artifact in sys.argv[1:]:
    print 'Uploading artifact: {0!r}...'.format(artifact),
    obj = driver.upload_object_via_stream(iterator=open(artifact, 'r'),
                                          container=container,
                                          object_name=artifact)
    print '{0} KB'.format((obj.size / 1024))
