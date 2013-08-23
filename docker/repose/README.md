# Repose container
This is for setting up [repose](http://openrepose.org/) to do auth and rate limiting in front of otter.

## Expected environment variables:

### Authentication/authorization
- `IDENTITY_USERNAME` - (required) admin username for identity
- `IDENTITY_PASSWORD` - (required) password corresp to the admin username for identity
- `IDENTITY_URL` - (optional) url of the identity server

### Otter
- `OTTER_IP` - (required) ip of host where the otter rest api is running
- `OTTER_PORT` - (optional) port of the otter rest api; defaults to 9000

### Deployment Information
- `AUTOSCALE_REGION` - (required) what region the autoscale endpoint is for
- `AUTOSCALE_URL` - (optional) the deployed URL of autoscale; defaults to https://[region].autoscale.api.rackspacecloud.com/v1.0

## Running after building

Example:

`sudo docker run -h "repose" -i -t -e IDENTITY_USERNAME=... -e IDENTITY_PASSWORD=... -e OTTER_IP=localhost -e AUTOSCALE_REGION="ord" otter/repose start_repose.sh`
