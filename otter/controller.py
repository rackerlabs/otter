"""
TODO:
 * Migrate over to new storage model for state information
 * Lock yak shaving
 * cooldown
 * Eviction policy
 * 

Storage model for state information:
 * active list
  * Instance URI
  * Created time
 * pending list
  * Job ID
 * last touched information for group
 * last touched information for polciy

"""


def obey_config_change(log, transaction_id, scaling_group):
	"""
	Checks to make sure, after a scaling policy config change, that
	the current steady state is within the min and max.
	"""
	state = scaling_group.view_state()
	# TODO: Lock group
	# TODO: finish

def complete_pending_job(log, job_id, state):
	"""
	Updates the state with a pending job, mark it as completed

	State is True if we succeeded, False if we didn't

	Recursive Forkbomb pseudocode magic!  Fill in later! That's why it's magic!
	"""

def maybe_execute_scaling_policy(log, transaction_id, scaling_group, policy):
    """
	Checks whether and how much a scaling policy can be executed.
	
	:param scaling_group: an IScalingGroup provider
	:param policy_id: the policy id to execute
	
	Current plan: If a user executes a policy, return whether or not it will be
	executed. If it is going to be executed, ????
	
	:return: a ``Deferred`` that fires with the audit log ID of this job
	:raises: Some exception about why you don't want to execute the policy. This
	Exception should also have an audit log id
	
	policy example:
	       {
	            "name": "scale up by 10",
	            "change": 10,
	            "cooldown": 5
	        },
	
	
	"""
	# TODO: Lock group
	state = scaling_group.view_state()
    if check_cooldowns(log, scaling_group, policy_id, "i got this data from the db"):
    	(new_state, delta) = calculate_new_steady_state(log, state, policy)
        execute_launch_config(log, transaction_id, state, scaling_group, delta)
        record_policy_trigger_time(log, scaling_group, policy_id, time.time())
    else:
        record_policy_decision_time(log, scaling_group, policy_id, time.time(),
                                    'i was rejected because...')

def check_cooldowns(*args):
	return True

def calculate_new_steady_state(log, state, policy):
	if "change" in policy:
		return (state['steadyState'] + policy["change"], policy["change"])
	else:
		raise NotImplemented()

def find_server_to_evict(log, scaling_group):

def execute_launch_config(log, state, scaling_group, delta):
	launch_config = scaling_group.view_launch_config()
	# Evicting servers cherfully ignored
	for i in range(abs(delta)):
		state['pending'].append(supervisor.execute_one_config(log, transaction_id, 
			scaling_group.uuid, launch_config))