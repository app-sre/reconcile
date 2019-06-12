import time
import pypd
import datetime

from slackclient import SlackClient

import utils.vault_client as vault_client


class PagerDutyApi(object):
    """Wrapper around PagerDuty API calls"""

    def __init__(self, token):
        token_path = token['path']
        token_field = token['field']
        pd_api_key = vault_client.read(token_path, token_field)
        pypd.api_key = pd_api_key

    def get_final_schedule(self, schedule_id):
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            schedule = pypd.Schedule.fetch(
                id=schedule_id,
                since=now,
                until=now,
                time_zone='UTC')
        except requests.exceptions.HTTPError as e:
            return None

        entries = schedule['final_schedule']['rendered_schedule_entries']
        if len(entries) != 1:
            return None

        [entry] = entries
        return entry['user']['summary']
