import logging

import reconcile.openshift_resources as openshift_resources

import utils.gql as gql

from utils.config import get_config
from utils.openshift_resource import ResourceInventory
from utils.oc import StatusCodeError

from multiprocessing.dummy import Pool as ThreadPool
from functools import partial

QUERY = """
{
  namespaces: namespaces_v1 {
    name
    cluster {
      name
      serverUrl
      jumpHost {
          hostname
          knownHosts
          user
          port
          identity {
              path
              field
              format
          }
      }
      automationToken {
        path
        field
        format
      }
    }
  }
}
"""


def get_desired_state():
    gqlapi = gql.get_api()
    query = gqlapi.query(QUERY)['namespaces']
    for namespace_info in query:
        # adjust to match openshift_resources functions
        namespace_info['managedResourceTypes'] = ['Namespace']
    ri = ResourceInventory()
    oc_map = {}
    openshift_resources.init_specs_to_fetch(ri, oc_map, query)
    desired_state = [{"cluster": cluster, "namespace": namespace} for cluster, namespace, _, _ in ri]

    return oc_map, desired_state


def check_ns_exists(spec, oc_map):
    cluster = spec['cluster']
    namespace = spec['namespace']

    create = False
    try:
        oc_map[cluster].get(namespace, 'Namespace', namespace)
    except StatusCodeError:
        create = True

    return spec, create


def create_new_project(spec, oc_map):
    cluster = spec['cluster']
    namespace = spec['namespace']

    oc_map[cluster].new_project(namespace)


def run(dry_run=False, thread_pool_size=10):
    oc_map, desired_state = get_desired_state()

    pool = ThreadPool(thread_pool_size)
    check_ns_exists_partial = \
        partial(check_ns_exists, oc_map=oc_map)
    results = pool.map(check_ns_exists_partial, desired_state)
    specs_to_create = [spec for spec, create in results if create]

    for spec in specs_to_create:
        logging.info(['create', spec['cluster'], spec['namespace']])

        if not dry_run:
            create_new_project(spec, oc_map)
