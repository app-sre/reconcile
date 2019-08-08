import time
import requests

from utils.retry import retry


class RawGithubApi(object):
    """
    REST based GH interface

    Unfortunately this needs to be used because PyGithub does not yet support
    checking pending invitations
    """

    BASE_URL = "https://api.github.com"
    BASE_HEADERS = {
        'Accept': 'application/vnd.github.v3+json,'
        'application/vnd.github.dazzler-preview+json'
    }

    def __init__(self, password):
        self.password = password

    def headers(self, headers={}):
        new_headers = headers.copy()
        new_headers.update(self.BASE_HEADERS)
        new_headers['Authorization'] = "token %s" % (self.password,)
        return new_headers

    def patch(self, url):
        res = requests.patch(url, headers=self.headers())
        res.raise_for_status()
        return res

    @retry(exceptions=Exception, max_attempts=3)
    def query(self, url, headers={}):
        h = self.headers(headers)

        attempt = 0
        attempts = 3
        while attempt < attempts:
            try:
                res = requests.get(self.BASE_URL + url, headers=h)
                res.raise_for_status()
                break
            except Exception as e:
                attempt += 1
                if attempt == attempts:
                    raise e
                else:
                    time.sleep(attempt)

        result = res.json()

        if isinstance(result, list):
            elements = []

            for element in result:
                elements.append(element)

            while 'last' in res.links and 'next' in res.links:
                if res.links['last']['url'] == res.links['next']['url']:
                    req_url = res.links['next']['url']
                    res = requests.get(req_url, headers=h)

                    try:
                        res.raise_for_status()
                    except Exception as e:
                        raise Exception(e.message)

                    for element in res.json():
                        elements.append(element)

                    return elements
                else:
                    req_url = res.links['next']['url']
                    res = requests.get(req_url, headers=h)

                    try:
                        res.raise_for_status()
                    except Exception as e:
                        raise Exception(e.message)

                    for element in res.json():
                        elements.append(element)

            return elements

        return result

    def org_invitations(self, org):
        invitations = self.query('/orgs/{}/invitations'.format(org))

        return [
            login for login in (
                invitation.get('login') for invitation in invitations
            ) if login is not None
        ]

    def team_invitations(self, team_id):
        invitations = self.query('/teams/{}/invitations'.format(team_id))

        return [
            login for login in (
                invitation.get('login') for invitation in invitations
            ) if login is not None
        ]

    def repo_invitations(self):
        return self.query('/user/repository_invitations')

    def accept_repo_invitation(self, invitation_id):
        url = self.BASE_URL + \
            '/user/repository_invitations/{}'.format(invitation_id)
        res = self.patch(url)
        res.raise_for_status()
