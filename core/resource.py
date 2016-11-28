import os
from collections import namedtuple
from collections import OrderedDict
import json
import copy
import yaml

import logging
logger = logging.getLogger(__name__)

import plugins.bitbucket.api as bitbucket_api
import plugins.github.api as github_api

import settings
import creds

def to_dict(o):
    if type(o) == ResourceDetails:
        return _ResourceDetails_to_dict(o)
    elif type(o) == PullRequestSummary:
        return _PullRequestSummary_to_dict(o)
    elif type(o) == ResourceConfiguration:
        return _ResourceConfiguration_to_dict(o)
    else:
        logger.error("Unknown type: '{}'.".format(type(o)))
        return {}



'''
    Resource

    This is to provide information of translatable resources defined in resource configuration file.
'''

# Translation
#
# keys              values
# ----------------------------------------------------------------------
# language_code     Language code for the translation.
# path              Path of the translation.
Translation = namedtuple('Translation', 'language_code, path')

def _Translation_to_dict(o):
    return o._asdict()

def _to_translations(translations):
    results = []
    for t in translations:
        results.append(Translation(t.language_code, t.path))
    return results

# Resource
#
# keys              values
# ----------------------------------------------------------------------
# path              Path of the resource.
# translations      List of translation for the resource (Translation tuple).
Resource = namedtuple('Resource', 'path, translations')

def _Resource_to_dict(o):
    translations = []
    for t in o.translations:
        translations.append(_Translation_to_dict(t))
    return {'path': o.path, 'translations': translations}

def _to_resources(resources):
    results = []
    for r in resources:
        results.append(Resource(r.path, _to_translations(r.translations)))
    return results

# Resource Reposiory Details.
#
# keys              values
# ----------------------------------------------------------------------
# url               URL to the repository.
# platform          Resource repository platform name (e.g. Bitbucket).
# owner             Resource repository owner of the platform (e.g. inindca)
# name              Resource repository name.
# branch            Branch of the repository (e.g. master).
# resources         List of resources (Resource tuple).
ResourceDetails = namedtuple('ResourceDetails', 'url, platform, owner, name, branch, resources') 

def _ResourceDetails_to_dict(o):
    resources = []
    for res in o.resources:
        resources.append(_Resource_to_dict(res))
    return {'url': o.url, 'platform': o.platform, 'owner': o.owner, 'name': o.name, 'branch': o.branch, 'resources': resources}

def get_details(config_filename):
    """
    Return resource details, or None on any errors.
    """
    c = get_configuration(filename=config_filename)
    if c:
        return ResourceDetails(c.repository_url, c.repository_platform, c.repository_owner, c.repository_name, c.repository_branch, _to_resources(c.resources))
    else:    
        logger.error("Failed to get configuration for resource repository details. configuration file: '{}'.".format(config_filename))
        return None

'''
    Pull Request Summary

'''
# Pull Request Summary.
#
# key                           value
# -------------------------------------------------------
# date                          Date of pull request is issued.
# number                        Pull request number.
# url                           URL to the pull request.
# state                         Pull rquest state. e.g. 'open'
PullRequestSummary = namedtuple('PullRequestSummary', 'date, number, url, state')

def _PullRequestSummary_to_dict(o):
    return {'date': o.date, 'number': o.number, 'url': o.url, 'state': o.state}

def _query_bitbucket_pullrequest(**kwargs):

    def _next_page(url, creds):
        headers = {'Content-Type': 'application/json'}
        try:
            r = requests.get(url, auth=(creds['username'], creds['userpasswd']), headers=headers)
            r.raise_for_status()
        except (RequestException, HTTPError) as e:
            logger.error(e)
            return None
        else:
            try:
                j = json.loads(ret.response.text, object_pairs_hook=OrderedDict)
            except ValueError as e:
                logger.error(e)
                return None
            else:
                return j

    c = creds.get('bitbucket')
    if not c:
        logger.error("Failed to get creds for bitbucket.")
        return None

    ret = bitbucket_api.get_pullrequests(kwargs['repository_owner'], kwargs['repository_name'], {'username': c.username, 'userpasswd': c.userpasswd})
    if not ret.succeeded:
        return ret
    
    try:
        j = json.loads(ret.response.text, object_pairs_hook=OrderedDict)
    except ValueError as e:
        logger.error("Failed to load pullreqeust results a json. Reason: '{}'.".format(e))
        return None

    if 'author' in kwargs:
        author = kwargs['author']
    else:
        author = c.username

    if 'limit' in kwargs:
        limit = kwargs['limit']
    else:
        # FIXME
        limit = 100

    results = []
    count = 0
    done = False
    while not done:
        for v in j['values']:
            if count < limit:
                if v['author']['username'] == author:
                    results.append(PullRequestSummary(v['created_on'], v['id'], v['links']['html']['href'], v['state']))
                    count += 1
            else:
                done = True
                break
        else:
            if 'next' in v:
                j = _next_page(v['next'], c)
                if not j:
                    done = True

    return results

def _query_github_pullrequest(**kwargs):
    c = creds.get('github')
    if not c:
        logger.error("Failed to get creds for github.")
        return None

    if 'author' in kwargs:
        author = kwargs['author']
    else:
        author = c.username

    # query issues only once (assuming git hub returns enough issues)
    ret = github_api.search_issues(kwargs['repository_owner'], kwargs['repository_name'], author, {'username': c.username, 'userpasswd': c.userpasswd})
    if not ret.succeeded:
        logger.error("Failed to search github issues. Reason: '{}'.".format(ret.message))
        return None
    
    try:
        j = json.loads(ret.response.text, object_pairs_hook=OrderedDict)
    except ValueError as e:
        logger.error("Failed to load github query result as json. Reason: '{}'.".format(e))
        return None

    results = []
    items = j['items']
    if 'limit' in kwargs:
        count = 0
        for o in items:
            if count < kwargs['limit']:
                results.append(PullRequestSummary(o['created_at'], o['number'], o['html_url'], o['state']))
                count += 1
            else:
                break
    else:
        for o in items:
            results.append(PullRequestSummary(o['created_at'], o['number'], o['html_url'], o['state']))
    return results

def query_pullrequest(**kwargs):
    """
    Return list of pull request summary.

    Mandatory
    ---------
    platform:               Resource platform name.
    repository_owner:       Repository owner.
    repository_name:        Repository name.

    OPTION
    ------
    author:                 Username of pull request submitter. Default author is obtained from  username in creds file.
    limit:                  Max number of pullrequest to query.
    """
    if kwargs['platform'] == 'bitbucket':
        return _query_bitbucket_pullrequest(**kwargs)
    elif kwargs['platform'] == 'github':
        return _query_github_pullrequest(**kwargs)
    else:
        logger.error("Unknown resource platform: '{}'.\n".format(resource_platform))
        return None 


'''
    Resoruce Configuration


    Resource configuration file format.

{
    "repository": {
        "platform": "bitbucket",
        "url": "https://bitbucket.org/inindca/i18n-automation.git",
        "owner": "inindca"
        "name": "i18n-automation",
        "branch": "master",
        "resources": [
            {
                "resource": {
                    "path": "test/src/flat.json",
                    "filetype": "json",
                    "language_code": "en-US"
                    "translations": [
                        {"ja": "test/src/flat_ja.json"}
                    ]
                }
            }, 
            {
                "resource": {
                    "path": "test/src/structured.json",
                    "filetype": "json",
                    "language_code": "en-US"
                    "translations": [
                        {"ja": "test/src/structured.json"}
                    ]
                }
            }
        ],
        "pullrequest": {
            "reviewers": ["kiyoshiiwase"],
            "title": "(TEST) Translation Updates"
        },
        "options": [
            "option_1",
            "option_2"
        ]
    }
}
'''

# ResourceConfigurationTranslation
#
# keys          values
# -----------------------------------
# language_code     Language code for the translation file. e.g. 'es-MX'
# path              Path to the translation file in repository. e.g. src/strings/en-MX/localizable.json
ResourceConfigurationTranslation = namedtuple('ResourceConfigurationTranslation', 'language_code, path')

# ResourceConfigurationResource
#
# keys          values
# -----------------------------------
# path          Path to a resouce file in repository. e.g. 'src/strings/en-US.json'
# filetype      File type string for the resource file. e.g. 'json'
# language_code     Language code for the resouce file. e.g. 'en-US'
# translations      List of Translation tuples for translation files.
ResourceConfigurationResource = namedtuple('ResourceConfigurationResoruce', 'path, filetype, language_code, translations')

# PullRequest for ResourceConfiguration 
# keys          values
# -----------------------------------
# title         One line text string for a pull request title.
# reviewers     List of reviewers.
ResourceConfigurationPullRequest = namedtuple('ResourceConfigurationPullRequest', 'title, reviewers')

# Option
#
# keys          values
# -----------------------------------
# name          Name of option. 
# value         Value of the option. 
ResourceConfigurationOption = namedtuple('ResourceConfigurationOption', 'name, value')

# Represents a Resource Configuration file.
#
# keys          values
# -----------------------------------
# filename                  Resource file name
# path                      Resource file path
# --- configuration file context ----
# repository_platform       Resource repository platform name (e.g. Bitbucket).
# repository_url            URL to the repository.
# repository_name           Resource repository name.
# repository_owner          Resource repository owner of the platform (e.g. inindca)
# repository_branch         Branch of the repository (e.g. master).
# resources                 List of Resource tuples
# pullrequest               A PullRequest tule
# options                   List of Option tuples.
ResourceConfiguration = namedtuple('ResourceConfiguration', 'filename, path, repository_platform, repository_url, repository_name, repository_owner, repository_branch, resources, pullrequest, options')

def _options_to_dict(o):
    results = []
    for x in o:
        results.append({x.name: x.value})
    return results

def _PullRequest_to_dict(o):
    return {'title': o.title, 'reviewers': o.reviewers}

def _translations_to_dict(o):
    results = []
    for x in o:
        results.append({x.language_code: x.path})
    return results

def _resources_to_dict(o):
    results = []
    for x in o:
        results.append({'path': x.path, 'filetype': x.filetype, 'language_code': x.language_code, 'translations': _translations_to_dict(x.translations)})
    return results

def _ResourceConfiguration_to_dict(o):
    return {
            'filename': o.filename,
            'path': o.path,
            'repository_platform': o.repository_platform,
            'repository_url': o.repository_url,
            'repository_name': o.repository_name,
            'repository_owner': o.repository_owner,
            'repository_branch': o.repository_branch,
            'resources': _resources_to_dict(o.resources),
            'pullrequest': _PullRequest_to_dict(o.pullrequest),
            'options': _options_to_dict(o.options)
            }

def get_configuration(**kwargs):
    """ 
    Return ResourceConfiguration for a resource configuration file (w/ 'filename' option),
    or list of available ResourceConfiguration.

    OPTION:
        'filename': To specify a specific resouce configuration filename.
    """

    if 'filename' in kwargs:
        return _read_configuration_file(os.path.join(settings.CONFIG_RESOURCE_DIR, kwargs['filename']))
    else:
        results = []
        for filename in os.listdir(settings.CONFIG_RESOURCE_DIR):
            if not os.path.splitext(filename)[1] == '.json':
                continue
            c = _read_configuration_file(os.path.join(settings.CONFIG_RESOURCE_DIR, filename))
            if c:
                results.append(c)
        return results

def _read_options(o):
    options = []
    # options are optional.
    if o:
        for x in o:
            for k, v in x.items():
                options.append(ResourceConfigurationOption(k, v))
    return options
    
def _read_pullrequest(o):
    reviewers = []
    # reviewers are optional.
    if o['reviewers']:
        for x in o['reviewers']:
            reviewers.append(x)
    return ResourceConfigurationPullRequest(o['title'], reviewers)

def _read_translations(o):
    results = []
    for x in o:
        for k,v in x.items():
            results.append(ResourceConfigurationTranslation(k, v))
    return results

def _read_resources(o):
    results = []
    for x in o:
        translations = _read_translations(x['resource']['translations'])
        results.append(ResourceConfigurationResource(x['resource']['path'], x['resource']['filetype'], x['resource']['language_code'], translations))
    return results

def _read_configuration_file(file_path):
    with open(file_path) as fi:
        try:
            j = json.load(fi)
        except ValueError as e:
            logger.error("Failed to load json. File: '{}', Reason: '{}'.".format(file_path, e))
            return None
        else:
            try: # catch all exceptions here, including one raised in subsquent functions.
                platform = j['repository']['platform']
                url = j['repository']['url']
                owner = j['repository']['owner']
                name = j['repository']['name']
                branch = j['repository']['branch']
                resources = _read_resources(j['repository']['resources'])
                pullrequest = _read_pullrequest(j['repository']['pullrequest'])
                options = _read_options(j['repository']['options'])
            except KeyError as e:
                logger.error("Failed to read json. File: '{}', Reason: '{}'.".format(file_path, e))
                return None
            else:
                return ResourceConfiguration(os.path.basename(file_path), file_path, platform, url, name, owner, branch, resources, pullrequest, options)
