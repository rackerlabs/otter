def execute_one_config(log, transaction_id, group_uuid, launch_config):
	id = "{}.{}".format(group_uuid, uuid.v4())
	# Add job blob
	# Fire off job working process
	# eventually calls complete_pending_job()
	return id

def add_job_record(log, transaction_id, data):