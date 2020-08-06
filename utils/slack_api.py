import time

from slackclient import SlackClient
from sretoolbox.utils import retry

import utils.secret_reader as secret_reader


class UsergroupNotFoundException(Exception):
    pass


class SlackApi(object):
    """Wrapper around Slack API calls"""

    def __init__(self, token, settings=None, init_usergroups=True,
                 **chat_kwargs):
        slack_token = secret_reader.read(token, settings=settings)
        self.sc = SlackClient(slack_token)
        self.results = {}
        self.chat_kwargs = chat_kwargs
        if init_usergroups:
            self.initiate_usergroups()

    def chat_post_message(self, text):
        self.sc.api_call(
            "chat.postMessage",
            text=text,
            **self.chat_kwargs
        )

    def describe_usergroup(self, handle):
        usergroup = self.get_usergroup(handle)
        description = usergroup['description']

        user_ids = usergroup['users']
        users = self.get_users_by_ids(user_ids)

        channel_ids = usergroup['prefs']['channels']
        channels = self.get_channels_by_ids(channel_ids)

        return users, channels, description

    def get_usergroup_id(self, handle):
        usergroup = self.get_usergroup(handle)
        return usergroup['id']

    @retry()
    def initiate_usergroups(self):
        result = self.sc.api_call(
            "usergroups.list",
            include_users=True
        )
        if not result['ok']:
            raise Exception(result['error'])
        self.usergroups = result['usergroups']

    def get_usergroup(self, handle):
        usergroup = [g for g in self.usergroups if g['handle'] == handle]
        if len(usergroup) != 1:
            raise UsergroupNotFoundException(handle)
        [usergroup] = usergroup
        return usergroup

    def update_usergroup(self, id, channels_list, description):
        channels = ','.join(channels_list)
        self.sc.api_call(
            "usergroups.update",
            usergroup=id,
            channels=channels,
            description=description,
        )

    def update_usergroup_users(self, id, users_list):
        users = ','.join(users_list)
        self.sc.api_call(
            "usergroups.users.update",
            usergroup=id,
            users=users,
        )

    def get_channels_by_names(self, channels_names):
        return {k: v for k, v in self.get('channels').items()
                if v in channels_names}

    def get_channels_by_ids(self, channels_ids):
        return {k: v for k, v in self.get('channels').items()
                if k in channels_ids}

    def get_users_by_names(self, user_names):
        return {k: v for k, v in self.get('users').items()
                if v in user_names}

    def get_users_by_ids(self, users_ids):
        return {k: v for k, v in self.get('users').items()
                if k in users_ids}

    def get(self, type):
        result_key = 'members' if type == 'users' else type
        results = {}
        cursor = ''

        if type in self.results:
            return self.results[type]

        while True:
            result = self.sc.api_call(
                "{}.list".format(type),
                cursor=cursor
            )
            if 'error' in result and result['error'] == 'ratelimited':
                time.sleep(1)
                continue
            for r in result[result_key]:
                results[r['id']] = r['name']
            cursor = result['response_metadata']['next_cursor']
            if cursor == '':
                break

        self.results[type] = results
        return results

    def create_channel(self, name, is_private=True):
        result = self.sc.api_call(
            "conversations.create",
            name=name,
            is_private=is_private,
            **self.chat_kwargs
        )
        return result

    def get_channel_list(self):
        response = self.sc.api_call(
            "conversations.list",
            types=["private_channel"],
            **self.chat_kwargs
        )
        channel_name = [{c['name']:c['id']} for c in response["channels"]]
        return channel_name

    def invite_users_to_channel(self, channel, users):
        response = self.sc.api_call(
            "conversations.invite",
            channel=channel,
            users=users,
            **self.chat_kwargs
        )
        return response

    def chat_post_message_to_channel(self, channel, text):
        self.sc.api_call(
            "chat.postMessage",
            channel=channel,
            text=text,
            **self.chat_kwargs
        )

    def get_user_list_by_names(self, user_names):
        return [k for k, v in self.get('users').items()
                if v in user_names]
