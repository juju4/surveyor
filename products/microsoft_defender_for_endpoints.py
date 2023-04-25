import configparser
import json
import logging
import os

import requests
from typing import Union
from common import Product, Tag, Result

PARAMETER_MAPPING: dict[str, dict[str, Union[str, list[str]]]] = {
    'process_name': {'table':'DeviceProcessEvents','field':'FolderPath',
                     'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']},
    'filemod': {'table':'DeviceFileEvents','field':'FolderPath', 
                'projections':['DeviceName', 'InitiatingProcessAccountName','InitatingProcessFolderPath','ProcessCommandLine']},
    'ipaddr': {'table':'DeviceNetworkEvents','field':'RemoteIP', 
               'projections':['DeviceName', 'InitiatingProcessAccountName','InitatingProcessFolderPath','ProcessCommandLine']},
    'cmdline': {'table':'DeviceProcessEvents','field':'ProcessCommandLine', 
                'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']},
    'digsig_publisher': {'table':'DeviceFileCertificateInfo','field':'Signer', 
                         'additional':'| join kind=inner DeviceProcessEvents on $left.SHA1 == $right.SHA1',
                         'projections':['DeviceName', 'AccountName','FolderPath','ProcessCommandLine']},
    'domain': {'table':'DeviceNetworkEvents','field':'RemoteUrl', 
               'projections':['DeviceName', 'InitiatingProcessAccountName','InitatingProcessFolderPath','ProcessCommandLine']},
    'internal_name': {'table':'DeviceProcessEvents','field':'ProcessVersionInfoInternalFileName', 
                      'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']},
    'md5': {'table':'DeviceProcessEvents','field':'MD5',
            'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']},
    'sha1':{'table':'DeviceProcessEvents','field':'SHA1',
            'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']},
    'sha256':{'table':'DeviceProcessEvents','field':'SHA256',
              'projections':['DeviceName','AccountName','FolderPath','ProcessCommandLine']}
}

class DefenderForEndpoints(Product):
    """
    Surveyor implementation for product "Microsoft Defender For Endpoint"
    """
    product: str = 'dfe'
    creds_file: str  # path to credential configuration file
    _token: str  # AAD access token

    def __init__(self, profile: str, creds_file: str, **kwargs):
        if not os.path.isfile(creds_file):
            raise ValueError(f'Credential file {creds_file} does not exist')

        self.creds_file = creds_file

        super().__init__(self.product, profile, **kwargs)

    def _authenticate(self) -> None:
        config = configparser.ConfigParser()
        config.sections()
        config.read(self.creds_file)

        if self.profile not in config:
            raise ValueError(f'Profile {self.profile} is not present in credential file')

        section = config[self.profile]

        if 'tenantId' not in section or 'appId' not in section or 'appSecret' not in section:
            raise ValueError(f'Credential file must contain tenantId, appId, and appSecret values')

        #self._token = self._get_aad_token(section['tenantId'], section['appId'], section['appSecret'])

    def _get_aad_token(self, tenant_id: str, app_id: str, app_secret: str) -> str:
        """
        Retrieve an authentication token from Azure Active Directory using app ID and secret.
        """
        self.log.debug(f'Acquiring AAD access token for tenant {tenant_id} and app {app_id}')

        body = {
            "resource": 'https://api.securitycenter.windows.com',
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "client_credentials"
        }

        url = f"https://login.windows.net/{tenant_id}/oauth2/token"

        response = requests.get(url, data=body)
        response.raise_for_status()

        return response.json()['access_token']

    def _post_advanced_query(self, data: dict, headers: dict) -> list[Result]:
        results = set()

        try:
            url = "https://api.securitycenter.microsoft.com/api/advancedqueries/run"
            response = requests.post(url, data=json.dumps(data).encode('utf-8'), headers=headers)

            if response.status_code == 200:
                # TODO: Make this more dynamic since the column names for AccountName, ProcessCommandLine, and FolderPath aren't always consistent
                for res in response.json()["Results"]:
                    result = Result(res["DeviceName"], res["AccountName"], res["ProcessCommandLine"], res["FolderPath"],
                                    (res["Timestamp"],))
                    results.add(result)
            else:
                self._echo(f"Received status code: {response.status_code} (message: {response.json()})")
        except KeyboardInterrupt:
            self._echo("Caught CTRL-C. Rerun surveyor")
        except Exception as e:
            self._echo(f"There was an exception {e}")
            self.log.exception(e)

        return list(results)

    def _get_default_header(self) -> dict[str, str]:
        return {
            "Authorization": 'Bearer ' + self._token,
            "Content-Type": 'application/json',
            "Accept": 'application/json'
        }

    def process_search(self, tag: Tag, base_query: dict, query: str) -> None:
        query = query + self.build_query(base_query)

        query = query.rstrip()

        self.log.debug(f'Query: {query}')
        full_query = {'Query': query}

        #results = self._post_advanced_query(data=full_query, headers=self._get_default_header())
        #self._add_results(list(results), tag)

    def nested_process_search(self, tag: Tag, criteria: dict, base_query: dict) -> None:
        results : set = set()

        query_base = self.build_query(base_query)

        try:
            for search_field, terms in criteria.items():
                if search_field == 'query':
                    if isinstance(terms, list):
                        for query_entry in terms:
                            query_entry += query_base
                            self.process_search(tag, {}, query_entry)
                    else:
                        self.process_search(tag, base_query, terms)
                else:
                    all_terms = ', '.join(f"'{term}'" for term in terms)
                    if search_field in PARAMETER_MAPPING:
                        query = f"| where {PARAMETER_MAPPING[search_field]['field']} has_any ({all_terms})"
                    else:
                        self._echo(f'Query filter {search_field} is not supported by product {self.product}',
                                   logging.WARNING)
                        continue
                
                    query = f"{PARAMETER_MAPPING[search_field]['table']} {query} "

                    query += str(PARAMETER_MAPPING[search_field]['additional']) if 'additional' in PARAMETER_MAPPING[search_field] else ''

                    query += f" {query_base} | project {', '.join(PARAMETER_MAPPING[search_field]['projections'])}"

                    self.process_search(tag, {}, query)
        except KeyboardInterrupt:
            self._echo("Caught CTRL-C. Returning what we have...")

        self._add_results(list(results), tag)

    def build_query(self, filters: dict) -> str:
        query_base = ''

        for key, value in filters.items():
            if key == 'days':
                query_base += f'| where Timestamp > ago({value}d)'
            elif key == 'minutes':
                query_base += f'| where Timestamp > ago({value}m)'
            elif key == 'hostname':
                query_base += f'| where DeviceName contains "{value}"'
            elif key == 'username':
                query_base += f'| where AccountName contains "{value}"'
            else:
                self._echo(f'Query filter {key} is not supported by product {self.product}', logging.WARNING)

        return query_base

    def get_other_row_headers(self) -> list[str]:
        return ['Timestamp']