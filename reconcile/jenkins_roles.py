import logging

import utils.gql as gql

from utils.jenkins_api import JenkinsApi


PERMISSIONS_QUERY = """
{
  permissions: permissions_v1 {
    service
    ...on PermissionJenkinsRole_v1 {
      instance
      role
      token {
        path
        field
      }
    }
  }
}
"""

ROLES_QUERY = """
{
  roles: roles_v1 {
    name
    users {
      redhat_username
    }
    bots {
      redhat_username
    }
    permissions {
      service
      ...on PermissionJenkinsRole_v1 {
        instance
        role
        token {
          path
          field
        }
      }
    }
  }
}
"""


def get_jenkins_map():
    gqlapi = gql.get_api()
    permissions = gqlapi.query(PERMISSIONS_QUERY)['permissions']

    jenkins_permissions = \
        [p for p in permissions if p['service'] == 'jenkins-role']

    jenkins_map = {}
    for jp in jenkins_permissions:
        instance = jp['instance']
        if instance in jenkins_map:
            continue

        token = jp['token']
        jenkins = JenkinsApi(token, False)
        jenkins_map[instance] = jenkins

    return jenkins_map


def get_current_state(jenkins_map):
    current_state = []

    for instance, jenkins in jenkins_map.items():
        roles = jenkins.get_all_roles()
        for role_name, users in roles.items():
            if role_name == 'anonymous':
              continue

            for user in users:
                current_state.append({
                    "instance": instance,
                    "role": role_name,
                    "user": user
                })

    return current_state


def get_desired_state():
    gqlapi = gql.get_api()
    roles = gqlapi.query(ROLES_QUERY)['roles']

    desired_state = []
    for r in roles:
        for p in r['permissions']:
            if p['service'] != 'jenkins-role':
                continue

            for u in r['users']:
                desired_state.append({
                    "instance": p['instance'],
                    "role": p['role'],
                    "user": u['redhat_username']
                })
            for u in r['bots']:
                if u['redhat_username'] is None:
                    continue

                desired_state.append({
                    "instance": p['instance'],
                    "role": p['role'],
                    "user": u['redhat_username']
                })

    return desired_state


def calculate_diff(current_state, desired_state):
    diff = []
    users_to_assign = \
        subtract_states(desired_state, current_state, "assign_role_to_user")
    diff.extend(users_to_assign)
    users_to_unassign = \
        subtract_states(current_state, desired_state, "unassign_role_from_user")
    diff.extend(users_to_unassign)

    return diff


def subtract_states(from_state, subtract_state, action):
    result = []

    for f_user in from_state:
        found = False
        for s_user in subtract_state:
            if f_user != s_user:
                continue
            found = True
            break
        if not found:
            result.append({
                "action": action,
                "instance": f_user['instance'],
                "role": f_user['role'],
                "user": f_user['user']
            })

    return result


def act(diff, jenkins_map):
    instance = diff['instance']
    role = diff['role']
    user = diff['user']
    action = diff['action']

    if action == "assign_role_to_user":
        jenkins_map[instance].assign_role_to_user(role, user)
    elif action == "unassign_role_from_user":
        jenkins_map[instance].unassign_role_from_user(role, user)
    else:
        raise Exception("invalid action: {}".format(action))


def run(dry_run=False):
    jenkins_map = get_jenkins_map()
    current_state = get_current_state(jenkins_map)
    desired_state = get_desired_state()
    diffs = calculate_diff(current_state, desired_state)

    for diff in diffs:
        logging.info(diff.values())

        if not dry_run:
            act(diff, jenkins_map)
