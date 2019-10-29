import sys
import shutil
import semver

import utils.gql as gql
import utils.threaded as threaded
import reconcile.openshift_base as ob
import reconcile.queries as queries

from utils.terrascript_client import TerrascriptClient as Terrascript
from utils.terraform_client import OR, TerraformClient as Terraform
from utils.openshift_resource import ResourceInventory
from utils.oc import OC_Map
from utils.defer import defer

TF_NAMESPACES_QUERY = """
{
  namespaces: namespaces_v1 {
    name
    managedTerraformResources
    terraformResources {
      provider
      ... on NamespaceTerraformResourceRDS_v1 {
        account
        identifier
        defaults
        overrides
        output_resource_name
      }
      ... on NamespaceTerraformResourceS3_v1 {
        account
        region
        identifier
        defaults
        overrides
        output_resource_name
      }
      ... on NamespaceTerraformResourceElastiCache_v1 {
        account
        identifier
        defaults
        overrides
        output_resource_name
      }
      ... on NamespaceTerraformResourceServiceAccount_v1 {
        account
        identifier
        variables
        policies
        user_policy
        output_resource_name
      }
      ... on NamespaceTerraformResourceSQS_v1 {
        account
        region
        identifier
        defaults
        overrides
        output_resource_name
        queues {
          key
          value
        }
      }
    }
    cluster {
      name
      serverUrl
      automationToken {
        path
        field
        format
      }
    }
  }
}
"""

QONTRACT_INTEGRATION = 'terraform_resources'
QONTRACT_INTEGRATION_VERSION = semver.format_version(0, 5, 2)
QONTRACT_TF_PREFIX = 'qrtf'


def populate_oc_resources(spec, ri):
    if spec.oc is None:
        return
    for item in spec.oc.get_items(spec.resource,
                                  namespace=spec.namespace):
        openshift_resource = OR(item,
                                QONTRACT_INTEGRATION,
                                QONTRACT_INTEGRATION_VERSION)
        ri.add_current(
            spec.cluster,
            spec.namespace,
            spec.resource,
            openshift_resource.name,
            openshift_resource
        )


def fetch_current_state(namespaces, thread_pool_size):
    ri = ResourceInventory()
    oc_map = OC_Map(namespaces=namespaces, integration=QONTRACT_INTEGRATION)
    state_specs = \
        ob.init_specs_to_fetch(
            ri,
            oc_map,
            namespaces,
            override_managed_types=['Secret']
        )
    threaded.run(populate_oc_resources, state_specs, thread_pool_size, ri=ri)

    return ri, oc_map


def setup(print_only, thread_pool_size):
    gqlapi = gql.get_api()
    accounts = queries.get_aws_accounts()
    namespaces = gqlapi.query(TF_NAMESPACES_QUERY)['namespaces']
    tf_namespaces = [namespace_info for namespace_info in namespaces
                     if namespace_info.get('managedTerraformResources')]
    ri, oc_map = fetch_current_state(tf_namespaces, thread_pool_size)
    ts = Terrascript(QONTRACT_INTEGRATION,
                     QONTRACT_TF_PREFIX,
                     thread_pool_size,
                     accounts,
                     oc_map)
    working_dirs, error = ts.dump(print_only)
    if error:
        cleanup_and_exit(status=error, working_dirs=working_dirs)
    tf = Terraform(QONTRACT_INTEGRATION,
                   QONTRACT_INTEGRATION_VERSION,
                   QONTRACT_TF_PREFIX,
                   working_dirs,
                   thread_pool_size)
    existing_secrets = tf.get_terraform_output_secrets()
    ts.populate_resources(tf_namespaces, existing_secrets)
    _, error = ts.dump(print_only, existing_dirs=working_dirs)
    if error:
        cleanup_and_exit(status=error, working_dirs=working_dirs)

    return ri, oc_map, tf


def cleanup_and_exit(tf=None, status=False, working_dirs={}):
    if tf is None:
        for wd in working_dirs.values():
            shutil.rmtree(wd)
    else:
        tf.cleanup()
    sys.exit(status)


@defer
def run(dry_run=False, print_only=False,
        enable_deletion=False, io_dir='throughput/',
        thread_pool_size=10, defer=None):
    ri, oc_map, tf = setup(print_only, thread_pool_size)
    defer(lambda: oc_map.cleanup())
    if print_only:
        cleanup_and_exit()
    if tf is None:
        err = True
        cleanup_and_exit(tf, err)

    deletions_detected, err = tf.plan(enable_deletion)
    if err:
        cleanup_and_exit(tf, err)
    if deletions_detected:
        if enable_deletion:
            tf.dump_deleted_users(io_dir)
        else:
            cleanup_and_exit(tf, deletions_detected)

    if dry_run:
        cleanup_and_exit(tf)

    err = tf.apply()
    if err:
        cleanup_and_exit(tf, err)

    tf.populate_desired_state(ri)
    ob.realize_data(dry_run, oc_map, ri,
                    enable_deletion=enable_deletion,
                    recycle_pods=True)

    cleanup_and_exit(tf)
