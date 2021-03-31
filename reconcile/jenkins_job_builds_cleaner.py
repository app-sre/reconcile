import logging
import re
import time

import reconcile.queries as queries

from reconcile.utils.jenkins_api import JenkinsApi

QONTRACT_INTEGRATION = 'jenkins-job-builds-cleaner'


def hours_to_ms(hours):
    return hours * 60 * 60 * 1000


def run(dry_run):
    jenkins_instances = queries.get_jenkins_instances()
    settings = queries.get_app_interface_settings()

    time_ms = time.time() * 1000

    for instance in jenkins_instances:
        instance_cleanup_rules = instance.get('buildsCleanupRules', [])
        if not instance_cleanup_rules:
            # Skip instance if no cleanup rules defined
            continue

        # Process cleanup rules, pre-compile as regexes
        cleanup_rules = []
        for rule in instance_cleanup_rules:
            cleanup_rules.append({
                'name': rule['name'],
                'name_re': re.compile(rule['name']),
                'keep_hours': rule['keep_hours'],
                'keep_ms': hours_to_ms(rule['keep_hours'])
            })

        instance_name = instance['name']
        token = instance['token']
        jenkins = JenkinsApi(token, ssl_verify=False, settings=settings)
        all_job_names = jenkins.get_job_names()

        delete_builds = []

        for job_name in all_job_names:
            builds = None
            for rule in cleanup_rules:
                if rule['name_re'].search(job_name):
                    # Fetch list of builds if we dont have it already
                    if not builds:
                        builds = jenkins.get_builds(job_name)
                    for build in builds:
                        build_id = build['id']
                        if time_ms - rule['keep_ms'] > build['timestamp']:
                            delete_builds.append({
                                'job_name': job_name,
                                'rule_name': rule['name'],
                                'rule_keep_hours': rule['keep_hours'],
                                'build_id': build['id'],
                            })

        todel_current = 0
        todel_total = len(delete_builds)
        for build in delete_builds:
            todel_current += 1
            job_name = build['job_name']
            build_id = build['build_id']
            progress_str = f"{todel_current}/{todel_total}"
            logging.info(['clean_job_builds', progress_str,
                         instance_name, job_name, build['rule_name'],
                         build['rule_keep_hours'], build_id])
            if not dry_run:
                try:
                    jenkins.delete_build(build['job_name'], build['build_id'])
                except Exception as e:
                    msg = f"[{instance_name}] failed to delete " \
                          f"{job_name}/{build_id}. Error was: {e}"
                    logging.error(msg)
