import csv
from itertools import zip_longest
import os
from pprint import pprint
import re
import sys

import httplib2

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

    _WAIT = 10 # seconds per request

    def __init__(self, *args, **kwargs):
        super().__init__(cache=cache_dir(), *args, **kwargs)

    @rate_limited(every=_WAIT)
    def _conn_request(self, *args, **kwargs):
        response, content = super()._conn_request(*args, **kwargs)
        response['cache-control'] = 'ERASED'
        response['expires'] = 'Fri, 01 Jan 9999 00:00:00 GMT'
        return response, content


class DownloadError(Exception):
    def __init__(self, response):
        super().__init__(f"HTTP {response.status}")


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

    def get_file_metadata(self, file_id):
        return self.service.files().get(fileId=file_id).execute()

    def _list(self, api, **kwargs):
        response = api.list(**kwargs).execute()
        items = response['items']
        while 'nextPageToken' in response:
            response = api.list(**kwargs, pageToken=response['nextPageToken']).execute()
            items += response['items']
        return items

    def list_revisions(self, file_id):
        return self._list(self.service.revisions(), fileId=file_id)

    def list_folder(self, folder_id):
        return self._list(self.service.children(), folderId=folder_id)

    def load_revision(self, revision):
        response, content = self.http.request(
            revision['exportLinks']['text/csv'],
            headers={'cache-control': 'min-fresh=-100000000000'}
        )
        if response.status != 200:
            raise DownloadError(response)
        return list(csv.reader(content.decode('utf-8').split('\n')))


def extract_part(pattern, string):
    match = re.match(pattern, string)
    if match is not None:
        return match.group(1)
    return None


def extract_file_id(url):
    file_id = extract_part(r'https://docs.google.com/spreadsheets/d/([^/]+)', url)
    if file_id is None:
        file_id = extract_part(r'https://www.googleapis.com/drive/v\d/files/([^/]+)', url)
    return file_id


def extract_folder_id(url):
    return extract_part(r'https://drive.google.com/drive/folders/([^/]+)', url)


def diff_sheet(prev, cur):
    def enum_zip(x, y, fillvalue):
        return enumerate(zip_longest(x, y, fillvalue=fillvalue), 1)
    return [
        { 'row': row, 'col': col, 'prev': prev_cell, 'cur': cur_cell }
        for (row, (prev_row, cur_row)) in enum_zip(prev, cur, [])
        for (col, (prev_cell, cur_cell)) in enum_zip(prev_row, cur_row, '')
        if prev_cell != cur_cell
    ]


def get_file_id_list(service, urls):
    file_ids = []
    for url in urls:
        file_id = extract_file_id(url)
        if file_id is not None:
            file_ids.append(file_id)
        else:
            folder_id = extract_folder_id(url)
            if folder_id is not None:
                file_ids += [
                    extract_file_id(file['childLink'])
                    for file in service.list_folder(folder_id)
                ]
            else:
                raise ValueError("URL not understood")
    return file_ids


def gsheetlog(*urls):
    """Returns the change log for given urls as a list with one dict per
spreadsheet. Urls may point to spreadsheets or to folders of
spreadsheets (one level expanded).
    """
    service = GoogleDriveService()
    result = []
    for file_id in get_file_id_list(service, urls):
        revisions = service.list_revisions(file_id)
        cur = []
        for revision in revisions:
            prev = cur
            cur = service.load_revision(revision)
            revision['diff'] = diff_sheet(prev, cur)
        result.append({
            'file': service.get_file_metadata(file_id),
            'content': cur,
            'revisions': revisions,
        })
    return result


@click.command()
@click.argument('urls', nargs=-1)
def main(urls):
    pprint(gsheetlog(*urls))
