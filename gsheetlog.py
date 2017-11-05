import csv
import httplib2
import os
import re
import time

import apiclient
import oauth2client

import click

from ratelimit import rate_limited


SCOPES = 'https://www.googleapis.com/auth/drive.readonly'
APP_NAME = 'gsheetlog'


def cache_dir():
    return os.path.join(os.getenv('HOME'), '.cache', APP_NAME)


class Http(httplib2.Http):

    """Http client with tweaks:

- forced cache: Google sets "no-cache" etc. on revision content; I
believe the content is immutable, but you can never tell with Google).
- rate limit: didn't find any documetation, trying to guess

    """

    _RATE = 5 # seconds per request

    def __init__(self, *args, **kwargs):
        super().__init__(cache=cache_dir(), *args, **kwargs)

    @rate_limited(_RATE)
    def _conn_request(self, *args, **kwargs):
        response, content = super()._conn_request(*args, **kwargs)
        try:
            del response['cache-control']
        except KeyError:
            pass
        return response, content

class GoogleDriveService:
    def __init__(self):
        app_dir = click.get_app_dir(APP_NAME)
        credential_path = os.path.join(app_dir, 'credentials.json')

        store = oauth2client.file.Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            client_secret_file = os.path.join(app_dir, 'client_secret.json')
            flow = oauth2client.client.flow_from_clientsecrets(client_secret_file, SCOPES)
            flow.user_agent = APP_NAME
            flags = oauth2client.tools.argparser.parse_args('')
            credentials = oauth2client.tools.run_flow(flow, store, flags)
            print('Storing credentials to ' + credential_path)

        self.http = credentials.authorize(Http())

        # Using API v2, because v3 lists revisions, but the revision objects have less fields, notably lastModifyingUser
        # and exportLinks are missing. Not sure why: the structure in the API docs looks identical. I thought it could
        # have something to do with OAuth2 scopes (for example, exportLinks silently disappears if we use API v2 and
        # authenticate for ".../drive.metadata.readonly"), but tweaking that didn't bring any observable changes.
        self.service = apiclient.discovery.build('drive', 'v2', http=self.http)

    def list_revisions(self, file_id):
        response = self.service.revisions().list(fileId=file_id).execute()
        revisions = response['items']
        while 'nextPageToken' in response:
            response = self.service.revisions().list(fileId=file_id, pageToken=response['nextPageToken']).execute()
            revisions += response['items']
        return revisions

    def request(self, url, *args, **kwargs):
        return self.http.request(url, *args, **kwargs)


def strip_file_id(file_id_or_url):
    url_match = re.match('https://docs.google.com/spreadsheets/d/([^/]+)', file_id_or_url)
    if url_match is not None:
        return url_match.group(1)
    else:
        return file_id_or_url


class DownloadError(Exception):
    def __init__(self, response):
        super().__init__(f"HTTP {response.status}")


def load_revision(service, revision):
    response, content = service.request(
        revision['exportLinks']['text/csv'],
        headers={'cache-control': 'min-fresh=-100000000000'}
    )
    from pprint import pprint
    if response.status != 200:
        raise DownloadError(response)
    return list(csv.reader(content.decode('utf-8').split('\n')))


@click.command()
@click.argument('file_id_or_url')
def main(file_id_or_url):
    file_id = strip_file_id(file_id_or_url)
    service = GoogleDriveService()
    revisions = service.list_revisions(file_id)
    for revision in revisions:
        revision['content'] = load_revision(service, revision)
        from pprint import pprint
        pprint(revision)
