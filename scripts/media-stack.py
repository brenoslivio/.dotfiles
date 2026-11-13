#!/usr/bin/env python3
"""Local media provisioning. Secrets are generated on the host, never in Nix."""
import argparse
import base64
import configparser
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

GIB = 1024**3


class APIError(RuntimeError):
    def __init__(self, status, location, fields):
        super().__init__(f'{location}: HTTP {status} {",".join(fields)}')
        self.status = status


def atomic(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.media-stack-')
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2) + '\n')


def usage_bytes(root):
    # Hardlinks share disk blocks. Do not follow symlinks or cross filesystems.
    root = Path(root)
    device = root.stat().st_dev
    seen, total = set(), 0
    def unreadable(error):
        raise error
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        dirs[:] = [d for d in dirs if not (Path(parent)/d).is_symlink()]
        for name in files:
            path = Path(parent)/name
            try:
                stat = path.lstat()
            except FileNotFoundError:
                continue
            if path.is_symlink():
                continue
            if stat.st_dev != device:
                raise RuntimeError('Media paths must share one filesystem.')
            identity = (stat.st_dev, stat.st_ino)
            if identity not in seen:
                seen.add(identity)
                # Logical size also reserves the budget for sparse/preallocated downloads.
                total += max(stat.st_size, stat.st_blocks * 512)
    return total


def space_ok(cfg):
    root = Path(cfg['root'])
    devices = {p.stat().st_dev for p in [root, root/'downloads', root/'library']}
    if len(devices) != 1:
        raise RuntimeError('Downloads and library must share the same filesystem.')
    budget = cfg['budgetGiB']
    within_budget = budget is None or usage_bytes(root) < budget*GIB
    return within_budget and shutil.disk_usage(root).free >= cfg['minFreeGiB']*GIB


def prepare(cfg):
    state = Path(cfg['stateDir'])
    path = state/'credentials.json'
    credentials = json.loads(path.read_text()) if path.exists() else {}
    for name in cfg['enabled']:
        if name == 'seerr':
            continue  # Seerr signs in with Jellyfin accounts, not a second password.
        initial = {'username': 'admin', 'password': secrets.token_urlsafe(24)}
        if name in ('radarr', 'sonarr', 'prowlarr', 'bazarr', 'lidarr'):
            initial['apiKey'] = secrets.token_hex(16)
        credentials.setdefault(name, initial)
    if 'jellyfin' in cfg['enabled']:
        viewers = credentials['jellyfin'].setdefault('viewers', {})
        for name in cfg['viewers']:
            viewers.setdefault(name, secrets.token_urlsafe(24))
    write_json(path, credentials)
    runtime = Path('/run/media-stack')
    runtime.mkdir(mode=0o700, exist_ok=True)
    for name in cfg['enabled']:
        if name in ('radarr', 'sonarr', 'prowlarr', 'lidarr'):
            atomic(runtime/f'{name}.env', f'{name.upper()}__AUTH__APIKEY={credentials[name]["apiKey"]}\n')
        if name == 'qbittorrent':
            write_json(state/'qbittorrent.json', credentials[name])
    if 'bazarr' in cfg['enabled']:
        atomic(state/'bazarr-apikey', credentials['bazarr']['apiKey'])
        # Bazarr stores its UI password as MD5; the random password remains private.
        atomic(state/'bazarr-password', hashlib.md5(credentials['bazarr']['password'].encode()).hexdigest())
        for name in ('radarr', 'sonarr'):
            if name in cfg['enabled']:
                atomic(state/f'{name}-apikey', credentials[name]['apiKey'])


def seed(cfg, service):
    if service == 'jellyfin':
        path = Path('/var/lib/jellyfin/config/network.xml')
        root = ET.parse(path).getroot() if path.exists() else ET.Element('NetworkConfiguration')
        values = {'InternalHttpPort': str(cfg['ports']['jellyfin']), 'EnableIPv4': 'true',
                  'EnableIPv6': 'false', 'EnableRemoteAccess': str(bool(cfg.get('jellyfinDomain'))).lower(), 'EnableUPnP': 'false',
                  'AutoDiscovery': 'false', 'EnableHttps': 'false', 'RequireHttps': 'false'}
        for key, value in values.items():
            element = root.find(key)
            if element is None:
                element = ET.SubElement(root, key)
            element.text = value
        old = root.find('LocalNetworkAddresses')
        if old is not None:
            root.remove(old)
        bind = '0.0.0.0' if cfg.get('jellyfinLanInterfaces') else '127.0.0.1'
        ET.SubElement(ET.SubElement(root, 'LocalNetworkAddresses'), 'string').text = bind
        old = root.find('KnownProxies')
        if old is not None:
            root.remove(old)
        proxies = ET.SubElement(root, 'KnownProxies')
        if cfg.get('jellyfinDomain'):
            ET.SubElement(proxies, 'string').text = '127.0.0.1'
        atomic(path, ET.tostring(root, encoding='unicode'))
    elif service == 'qbittorrent':
        path = Path('/var/lib/qBittorrent/qBittorrent/config/qBittorrent.conf')
        credentials = json.loads((Path(os.environ['CREDENTIALS_DIRECTORY'])/'qbittorrent').read_text())
        ini = configparser.ConfigParser(interpolation=None, strict=False)
        ini.optionxform = str
        if path.exists():
            ini.read(path)
        values = {
            'LegalNotice': {'Accepted': 'true'},
            'WebUI': {'Address': '127.0.0.1', 'Port': str(cfg['ports']['qbittorrent']),
                      'LocalHostAuth': 'true', 'AuthSubnetWhitelistEnabled': 'false',
                      'HostHeaderValidation': 'true', 'ServerDomains': 'localhost;127.0.0.1',
                      'CSRFProtection': 'true', 'UseUPnP': 'false', 'SecureCookie': 'false'},
            'BitTorrent': {'Session\\DefaultSavePath': cfg['root']+'/downloads',
                          'Session\\QueueingSystemEnabled': 'true', 'Session\\MaxActiveDownloads': '1',
                          'Session\\MaxActiveUploads': '1', 'Session\\MaxActiveTorrents': '2',
                          'Session\\LSDEnabled': 'false', 'Session\\GlobalDLSpeedLimit': str(cfg['downloadKiB']),
                          'Session\\GlobalUPSpeedLimit': str(cfg['uploadKiB'])},
            'Network': {'PortForwardingEnabled': 'false'},
        }
        for section, settings in values.items():
            if section not in ini:
                ini.add_section(section)
            for key, value in settings.items():
                ini[section][key] = value
        if not ini['WebUI'].get('Password_PBKDF2'):
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac('sha512', credentials['password'].encode(), salt, 100000)
            value = base64.b64encode(salt).decode()+':'+base64.b64encode(digest).decode()
            ini['WebUI']['Username'] = credentials['username']
            ini['WebUI']['Password_PBKDF2'] = f'"@ByteArray({value})"'
        import io
        stream = io.StringIO()
        ini.write(stream, space_around_delimiters=False)
        atomic(path, stream.getvalue())
    else:
        raise RuntimeError('Unknown service to seed.')


class API:
    def __init__(self, port, prefix='', headers=None):
        self.base = f'http://127.0.0.1:{port}'
        self.prefix = prefix
        self.headers = headers or {}
        self.timeout = 30
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, data=None, method=None, form=False):
        headers = {'Origin': self.base, 'Referer': self.base+'/', **self.headers}
        body = None
        if data is not None:
            body = (urllib.parse.urlencode(data, doseq=True) if form else json.dumps(data)).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        request = urllib.request.Request(self.base+self.prefix+path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = response.read()
        except urllib.error.HTTPError as error:
            # Response bodies can contain credentials. Never put them in the journal.
            locations = []
            try:
                locations = [str(x.get('path', '')) for x in json.loads(error.read()).get('errors', [])]
            except (ValueError, AttributeError, TypeError):
                pass
            raise APIError(error.code, self.base+self.prefix+path.split('?')[0], locations) from None
        if not result:
            return None
        try:
            return json.loads(result)
        except ValueError:
            return result.decode()

    def wait(self, path, ready=None, **kwargs):
        for _ in range(90):
            try:
                result = self.call(path, **kwargs)
                if ready is None or ready(result):
                    return result
            except (RuntimeError, urllib.error.URLError, TimeoutError):
                pass
            time.sleep(2)
        raise RuntimeError(f'{self.base} did not become ready.')


def fields(schema, values):
    result = json.loads(json.dumps(schema))
    for field in result.get('fields', []):
        if field['name'] in values:
            field['value'] = values[field['name']]
    return result


def put_named(api, endpoint, desired, include_id=True):
    existing = next((x for x in api.call(endpoint) if x.get('name') == desired['name']), None)
    if existing:
        if include_id:
            desired['id'] = existing['id']
        return api.call(f'{endpoint}/{existing["id"]}', desired, 'PUT')
    return api.call(endpoint, desired)


def indexers(api, selected, automatic_search=False):
    """Reconcile only our named sources; external availability must not block boot."""
    prefix = 'Media stack indexer: '
    existing = api.call('/indexer')
    if not selected and not any(x['name'].startswith(prefix) for x in existing):
        return
    profiles = api.call('/appprofile')
    previous = next((x for x in profiles if x['name'] == 'Media stack requests'), None)
    if previous is None:
        previous = next((x for x in profiles if x['name'] == 'Media stack interactive'), None)
    profile = {'name': 'Media stack requests', 'enableRss': automatic_search,
               'enableAutomaticSearch': automatic_search, 'enableInteractiveSearch': True,
               'minimumSeeders': 1}
    if previous:
        profile['id'] = previous['id']
        profile = api.call(f'/appprofile/{previous["id"]}', profile, 'PUT')
    else:
        profile = api.call('/appprofile', profile)
    schemas = api.call('/indexer/schema') if selected else []
    for source in selected:
        schema = next((x for x in schemas if x['implementation'].lower() == source or (x['implementation'] == 'Cardigann'
            and any(f['name'] == 'definitionFile' and f.get('value') == source
                    for f in x['fields']))), None)
        if schema is None:
            raise RuntimeError(f'Prowlarr definition unavailable: {source}')
        current = next((x for x in existing if x['name'] == prefix+source), None)
        desired = fields(current or schema, {})
        desired.update(name=prefix+source, appProfileId=profile['id'], enable=True)
        if current is None:
            # Creating disabled avoids an external connectivity test. Enabling with
            # forceSave still validates settings, but skips that network test.
            desired['enable'] = False
            desired = api.call('/indexer', desired)
            desired['enable'] = True
        api.call(f'/indexer/{desired["id"]}?forceSave=true', desired, 'PUT')
    for current in existing:
        if current['name'].startswith(prefix) and current['name'][len(prefix):] not in selected:
            current.update(enable=False, appProfileId=profile['id'])
            api.call(f'/indexer/{current["id"]}?forceSave=true', current, 'PUT')


def indexer_supports(source, target):
    category = {'radarr': 2000, 'sonarr': 5000, 'lidarr': 3000}[target]
    return any(category <= c['id'] < category+1000 for c in source['capabilities']['categories'])


def sync_indexers(cfg, credentials):
    """Verify effective ARR flags after Prowlarr's asynchronous create/update events."""
    if 'prowlarr' not in cfg['enabled']:
        return
    prowlarr = API(cfg['ports']['prowlarr'], '/api/v1', {'X-Api-Key': credentials['prowlarr']['apiKey']})
    sources = [x for x in prowlarr.call('/indexer') if x['name'].startswith('Media stack indexer: ')]
    if not sources:
        return
    targets = [(n, API(cfg['ports'][n], '/api/v1' if n == 'lidarr' else '/api/v3', {'X-Api-Key': credentials[n]['apiKey']}))
               for n in ('radarr', 'sonarr', 'lidarr') if n in cfg['enabled']]
    for _ in range(3):
        # Updating an existing source can sync its flags during an outage, but
        # creating it in an ARR app may fail that app's connectivity test.
        for source in sources:
            prowlarr.call(f'/indexer/{source["id"]}?forceSave=true', source, 'PUT')
        for _ in range(10):
            pending, missing = [], []
            for name, target in targets:
                rows = target.call('/indexer')
                for source in sources:
                    row = next((x for x in rows if x['name'] == source['name']+' (Prowlarr)'), None)
                    enabled = source['enable'] and indexer_supports(source, name)
                    if row is None:
                        if enabled:
                            missing.append(f'{name}: {source["name"]}')
                        continue
                    automatic = enabled and cfg.get('automaticSearch', False)
                    if (row['enableRss'] != automatic or row['enableAutomaticSearch'] != automatic
                            or row['enableInteractiveSearch'] != enabled):
                        flags = {k: row[k] for k in ('enableRss', 'enableAutomaticSearch', 'enableInteractiveSearch')}
                        pending.append(f'{target.base} {source["name"]}: {flags}')
            if not pending and not missing:
                return
            time.sleep(2)
    if pending:
        raise RuntimeError('Managed indexer flags did not sync: '+'; '.join(pending))
    # A missing source cannot download anything. Keep the local UI available;
    # do not relax checks on sources that exist with unsafe automatic flags.
    print('Warning: indexers not yet available in their apps: '+'; '.join(missing)+
          '. Retry app sync in Prowlarr after the sources recover.', file=sys.stderr)


def subtitle_import_settings(management):
    # Keep user-selected extra files while carrying bundled subtitles into the library.
    extensions = [x.strip() for x in (management.get('extraFileExtensions') or '').split(',') if x.strip()]
    existing = {x.lower().lstrip('.') for x in extensions}
    extensions.extend(x for x in ('srt', 'ass', 'ssa', 'vtt', 'sub', 'idx') if x not in existing)
    return dict(management, importExtraFiles=True, extraFileExtensions=','.join(extensions))


def arrange(cfg, credentials, name):
    api = API(cfg['ports'][name], '/api/v1' if name == 'prowlarr' else '/api/v3', {'X-Api-Key': credentials[name]['apiKey']})
    api.wait('/system/status')
    host = api.call('/config/host')
    # Set credentials only until our first successful setup. Subsequent UI changes survive.
    if not host.get('username'):
        host.update(username='admin', password=credentials[name]['password'], passwordConfirmation=credentials[name]['password'], authenticationMethod='forms', authenticationRequired='enabled')
        api.call('/config/host', host, 'PUT')
    if name == 'prowlarr':
        schemas = api.call('/applications/schema')
        for target in ('radarr', 'sonarr', 'lidarr'):
            if target not in cfg['enabled']:
                continue
            schema = next(x for x in schemas if x['implementation'].lower() == target)
            desired = fields(schema, {'baseUrl': f'http://127.0.0.1:{cfg["ports"][target]}',
                'prowlarrUrl': api.base, 'apiKey': credentials[target]['apiKey']})
            desired.update(name=f'Media stack {target}', syncLevel='fullSync')
            put_named(api, '/applications', desired)
        indexers(api, cfg.get('indexers', []), cfg.get('automaticSearch', False))
        if cfg.get('manualReleaseSelection'):
            for profile in api.call('/appprofile'):
                profile.update(enableRss=False, enableAutomaticSearch=False)
                api.call('/appprofile/'+str(profile['id']), profile, 'PUT')
        return None
    category = 'movies' if name == 'radarr' else 'tv'
    library = cfg['root']+'/library/'+category
    if not any(x['path'] == library for x in api.call('/rootfolder')):
        api.call('/rootfolder', {'path': library})
    management = subtitle_import_settings(api.call('/config/mediamanagement'))
    management.update(copyUsingHardlinks=True, minimumFreeSpaceWhenImporting=1024, setPermissionsLinux=False)
    api.call('/config/mediamanagement', management, 'PUT')
    downloads = api.call('/config/downloadclient')
    downloads['enableCompletedDownloadHandling'] = True
    if cfg.get('manualReleaseSelection'):
        downloads.update(autoRedownloadFailed=False, autoRedownloadFailedFromInteractiveSearch=False)
    api.call('/config/downloadclient', downloads, 'PUT')
    naming = api.call('/config/naming')
    naming['renameMovies' if name == 'radarr' else 'renameEpisodes'] = True
    api.call('/config/naming', naming, 'PUT')
    if 'qbittorrent' in cfg['enabled']:
        schema = next(x for x in api.call('/downloadclient/schema') if x['implementation'] == 'QBittorrent')
        desired = fields(schema, {'host': '127.0.0.1', 'port': cfg['ports']['qbittorrent'],
            'username': 'admin', 'password': credentials['qbittorrent']['password'],
            'movieCategory': category, 'tvCategory': category})
        desired.update(name='Media stack qBittorrent', enable=True, priority=1)
        put_named(api, '/downloadclient', desired)
    profiles = api.call('/qualityprofile')
    profile = next((x for x in profiles if x['name'] in ('Media stack requests', 'Media test 720p')), None)
    if profile is None:
        profile = profiles[0]
        profile.pop('id', None)
        profile.update(name='Media test 720p', upgradeAllowed=False)
        for item in profile['items']:
            item['allowed'] = '720p' in item.get('quality', {}).get('name', '').lower()
            for child in item.get('items', []):
                child['allowed'] = '720p' in child.get('quality', {}).get('name', '').lower()
            if item.get('items'):
                item['allowed'] = any(x['allowed'] for x in item['items'])
        first_allowed = next(x for x in profile['items'] if x['allowed'])
        profile['cutoff'] = first_allowed['id'] if first_allowed.get('items') else first_allowed['quality']['id']
        profile = api.call('/qualityprofile', profile)
    if cfg.get('allowAllQualities'):
        # Update in place: titles already assigned to any profile keep their IDs.
        def allow(items):
            for item in items:
                item['allowed'] = True
                allow(item.get('items', []))
        for quality in api.call('/qualityprofile'):
            allow(quality['items'])
            quality['upgradeAllowed'] = False
            if quality['id'] == profile['id']:
                quality['name'] = 'Media stack requests'
                profile = quality
            api.call('/qualityprofile/'+str(quality['id']), quality, 'PUT')
    # Reconcile existing installations too, not just newly created profiles.
    maximum = cfg.get('maxSizeMBPerMinute', 20)
    for quality in api.call('/qualitydefinition'):
        quality.update(minSize=0, preferredSize=12 if maximum is None else min(12, maximum), maxSize=maximum)
        api.call(f'/qualitydefinition/{quality["id"]}', quality, 'PUT')
    if cfg.get('manualReleaseSelection'):
        for quality in api.call('/qualityprofile'):
            quality['upgradeAllowed'] = False
            api.call('/qualityprofile/'+str(quality['id']), quality, 'PUT')
        for source in api.call('/indexer'):
            source.update(enableRss=False, enableAutomaticSearch=False)
            api.call('/indexer/'+str(source['id'])+'?forceSave=true', source, 'PUT')
    return profile


def music(cfg, credentials):
    """Provision album imports; every grab still requires a viewer's release selection."""
    api = API(cfg['ports']['lidarr'], '/api/v1', {'X-Api-Key': credentials['lidarr']['apiKey']})
    api.wait('/system/status')
    host = api.call('/config/host')
    if not host.get('username'):
        host.update(username='admin', password=credentials['lidarr']['password'],
                    passwordConfirmation=credentials['lidarr']['password'], authenticationMethod='forms', authenticationRequired='enabled')
        api.call('/config/host', host, 'PUT')
    profiles = api.call('/qualityprofile')
    quality = next((p for p in profiles if p['name'] == 'Media stack music'), None)
    quality = json.loads(json.dumps(quality or profiles[0]))
    if quality['name'] != 'Media stack music':
        quality.pop('id', None)
    quality.update(name='Media stack music', upgradeAllowed=False)
    def allow(items):
        for item in items:
            item['allowed'] = True
            allow(item.get('items', []))
    allow(quality['items'])
    quality = put_named(api, '/qualityprofile', quality)
    metadata = next((p for p in api.call('/metadataprofile') if p['name'] == 'Media stack music'), None)
    metadata = metadata or api.call('/metadataprofile')[0]
    if metadata['name'] != 'Media stack music':
        metadata.pop('id', None)
    metadata['name'] = 'Media stack music'
    for item in metadata['primaryAlbumTypes']:
        item['allowed'] = True
    metadata = put_named(api, '/metadataprofile', metadata)
    library = cfg['root']+'/library/music'
    root = next((r for r in api.call('/rootfolder') if r['path'] == library), {})
    root.update(name='Media stack music', path=library, defaultQualityProfileId=quality['id'],
                defaultMetadataProfileId=metadata['id'], defaultMonitorOption='none', defaultNewItemMonitorOption='none', defaultTags=[])
    api.call('/rootfolder'+('/'+str(root['id']) if root.get('id') else ''), root, 'PUT' if root.get('id') else 'POST')
    management = api.call('/config/mediamanagement')
    # Tags change file contents: copies protect the torrent's seeding data.
    management.update(copyUsingHardlinks=False, minimumFreeSpaceWhenImporting=1024,
                      setPermissionsLinux=False, enableMediaInfo=True, watchLibraryForChanges=True,
                      autoUnmonitorPreviouslyDownloadedTracks=True, downloadPropersAndRepacks='doNotUpgrade')
    api.call('/config/mediamanagement', management, 'PUT')
    tags = api.call('/config/metadataprovider')
    tags.update(writeAudioTags='newFiles', embedCoverArt=True, scrubAudioTags=False)
    api.call('/config/metadataprovider', tags, 'PUT')
    naming = api.call('/config/naming')
    naming.update(renameTracks=True, standardTrackFormat='{Album Title}/{track:00} - {Track Title}',
                  multiDiscTrackFormat='{Album Title}/{medium:00}-{track:00} - {Track Title}', artistFolderFormat='{Artist Name}')
    api.call('/config/naming', naming, 'PUT')
    downloads = api.call('/config/downloadclient')
    downloads.update(enableCompletedDownloadHandling=True, autoRedownloadFailed=False, autoRedownloadFailedFromInteractiveSearch=False)
    api.call('/config/downloadclient', downloads, 'PUT')
    schema = next(s for s in api.call('/downloadclient/schema') if s['implementation'] == 'QBittorrent')
    client = fields(schema, {'host': '127.0.0.1', 'port': cfg['ports']['qbittorrent'],
        'username': 'admin', 'password': credentials['qbittorrent']['password'], 'musicCategory': 'music'})
    client.update(name='Media stack qBittorrent', enable=True, priority=1)
    put_named(api, '/downloadclient', client)
    for source in api.call('/indexer'):
        source.update(enableRss=False, enableAutomaticSearch=False)
        api.call('/indexer/'+str(source['id'])+'?forceSave=true', source, 'PUT')


def jellyfin(cfg, credentials):
    remote_access = bool(cfg.get('jellyfinDomain'))
    api = API(cfg['ports']['jellyfin'], headers={'Authorization': 'MediaBrowser Client="Media stack", Device="localhost", DeviceId="media-stack", Version="1"'})
    # Jellyfin can return HTTP 200 with startup progress while migrations run.
    public = api.wait('/System/Info/Public', ready=lambda data: isinstance(data, dict) and 'StartupWizardCompleted' in data)
    creds = credentials['jellyfin']
    if not public['StartupWizardCompleted']:
        first = api.call('/Startup/User')
        if first.get('Name') not in (None, '', 'admin', 'jellyfin'):
            raise RuntimeError('An existing Jellyfin setup needs manual review; refusing to replace its administrator.')
        api.call('/Startup/Configuration', {'UICulture': 'en-US', 'MetadataCountryCode': 'US', 'PreferredMetadataLanguage': 'en'})
        try:
            api.call('/Startup/User', {'Name': 'admin', 'Password': creds['password']})
        except APIError as error:
            if error.status != 403:
                raise
            # A previous attempt may have set the password before completing the wizard.
            login = api.call('/Users/AuthenticateByName', {'Username': 'admin', 'Pw': creds['password']})
            api.headers['Authorization'] += ', Token="' + login['AccessToken'] + '"'
        api.call('/Startup/RemoteAccess', {'EnableRemoteAccess': remote_access, 'EnableAutomaticPortMapping': False})
        api.call('/Startup/Complete', {}, 'POST')
    login = api.call('/Users/AuthenticateByName', {'Username': 'admin', 'Pw': creds['password']})
    api.headers['Authorization'] = api.headers['Authorization'].split(', Token=')[0] + ', Token="' + login['AccessToken'] + '"'
    users = api.call('/Users')
    for name in cfg['viewers']:
        if not any(x['Name'] == name for x in users):
            user = api.call('/Users/New', {'Name': name, 'Password': creds['viewers'][name]})
            policy = user['Policy']
            policy.update(IsAdministrator=False, EnableContentDeletion=False, EnableRemoteAccess=remote_access)
            api.call('/Users/'+user['Id']+'/Policy', policy)
    # Reconcile migrated accounts too, preserving their other permissions.
    for user in users:
        if user['Name'] in ['admin', *cfg['viewers']]:
            policy = dict(user['Policy'])
            if policy.get('EnableRemoteAccess') != remote_access:
                policy['EnableRemoteAccess'] = remote_access
                api.call('/Users/'+user['Id']+'/Policy', policy)
    libraries = api.call('/Library/VirtualFolders')
    collections = [('Movies', 'movies', 'movies'), ('Series', 'tvshows', 'tv')]
    if 'lidarr' in cfg['enabled']:
        collections.append(('Music', 'music', 'music'))
    for name, kind, folder in collections:
        if not any(x['Name'] == name for x in libraries):
            query = urllib.parse.urlencode({'name': name, 'collectionType': kind, 'refreshLibrary': 'false'})
            api.call('/Library/VirtualFolders?'+query, {'LibraryOptions': {
                'PathInfos': [{'Path': cfg['root']+'/library/'+folder}], 'EnableRealtimeMonitor': True,
                'SaveLocalMetadata': False}})
    scan = next(x for x in api.call('/ScheduledTasks') if x['Key'] == 'RefreshLibrary')
    triggers = [x for x in scan['Triggers'] if x['Type'] != 'IntervalTrigger']
    triggers.append({'Type': 'IntervalTrigger', 'IntervalTicks': cfg.get('libraryScanMinutes', 2)*60*10_000_000})
    api.call(f'/ScheduledTasks/{scan["Id"]}/Triggers', triggers, 'POST')
    return api


def seerr(cfg, credentials, profiles):
    api = API(cfg['ports']['seerr'], '/api/v1')
    public = api.wait('/settings/public')
    body = {'username': 'admin', 'password': credentials['jellyfin']['password']}
    if not public['initialized']:
        # A retry may already have configured Jellyfin before initialization finished.
        path = Path('/var/lib/seerr/settings.json')
        configured = path.exists() and bool(json.loads(path.read_text()).get('jellyfin', {}).get('ip'))
        if not configured:
            body.update(hostname='127.0.0.1', port=cfg['ports']['jellyfin'], urlBase='', useSsl=False, serverType=2, email='admin@localhost.invalid')
    api.call('/auth/jellyfin', body)
    # Seerr REQUEST | REQUEST_ADVANCED: choose profiles without managing other requests.
    request_permissions = 32 | 8192
    main = dict(applicationTitle='Media test', applicationUrl=api.base, defaultPermissions=request_permissions, newPlexLogin=True,
                defaultQuotas={'movie': {'quotaLimit': 1, 'quotaDays': 7}, 'tv': {'quotaLimit': 1, 'quotaDays': 7}})
    api.call('/settings/main', main)
    for name, profile in profiles.items():
        endpoint = '/settings/'+name
        desired = {'name': 'Media stack '+name, 'hostname': '127.0.0.1', 'port': cfg['ports'][name],
            'apiKey': credentials[name]['apiKey'], 'useSsl': False, 'baseUrl': '', 'is4k': False,
            'activeProfileId': profile['id'], 'activeProfileName': profile['name'], 'isDefault': True,
            'activeDirectory': cfg['root']+'/library/'+('movies' if name == 'radarr' else 'tv'),
            'minimumAvailability': 'released', 'enableSeasonFolders': True, 'syncEnabled': True,
            'preventSearch': not cfg.get('automaticSearch', False)}
        put_named(api, endpoint, desired, include_id=False)
    api.call('/settings/initialize', {}, 'POST')
    # Import viewers by signing in once; only the first test viewer gets auto-approval.
    for index, name in enumerate(cfg['viewers']):
        viewer = API(cfg['ports']['seerr'], '/api/v1')
        user = viewer.call('/auth/jellyfin', {'username': name, 'password': credentials['jellyfin']['viewers'][name], 'email': name+'@localhost.invalid'})
        api.call(f'/user/{user["id"]}/settings/permissions', {'permissions': request_permissions | (128 if index == 0 else 0)}, 'POST')
    main['newPlexLogin'] = False
    api.call('/settings/main', main)
    if cfg.get('manualReleaseSelection'):
        atomic(Path(cfg['stateDir'])/'seerr-apikey', api.call('/settings/main')['apiKey'])
    return api


ENHANCED_ID = 'f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b'
INTRO_SKIPPER_ID = 'c83d86bb-a1e0-4c35-a113-e2101cf4ee6b'


def playback_polish(jelly):
    """Generate previews and intro segments off-hours, inside the existing media slice."""
    config = jelly.call('/System/Configuration')
    options = config.setdefault('TrickplayOptions', {})
    options.update(EnableHwAcceleration=False, EnableHwEncoding=False, ProcessThreads=1,
                   ScanBehavior='NonBlocking', ProcessPriority='BelowNormal',
                   Interval=10000, WidthResolutions=[160])
    jelly.call('/System/Configuration', config, 'POST')
    for library in jelly.call('/Library/VirtualFolders'):
        if library['Name'] not in ('Movies', 'Series'):
            continue
        options = library['LibraryOptions']
        options.update(EnableTrickplayImageExtraction=True,
                       ExtractTrickplayImagesDuringLibraryScan=False, SaveTrickplayWithMedia=False)
        options['DisabledMediaSegmentProviders'] = [p for p in options.get('DisabledMediaSegmentProviders', []) if p != 'Intro Skipper']
        jelly.call('/Library/VirtualFolders/LibraryOptions', {'Id': library['ItemId'], 'LibraryOptions': options}, 'POST')
    endpoint = f'/Plugins/{INTRO_SKIPPER_ID}/Configuration'
    options = jelly.call(endpoint)
    options.update(AutoDetectIntros=True, UpdateMediaSegments=True, ScanIntroduction=True,
                   ScanCredits=True, ScanRecap=False, ScanPreview=False, ScanCommercial=False,
                   MaxParallelism=1, ProcessThreads=1)
    jelly.call(endpoint, options, 'POST')
    tasks = {t['Key']: t for t in jelly.call('/ScheduledTasks')}
    for key, hour in [('IntroSkipperDetectSegmentsTask', 3), ('RefreshTrickplayImages', 4)]:
        task = tasks[key]
        jelly.call(f'/ScheduledTasks/{task["Id"]}/Triggers',
                   [{'Type': 'DailyTrigger', 'TimeOfDayTicks': hour*3600*10_000_000}], 'POST')


def enhanced(cfg, credentials, jelly, requests):
    """Keep integration secrets server-side, preserving unrelated plugin preferences."""
    endpoint = f'/Plugins/{ENHANCED_ID}/Configuration'
    settings = jelly.call(endpoint)
    settings.update(JellyseerrEnabled=True, JellyseerrUrls=requests.base,
                    JellyseerrApiKey=requests.call('/settings/main')['apiKey'],
                    JellyseerrShowSearchResults=True, JellyseerrAutoImportUsers=False,
                    JellyseerrShowAdvanced=True,
                    DownloadsPageEnabled=True, DownloadsUseNativeTab=True,
                    DownloadsUseCustomTabs=False, DownloadsUsePluginPages=False,
                    DownloadsFilterByUserRequests=True,
                    RecommendationsPageEnabled=not cfg.get('personalHome'), RecommendationsUseNativeTab=not cfg.get('personalHome'),
                    RecommendationsUseCustomTabs=False, RecommendationsUsePluginPages=False,
                    DisableScriptInjectionMiddleware=False)
    if cfg.get('manualReleaseSelection'):
        settings.update(AutoMovieRequestEnabled=False, AutoSeasonRequestEnabled=False,
                        SyncJellyfinWatchlistToSeerr=False, AddRequestedMediaToWatchlist=False)
    for name in ('radarr', 'sonarr'):
        if name in cfg['enabled']:
            settings[name.title()+'Url'] = f'http://127.0.0.1:{cfg["ports"][name]}'
            settings[name.title()+'ApiKey'] = credentials[name]['apiKey']
    jelly.call(endpoint, settings, 'POST')


def subtitle_profile(api, languages):
    """Reconcile our profile without removing profiles or languages created in the UI."""
    profiles = api.call('/system/languages/profiles')
    profile = next((p for p in profiles if p['name'] == 'Media stack subtitles'), None)
    if profile is None:
        profile = {'name': 'Media stack subtitles',
                   'profileId': max((p['profileId'] for p in profiles), default=0)+1,
                   'mustContain': [], 'mustNotContain': [], 'originalFormat': 0, 'tag': None}
        profiles.append(profile)
    # No cutoff: both languages are desired, rather than stopping at the first match.
    profile.update(cutoff=None, items=[{
        'id': index, 'language': language, 'hi': 'False', 'forced': 'False',
        'audio_exclude': 'False', 'audio_only_include': 'False',
    } for index, language in enumerate(languages, 1)])
    enabled = {x['code2'] for x in api.call('/system/languages') if x['enabled']}
    api.call('/system/settings', {
        'languages-enabled': sorted(enabled | set(languages)),
        'languages-profiles': json.dumps(profiles),
        'settings-general-movie_default_enabled': 'true',
        'settings-general-serie_default_enabled': 'true',
        'settings-general-movie_default_profile': str(profile['profileId']),
        'settings-general-serie_default_profile': str(profile['profileId']),
    }, form=True)
    return profile['profileId']


def bazarr(cfg, credentials):
    api = API(cfg['ports']['bazarr'], '/api', {'X-API-KEY': credentials['bazarr']['apiKey']})
    settings = api.wait('/system/settings')
    profile_id = subtitle_profile(api, cfg['subtitleLanguages'])
    # Seed account-free providers only on first setup; preserve subsequent UI choices.
    marker = Path(cfg['stateDir'])/'bazarr-configured'
    if not marker.exists():
        providers = settings['general']['enabled_providers'] or ['yifysubtitles', 'gestdown']
        api.call('/system/settings', {'settings-general-enabled_providers': providers}, form=True)
    for component, endpoint, key, task in [
        ('radarr', '/movies', 'radarrid', 'update_movies'),
        ('sonarr', '/series', 'seriesid', 'update_series'),
    ]:
        if component not in cfg['enabled']:
            continue
        # Existing files may have synced before the default profile was created.
        for row in api.call(endpoint+'?profileid=none')['data']:
            identity = row['radarrId' if component == 'radarr' else 'sonarrSeriesId']
            api.call(endpoint, {key: identity, 'profileid': profile_id}, form=True)
        api.call('/system/tasks', {'taskid': task}, form=True)
    atomic(marker, 'configured\n')


def setup(cfg):
    credentials = json.loads((Path(cfg['stateDir'])/'credentials.json').read_text())
    if 'qbittorrent' in cfg['enabled']:
        api = API(cfg['ports']['qbittorrent'], '/api/v2')
        api.wait('/auth/login', data={'username': 'admin', 'password': credentials['qbittorrent']['password']}, form=True)
        api.call('/app/version')  # Verify the session; 5.3 no longer returns "Ok.".
        categories = api.call('/torrents/categories')
        for category in ['movies', 'tv'] + (['music'] if 'lidarr' in cfg['enabled'] else []):
            endpoint = '/torrents/editCategory' if category in categories else '/torrents/createCategory'
            api.call(endpoint, {'category': category, 'savePath': cfg['root']+'/downloads/'+category}, form=True)
        api.call('/app/setPreferences', {'json': json.dumps({'max_ratio_enabled': True, 'max_ratio': 1,
            'max_seeding_time_enabled': True, 'max_seeding_time': 60, 'max_ratio_act': 0})}, form=True)
    profiles = {}
    if 'lidarr' in cfg['enabled']:
        music(cfg, credentials)
    for name in ('radarr', 'sonarr', 'prowlarr'):
        if name in cfg['enabled']:
            profile = arrange(cfg, credentials, name)
            if profile:
                profiles[name] = profile
    if 'jellyfin' in cfg['enabled']:
        jelly = jellyfin(cfg, credentials)
        if cfg.get('playbackPolish'):
            playback_polish(jelly)
        jelly.call('/Library/Refresh', {}, 'POST')
        if 'seerr' in cfg['enabled']:
            requests = seerr(cfg, credentials, profiles)
            if cfg.get('jellyfinEnhanced', False):
                enhanced(cfg, credentials, jelly, requests)
    if 'bazarr' in cfg['enabled']:
        bazarr(cfg, credentials)
    sync_indexers(cfg, credentials)
    write_json(Path(cfg['stateDir'])/'setup-complete.json', {'ports': cfg['ports'], 'root': cfg['root']})
    mode = 'Automatic searches and RSS monitoring enabled for monitored titles.' if cfg.get('automaticSearch', False) else 'Managed indexers use interactive searches only.'
    print('Media services connected. '+mode+' Completed downloads import automatically.')


def backup(cfg):
    """Quiesce databases; retain credentials and state, but never copy the media library."""
    directory = Path('/var/backups/media-stack')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + '.tar.gz')
    partial = destination.with_suffix('.partial')
    paths = {'jellyfin': '/var/lib/jellyfin', 'seerr': '/var/lib/seerr',
             'radarr': '/var/lib/radarr', 'sonarr': '/var/lib/sonarr',
             'prowlarr': '/var/lib/prowlarr', 'qbittorrent': '/var/lib/qBittorrent',
             'bazarr': '/var/lib/bazarr', 'lidarr': '/var/lib/lidarr'}
    services = cfg['enabled'] + ['media-stack-setup'] + (['media-releases'] if cfg.get('manualReleaseSelection') else [])
    if cfg.get('jellyfinDomain'):
        services.append('caddy')
    active = [name for name in services if subprocess.run(
        ['systemctl', 'is-active', '--quiet', name]).returncode == 0]
    try:
        if active:
            subprocess.run(['systemctl', 'stop', *active], check=True)
        with partial.open('xb') as stream:
            os.chmod(partial, 0o600)
            with tarfile.open(fileobj=stream, mode='w:gz', dereference=True) as archive:
                for path in [cfg['stateDir'], '/etc/media-stack.json', *[paths[n] for n in cfg['enabled']]]:
                    if Path(path).exists():
                        archive.add(path, arcname=path.lstrip('/'))
        os.replace(partial, destination)
        print(f'Private state backup: {destination} (media files excluded)')
    finally:
        if active:
            subprocess.run(['systemctl', 'start', *active], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='/etc/media-stack.json')
    parser.add_argument('command', choices=['prepare', 'seed', 'setup', 'credentials', 'status', 'check-space', 'guard', 'resume', 'backup'])
    parser.add_argument('service', nargs='?')
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    if args.command not in ('seed', 'check-space', 'status') and os.geteuid() != 0:
        raise RuntimeError('Run this command with sudo.')
    if args.command == 'prepare':
        prepare(cfg)
    elif args.command == 'seed':
        seed(cfg, args.service)
    elif args.command == 'setup':
        setup(cfg)
    elif args.command == 'backup':
        backup(cfg)
    elif args.command == 'credentials':
        print((Path(cfg['stateDir'])/'credentials.json').read_text())
    elif args.command == 'status':
        for name in cfg['enabled']:
            status = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
            print(f'{name:12} {status.stdout.strip():10} http://localhost:{cfg["ports"][name]}')
        status = subprocess.run(['systemctl', 'is-active', 'media-stack-setup'], capture_output=True, text=True)
        print(f'Setup: {status.stdout.strip()} (journalctl -u media-stack-setup for details)')
        budget = 'unlimited' if cfg['budgetGiB'] is None else f'{cfg["budgetGiB"]} GiB'
        print(f'Media: {cfg["root"]}; soft budget: {budget}; free-space reserve: {cfg["minFreeGiB"]} GiB')
    elif args.command in ('check-space', 'guard', 'resume'):
        if not space_ok(cfg):
            if args.command == 'guard':
                subprocess.run(['systemctl', 'stop', 'qbittorrent.service'], check=True)
                print('Downloads stopped: media budget or free-space reserve reached. Resume explicitly after freeing space.')
                return
            raise RuntimeError('Download budget or free-space reserve reached. Free space, then sudo media-stack resume.')
        if args.command == 'resume':
            subprocess.run(['systemctl', 'start', 'qbittorrent.service'], check=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, StopIteration) as error:
        print(f'Media stack: {error}', file=sys.stderr)
        sys.exit(1)
