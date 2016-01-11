
def publish_to_cloudfeeds(event, log=None):
    """
    Publish an event dictionary to cloudfeeds.
    """
    return service_request(
        ServiceType.CLOUD_FEEDS, 'POST',
        append_segments('autoscale', 'events'),
        # note: if we actually wanted a JSON response instead of XML,
        # we'd have to pass the header:
        # 'accept': ['application/vnd.rackspace.atom+json'],
        headers={
            'content-type': ['application/vnd.rackspace.atom+json']},
        data=event, log=log, success_pred=has_code(201),
        json_response=False)

