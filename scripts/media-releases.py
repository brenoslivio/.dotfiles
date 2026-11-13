#!/usr/bin/env python3
"""Private release broker. Browser choices are opaque, user-bound, and single-use."""
import importlib.util
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode


def disk_usage(root):
    stats = os.statvfs(root)
    total = stats.f_blocks * stats.f_frsize
    used = (stats.f_blocks - stats.f_bfree) * stats.f_frsize
    available = stats.f_bavail * stats.f_frsize
    if total <= 0:
        raise ValueError('Filesystem capacity is unavailable')
    return {'totalBytes': total, 'usedBytes': used, 'availableBytes': available,
            'usedPercent': round(100 * used / total, 1)}

spec = importlib.util.spec_from_file_location('media', Path(__file__).with_name('media-stack.py'))
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)
personal_spec = importlib.util.spec_from_file_location('personal', Path(__file__).with_name('media-personal.py'))
personal_module = importlib.util.module_from_spec(personal_spec)
personal_spec.loader.exec_module(personal_module)
removal_spec = importlib.util.spec_from_file_location('removal', Path(__file__).with_name('media-removal.py'))
removal_module = importlib.util.module_from_spec(removal_spec)
removal_spec.loader.exec_module(removal_module)
activity_spec = importlib.util.spec_from_file_location('activity', Path(__file__).with_name('media-activity.py'))
activity_module = importlib.util.module_from_spec(activity_spec)
activity_spec.loader.exec_module(activity_module)
music_spec = importlib.util.spec_from_file_location('music', Path(__file__).with_name('media-music.py'))
music_module = importlib.util.module_from_spec(music_spec)
music_spec.loader.exec_module(music_module)


class Problem(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def positive(value):
    if type(value) is not int or value < 1:
        raise Problem('Invalid identifier.', 400)
    return value


def fingerprint(row):
    return [row.get('guid'), row.get('indexerId'), row.get('title'), row.get('size'), row.get('infoHash')]


def rejection(row, context):
    reasons = list(row.get('rejections') or [])
    if str(row.get('protocol')).lower() not in ('torrent', '2'):
        reasons.append('Only torrents are supported.')
    if not row.get('guid') or not row.get('indexerId') or not row.get('size'):
        reasons.append('Incomplete release information.')
    if context['mediaType'] == 'tv':
        if row.get('seasonNumber') != context['season']:
            reasons.append('Wrong season.')
        if context.get('episode') is None:
            if not row.get('fullSeason'):
                reasons.append('Choose a full season pack, or select an episode above.')
        elif row.get('fullSeason') or row.get('episodeNumbers') != [context['episode']]:
            reasons.append('This release does not contain exactly the selected episode.')
    return reasons


class Broker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.db = sqlite3.connect(Path(cfg['stateDir'])/'releases.sqlite', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS choices (id TEXT PRIMARY KEY, owner INTEGER, created REAL, state TEXT, data TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS subtitle_choices (id TEXT PRIMARY KEY, owner INTEGER, created REAL, state TEXT, data TEXT)')
        self.db.execute("UPDATE subtitle_choices SET state='uncertain' WHERE state='submitting'")
        # A crash during a mutation has an unknown outcome. Never repeat that mutation.
        self.db.execute("UPDATE choices SET state='uncertain' WHERE state IN ('requesting','submitting')")
        self.db.commit()
        self.removal = removal_module.Removal(self, media, Problem)
        self.activity = activity_module.Activity(self, media, Problem)
        self.music = music_module.Music(self, media, Problem, personal_module.restricted, activity_module.torrent_hash)

    def creds(self):
        return json.loads((Path(self.cfg['stateDir'])/'credentials.json').read_text())

    def seerr(self, user=None):
        key = (Path(self.cfg['stateDir'])/'seerr-apikey').read_text().strip()
        headers = {'X-Api-Key': key}
        if user is not None:
            headers['X-Api-User'] = str(user)
        return media.API(self.cfg['ports']['seerr'], '/api/v1', headers)

    def arr(self, kind):
        name = 'radarr' if kind == 'movie' else 'sonarr'
        api = media.API(self.cfg['ports'][name], '/api/v3', {'X-Api-Key': self.creds()[name]['apiKey']})
        api.timeout = 180  # Interactive indexer searches can take longer than ordinary API calls.
        return api

    def bazarr(self):
        if 'bazarr' not in self.cfg.get('enabled', []):
            raise Problem('Subtitle search needs Bazarr enabled.')
        api = media.API(self.cfg['ports']['bazarr'], '/api', {'X-API-KEY': self.creds()['bazarr']['apiKey']})
        api.timeout = 180
        return api

    def subtitle_item(self, user, headers, item_id):
        try:
            item_id = uuid.UUID(str(item_id)).hex
            uid = uuid.UUID(user['jellyfinUserId']).hex
        except (ValueError, KeyError, TypeError):
            raise Problem('Open a movie or episode in your Jellyfin library.', 400) from None
        api = media.API(self.cfg['ports']['jellyfin'], headers={
            k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        try:
            visible = api.call('/Items?'+urlencode({'userId': uid, 'ids': item_id, 'recursive': 'true', 'fields': 'Path'}))['Items']
        except media.APIError:
            raise Problem('You cannot access this library item.', 403) from None
        if not visible:
            raise Problem('You cannot access this library item.', 403)
        item = visible[0]
        if item.get('Type') not in ('Movie', 'Episode') or not item.get('Path'):
            raise Problem('Open an imported movie or an individual episode.')
        path = Path(item['Path']).resolve()
        if not path.is_relative_to((Path(self.cfg['root'])/'library').resolve()) or not path.is_file():
            raise Problem('This file is outside the managed media library.', 403)
        stat = path.stat()
        return {'itemId': item_id, 'path': str(path), 'size': stat.st_size,
                'modified': stat.st_mtime_ns, 'type': item['Type'], 'title': item['Name']}

    def subtitle_target(self, item):
        api = self.bazarr()
        path = Path(item['path'])
        if item['type'] == 'Movie':
            start = 0
            while True:
                rows = api.call('/movies?'+urlencode({'start': start, 'length': 100}))['data']
                for row in rows:
                    if row.get('path') and Path(row['path']).resolve() == path:
                        return '/providers/movies', {'radarrid': row['radarrId']}
                if len(rows) < 100:
                    break
                start += 100
        else:
            for series in self.arr('tv').call('/series'):
                if not series.get('path') or not path.is_relative_to(Path(series['path']).resolve()):
                    continue
                rows = api.call('/episodes?'+urlencode({'seriesid[]': series['id']}))['data']
                for row in rows:
                    if row.get('path') and Path(row['path']).resolve() == path:
                        return '/providers/episodes', {'episodeid': row['sonarrEpisodeId'], 'seriesid': row['sonarrSeriesId']}
        raise Problem('Bazarr has not indexed this file yet. Wait for its library sync, then search again.')

    def subtitle_search(self, user, headers, body):
        item = self.subtitle_item(user, headers, body.get('itemId'))
        endpoint, target = self.subtitle_target(item)
        rows = self.bazarr().call(endpoint+'?'+urlencode(target))['data']
        self.db.execute('DELETE FROM subtitle_choices WHERE created < ?', (time.time()-900,))
        results = []
        languages = {'pt-br': 'pb', 'pob': 'pb', 'pb': 'pb', 'en': 'en', 'eng': 'en'}
        for row in rows[:250]:
            language = languages.get(str(row.get('language', '')).lower().replace('_', '-'))
            if language not in self.cfg.get('subtitleLanguages', ['pb', 'en']) or not row.get('subtitle'):
                continue
            token = secrets.token_urlsafe(24)
            data = {'item': item, 'endpoint': endpoint, 'target': target, 'subtitle': row}
            self.db.execute('INSERT INTO subtitle_choices VALUES (?,?,?,?,?)',
                            (token, user['id'], time.time(), 'preview', json.dumps(data)))
            results.append({'id': token, 'language': language, 'provider': row['provider'],
                            'score': row.get('score', 0), 'release': ', '.join(row.get('release_info') or []),
                            'hearingImpaired': str(row.get('hearing_impaired')).lower() == 'true',
                            'forced': str(row.get('forced')).lower() == 'true', 'missing': row.get('dont_matches') or []})
        self.db.commit()
        warnings = []
        try:
            providers = self.bazarr().call('/providers')['data']
            if not providers:
                warnings.append('No subtitle providers are enabled. Configure them in Bazarr → Settings → Providers.')
            for provider in providers:
                name = str(provider.get('name', ''))
                if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', name):
                    continue
                status = provider.get('status')
                if status == 'Good':
                    continue
                if status in ('AuthenticationError', 'ConfigurationError'):
                    reason = 'check its account settings in Bazarr'
                elif status in ('DownloadLimitExceeded', 'TooManyRequests'):
                    reason = 'download or request limit reached; try later'
                else:
                    reason = 'temporarily unavailable; check Bazarr provider status'
                warnings.append(f'{name}: {reason}.')
        except Exception:
            warnings.append('Provider health could not be checked. Results may be incomplete.')
        return {'title': item['title'], 'subtitles': sorted(results, key=lambda row: row['score'], reverse=True), 'warnings': warnings}

    def subtitle_download(self, user, headers, token):
        row = self.db.execute('SELECT owner,created,state,data FROM subtitle_choices WHERE id=?', (token,)).fetchone()
        if not row or row[0] != user['id']:
            raise Problem('Subtitle selection not found.', 404)
        if time.time()-row[1] > 900:
            raise Problem('Subtitle search expired. Search again.')
        if row[2] != 'preview':
            raise Problem('This subtitle was already submitted. Check the library or Bazarr activity before trying again.')
        data = json.loads(row[3])
        current = self.subtitle_item(user, headers, data['item']['itemId'])
        if current != data['item'] or self.subtitle_target(current) != (data['endpoint'], data['target']):
            raise Problem('The media file changed. Search again.')
        subtitle = data['subtitle']
        data['before'] = self.subtitle_files(current, subtitle['language'])
        payload = {**data['target'], 'subtitle': subtitle['subtitle'], 'provider': subtitle['provider'],
                   'hi': subtitle['hearing_impaired'], 'forced': subtitle['forced'],
                   'original_format': subtitle['original_format']}
        self.db.execute("UPDATE subtitle_choices SET state='submitting',data=? WHERE id=?", (json.dumps(data), token))
        self.db.commit()
        try:
            self.bazarr().call(data['endpoint'], payload, form=True)
        except Exception:
            self.db.execute("UPDATE subtitle_choices SET state='uncertain' WHERE id=?", (token,))
            self.db.commit()
            raise Problem('Subtitle submission could not be confirmed. Check Bazarr activity; it will not be retried automatically.') from None
        self.db.execute("UPDATE subtitle_choices SET state='queued' WHERE id=?", (token,))
        self.db.commit()
        return {'state': 'queued', 'message': 'Subtitle download queued in Bazarr. Once it finishes and Jellyfin refreshes the library, reopen playback and select the track in the subtitle menu.'}

    def subtitle_files(self, item, language):
        video = Path(item['path'])
        code = str(language).lower().replace('_', '-')
        codes = ('en', 'eng') if code in ('en', 'eng') else ('pt-br', 'pob', 'pb') if code in ('pt-br', 'pob', 'pb') else ()
        result = {}
        for path in video.parent.iterdir():
            suffix = path.name[len(video.stem):].lower() if path.name.startswith(video.stem+'.') else ''
            if path.is_symlink() or not any(re.fullmatch(r'\.'+re.escape(c)+r'(?:\.(?:hi|sdh|forced))*\.(?:srt|ass|ssa|vtt|sub|idx)', suffix) for c in codes):
                continue
            stat = path.stat()
            if path.is_file() and stat.st_size:
                result[str(path)] = [stat.st_size, stat.st_mtime_ns]
        return result

    def refresh_subtitle_item(self, item_id):
        api = self.media_jellyfin_admin()
        api.call('/Items/'+item_id+'/Refresh?Recursive=false&MetadataRefreshMode=Default&ImageRefreshMode=None&ReplaceAllMetadata=false&ReplaceAllImages=false', method='POST')

    def media_jellyfin_admin(self):
        api = media.API(self.cfg['ports']['jellyfin'], headers={
            'Authorization': 'MediaBrowser Client="Subtitle refresh", Device="Server", DeviceId="subtitle-refresh", Version="1"'})
        login = api.call('/Users/AuthenticateByName', {'Username': 'admin', 'Pw': self.creds()['jellyfin']['password']})
        api.headers['Authorization'] += ', Token="'+login['AccessToken']+'"'
        return api

    def subtitle_status(self, user, headers, token):
        row = self.db.execute('SELECT owner,state,data FROM subtitle_choices WHERE id=?', (token,)).fetchone()
        if not row or row[0] != user['id']:
            raise Problem('Subtitle selection not found.', 404)
        data = json.loads(row[2])
        item = self.subtitle_item(user, headers, data['item']['itemId'])
        if item != data['item']:
            raise Problem('The media file changed. Reopen subtitle search.')
        if row[1] == 'uncertain':
            return {'state': 'uncertain', 'message': 'Submission is unconfirmed. Check Bazarr activity before trying again.'}
        if row[1] not in ('queued', 'ready'):
            raise Problem('Subtitle has not been queued.')
        files = self.subtitle_files(item, data['subtitle']['language'])
        changed = [path for path, stat in files.items() if data.get('before', {}).get(path) != stat]
        if not changed:
            return {'state': 'queued', 'message': 'Waiting for Bazarr to finish downloading the subtitle.'}
        if not data.get('refreshRequested'):
            self.refresh_subtitle_item(item['itemId'])
            data['refreshRequested'] = True
            self.db.execute('UPDATE subtitle_choices SET data=? WHERE id=?', (json.dumps(data), token))
            self.db.commit()
        api = media.API(self.cfg['ports']['jellyfin'], headers={k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        items = api.call('/Items?'+urlencode({'userId': user['jellyfinUserId'], 'ids': item['itemId'], 'fields': 'MediaStreams'}))['Items']
        streams = items[0].get('MediaStreams', []) if items else []
        if any(s.get('Type') == 'Subtitle' and s.get('IsExternal') and s.get('Path') in changed for s in streams):
            self.db.execute("UPDATE subtitle_choices SET state='ready' WHERE id=?", (token,))
            self.db.commit()
            return {'state': 'ready', 'message': 'Subtitle is available in Jellyfin. Reopen playback and select it in the subtitle menu.'}
        return {'state': 'downloaded', 'message': 'Subtitle downloaded; waiting for Jellyfin to index the track.'}

    def identity(self, headers):
        auth = {k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)}
        if not auth:
            raise Problem('Sign in to Jellyfin.', 401)
        try:
            user = media.API(self.cfg['ports']['jellyfin'], headers=auth).call('/Users/Me')
        except media.APIError:
            raise Problem('Sign in to Jellyfin again.', 401) from None
        if user.get('Policy', {}).get('IsDisabled'):
            raise Problem('Account disabled.', 403)
        uid = user['Id'].replace('-', '').lower()
        # Never trust a caller-supplied user id; match the authenticated Jellyfin identity.
        offset = 0
        while True:
            rows = self.seerr().call(f'/user?take=100&skip={offset}')['results']
            for row in rows:
                if str(row.get('jellyfinUserId', '')).replace('-', '').lower() == uid:
                    return row
            if len(rows) < 100:
                break
            offset += 100
        raise Problem('Your Jellyfin account is not linked to Seerr.', 403)

    def permitted(self, user, kind):
        permissions = user.get('permissions', 0)
        flag = 262144 if kind == 'movie' else 524288
        if not permissions & (2 | 32 | flag):
            raise Problem('Your account cannot request this media.', 403)

    def guard(self):
        # Fail closed if any automation was enabled outside provisioning.
        for name in ('radarr', 'sonarr'):
            api = self.arr('movie' if name == 'radarr' else 'tv')
            if any(r.get('enableRss') or r.get('enableAutomaticSearch') for r in api.call('/indexer')):
                raise Problem('Automatic indexer downloads must be disabled. Run media-stack setup.')
            downloads = api.call('/config/downloadclient')
            if downloads.get('autoRedownloadFailed') or downloads.get('autoRedownloadFailedFromInteractiveSearch'):
                raise Problem('Automatic failed-download retries must be disabled.')
            if any(p.get('upgradeAllowed') for p in api.call('/qualityprofile')):
                raise Problem('Automatic quality upgrades must be disabled.')
            servers = self.seerr().call('/settings/'+name)
            if any(not s.get('preventSearch') for s in servers):
                raise Problem('Automatic Seerr searches must be disabled.')

    def context(self, user, body):
        kind = body.get('mediaType')
        if kind not in ('movie', 'tv') or body.get('is4k'):
            raise Problem('Choose a movie or series in the standard library.', 400)
        self.permitted(user, kind)
        tmdb = positive(body.get('mediaId'))
        if self.removal.blocked(kind, tmdb):
            raise Problem('An administrator is removing this title. Finish removal before requesting again.')
        api = self.arr(kind)
        name = 'radarr' if kind == 'movie' else 'sonarr'
        servers = self.seerr().call('/settings/'+name)
        server = next((s for s in servers if s.get('isDefault') and not s.get('is4k')), None)
        if not server:
            raise Problem('No default media server configured.')
        profile = body.get('profileId', server['activeProfileId'])
        if not user.get('permissions', 0) & (2 | 16 | 8192):
            profile = server['activeProfileId']
        if profile not in [p['id'] for p in api.call('/qualityprofile')]:
            raise Problem('Unknown quality profile.', 400)
        details = self.seerr(user['id']).call(f'/{kind}/{tmdb}')
        external = tmdb if kind == 'movie' else details.get('externalIds', {}).get('tvdbId')
        if not external:
            raise Problem('This series has no TVDB match. Match it in Sonarr first.')
        field = 'tmdbId' if kind == 'movie' else 'tvdbId'
        endpoint = '/movie' if kind == 'movie' else '/series'
        rows = api.call(endpoint)
        item = next((r for r in rows if r.get(field) == external), None)
        if item is None:
            lookup = api.call(endpoint+'/lookup?'+urlencode({'term': ('tmdb:' if kind == 'movie' else 'tvdb:')+str(external)}))
            item = next((r for r in lookup if r.get(field) == external), None)
            if not item:
                raise Problem('Title was not found by the library manager.')
            item = dict(item)
            item.pop('id', None)
            item.update(monitored=False, qualityProfileId=profile, rootFolderPath=server['activeDirectory'])
            item['addOptions'] = {'monitor': 'none', 'searchForMovie': False,
                                  'searchForMissingEpisodes': False, 'searchForCutoffUnmetEpisodes': False}
            if kind == 'tv':
                item['seasonFolder'] = True
                for season in item.get('seasons', []):
                    season['monitored'] = False
            item = api.call(endpoint, item)
        # Browsing never changes an existing title's profile or monitoring.
        context = {'mediaType': kind, 'mediaId': tmdb, 'arrId': item['id'], 'profileId': item['qualityProfileId'],
                   'serverId': server['id'], 'rootFolder': server['activeDirectory'],
                   'title': item['title'], 'tvdbId': external if kind == 'tv' else None}
        if kind == 'tv':
            seasons = [s['seasonNumber'] for s in item.get('seasons', [])]
            season = body.get('season')
            if type(season) is not int or season not in seasons:
                raise Problem('Select one season.', 400)
            context['season'] = season
            episodes = api.call('/episode?'+urlencode({'seriesId': item['id']}))
            choices = [{'number': e['episodeNumber'], 'title': e['title'], 'id': e['id']}
                       for e in episodes if e['seasonNumber'] == season]
            context['episodes'] = choices
            episode = body.get('episode')
            if episode is not None:
                match = next((e for e in choices if e['number'] == episode), None)
                if not match:
                    raise Problem('Episode metadata is not ready. Try searching again.', 400)
                context.update(episode=episode, episodeId=match['id'])
        return context

    def episodes(self, user, body):
        """Read catalogue/availability without adding a series or searching indexers."""
        self.permitted(user, 'tv')
        tmdb = positive(body.get('mediaId'))
        season = body.get('season')
        if type(season) is not int or season < 0:
            raise Problem('Select one season.', 400)
        details = self.seerr(user['id']).call(f'/tv/{tmdb}')
        if season not in [s['seasonNumber'] for s in details.get('seasons', [])]:
            raise Problem('Unknown season.', 400)
        metadata = self.seerr(user['id']).call(f'/tv/{tmdb}/season/{season}')
        tvdb = details.get('externalIds', {}).get('tvdbId')
        series = next((s for s in self.arr('tv').call('/series') if tvdb and s.get('tvdbId') == tvdb), None)
        local = self.arr('tv').call('/episode?'+urlencode({'seriesId': series['id']})) if series else []
        available = {e['episodeNumber'] for e in local if e['seasonNumber'] == season and e.get('hasFile')}
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        return {'title': details.get('name') or details.get('title'), 'season': season, 'episodes': [
            {'number': e['episodeNumber'], 'title': e.get('name') or e.get('title') or 'Untitled',
             'airDate': e.get('airDate'), 'aired': bool(e.get('airDate') and e['airDate'][:10] <= today),
             'available': e['episodeNumber'] in available}
            for e in metadata.get('episodes', [])]}

    def releases(self, context):
        if context['mediaType'] == 'movie':
            query = {'movieId': context['arrId']}
        elif context.get('episodeId'):
            query = {'episodeId': context['episodeId']}
        else:
            query = {'seriesId': context['arrId'], 'seasonNumber': context['season']}
        return self.arr(context['mediaType']).call('/release?'+urlencode(query))

    def save(self, token, owner, state, data, created=None):
        self.db.execute('INSERT OR REPLACE INTO choices VALUES (?,?,?,?,?)',
                        (token, owner, created or time.time(), state, json.dumps(data)))
        self.db.commit()

    def get(self, token, user):
        row = self.db.execute('SELECT owner,created,state,data FROM choices WHERE id=?', (token,)).fetchone()
        if not row or row[0] != user['id']:
            raise Problem('Selection not found.', 404)
        return row[1], row[2], json.loads(row[3])

    def search(self, user, body):
        self.guard()
        replacement = body.get('replacementOf')
        if replacement is not None and (not isinstance(replacement, str) or len(replacement) > 100):
            raise Problem('Invalid replacement selection.', 400)
        ctx = self.context(user, body)
        if replacement:
            _, state, previous = self.get(replacement, user)
            if state != 'submitted' or not self.activity.same_scope(previous['context'], ctx):
                raise Problem('Choose a replacement for the same movie, episode, or full season.')
        rows = self.releases(ctx)
        result = []
        self.db.execute("DELETE FROM choices WHERE state='preview' AND created < ?", (time.time()-900,))
        for row in rows[:250]:
            token = secrets.token_urlsafe(24)
            data = {'context': ctx, 'release': row}
            if replacement:
                data['replaces'] = replacement
            self.save(token, user['id'], 'preview', data)
            result.append({'id': token, 'title': row.get('title'), 'size': row.get('size'),
                           'seeders': row.get('seeders'), 'indexer': row.get('indexer'),
                           'quality': row.get('quality', {}).get('quality', {}).get('name'),
                           'rejections': rejection(row, ctx)})
        return {'title': ctx['title'], 'profileId': ctx['profileId'], 'episodes': ctx.get('episodes', []), 'releases': result}

    def select(self, user, token):
        created, state, data = self.get(token, user)
        if state != 'preview':
            return {'state': state, 'message': data.get('message', '')}
        if time.time()-created > 900:
            raise Problem('Search results expired. Search again.')
        ctx, release = data['context'], data['release']
        if self.removal.blocked(ctx['mediaType'], ctx['mediaId']):
            raise Problem('An administrator is removing this title.')
        self.permitted(user, ctx['mediaType'])
        if rejection(release, ctx):
            raise Problem('This release does not meet the library rules.')
        self.guard()
        if data.get('replaces'):
            data['replaceHash'] = self.activity.replacement(user, data['replaces'], data)
        for other in self.db.execute("SELECT data FROM choices WHERE state IN ('requesting','pending','submitting','uncertain')"):
            c = json.loads(other[0])['context']
            if (c['mediaType'], c['mediaId']) == (ctx['mediaType'], ctx['mediaId']):
                raise Problem('This title already has an active selection. Resolve it in Download status first.')
        body = {k: ctx[k] for k in ('mediaType', 'mediaId', 'profileId', 'serverId', 'rootFolder')}
        if ctx['mediaType'] == 'tv':
            body.update(seasons=[ctx['season']], tvdbId=ctx['tvdbId'])
        # A failed/cancelled selection can choose another release under the SAME
        # owned request and approved profile/season. Never borrow another user's approval.
        for previous_state, raw in self.db.execute("SELECT state,data FROM choices WHERE owner=? AND state IN ('failed','cancelled','submitted') ORDER BY created DESC", (user['id'],)):
            previous = json.loads(raw)
            # A season request covers subsequent, explicitly selected episodes too.
            if previous_state == 'submitted' and ctx['mediaType'] != 'tv' and not data.get('replaces'):
                continue
            keys = ('mediaType', 'mediaId', 'profileId', 'serverId', 'rootFolder', 'season')
            if not previous.get('requestId') or any(previous['context'].get(k) != ctx.get(k) for k in keys):
                continue
            try:
                request = self.seerr().call('/request/'+str(previous['requestId']))
            except media.APIError as error:
                if error.status == 404:
                    continue
                raise
            if request.get('requestedBy', {}).get('id') == user['id'] and request['status'] in (1, 2):
                data['requestId'] = request['id']
                self.save(token, user['id'], 'pending', data, created)
                return {'state': 'pending', 'message': 'New selection saved under your existing request.'}
        self.save(token, user['id'], 'requesting', data, created)
        try:
            request = self.seerr(user['id']).call('/request', body)
            data['requestId'] = request['id']
            self.save(token, user['id'], 'pending', data, created)
        except media.APIError as error:
            data['message'] = 'Seerr rejected the request; check your quota, approvals, or existing requests.'
            self.save(token, user['id'], 'failed' if error.status < 500 else 'uncertain', data, created)
            raise Problem(data['message']) from None
        except Exception:
            data['message'] = 'Request outcome unknown. Check Seerr before making another selection.'
            self.save(token, user['id'], 'uncertain', data, created)
            raise Problem(data['message']) from None
        return {'state': 'pending', 'message': 'Selection saved. Waiting for approval and release verification.'}

    def process(self):
        for token, owner, created, raw in self.db.execute("SELECT id,owner,created,data FROM choices WHERE state='pending'").fetchall():
            data = json.loads(raw)
            try:
                if self.removal.blocked(data['context']['mediaType'], data['context']['mediaId']):
                    raise Problem('An administrator is removing this title.')
                request = self.seerr().call('/request/'+str(data['requestId']))
                if request.get('requestedBy', {}).get('id') != owner:
                    raise Problem('Request ownership changed.')
                if request['status'] == 1:
                    continue
                if request['status'] != 2:
                    raise Problem('Request was declined, cancelled, or completed. No release was sent.')
                self.guard()
                user = self.seerr().call('/user/'+str(owner))
                self.permitted(user, data['context']['mediaType'])
                # Re-search only to verify the selected release, never to choose a replacement.
                exact = next((r for r in self.releases(data['context']) if fingerprint(r) == fingerprint(data['release'])), None)
                if not exact or rejection(exact, data['context']):
                    raise Problem('The selected release disappeared or no longer meets the rules. Choose again.')
                if not media.space_ok(self.cfg):
                    raise Problem('Download budget or free-space reserve reached.')
                # Durable at-most-once fence BEFORE the external side effect.
                self.save(token, owner, 'submitting', data, created)
                try:
                    if data.get('replaces'):
                        self.activity.stop_replaced(user, data)
                    receipt = self.arr(data['context']['mediaType']).call('/release', {'guid': exact['guid'], 'indexerId': exact['indexerId']})
                    if isinstance(receipt, dict) and activity_module.torrent_hash(receipt.get('downloadId')):
                        data['downloadId'] = activity_module.torrent_hash(receipt['downloadId'])
                except Exception:
                    data['message'] = 'Download outcome unknown. Check the queue; this selection will not retry.' + (' The original transfer may be stopped; its files are retained.' if data.get('replaces') else '')
                    self.save(token, owner, 'uncertain', data, created)
                else:
                    data['message'] = 'Selected release sent to the downloader.'
                    self.save(token, owner, 'submitted', data, created)
                    if data.get('replaces'):
                        old_created, _, old = self.get(data['replaces'], user)
                        old['downloadId'] = data['replaceHash']
                        old['message'] = 'Replaced by your confirmed selection. Old files are retained.'
                        self.save(data['replaces'], owner, 'replaced', old, old_created)
            except Problem as error:
                data['message'] = str(error)
                self.save(token, owner, 'failed', data, created)
            except media.APIError as error:
                if error.status == 404:
                    data['message'] = 'Request or title was removed. No download was sent.'
                    self.save(token, owner, 'failed', data, created)
                # Read failures are safe to retry; no download submission has happened.
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                pass

    def cancel(self, user, token):
        # Cancelling local intent never removes somebody else's request or queued download.
        row = self.db.execute('SELECT owner,created,state,data FROM choices WHERE id=?', (token,)).fetchone()
        if not row or (row[0] != user['id'] and not user.get('permissions', 0) & 2):
            raise Problem('Selection not found.', 404)
        if row[2] not in ('preview', 'pending', 'failed', 'uncertain'):
            raise Problem('This selection has already been sent. Manage it in the download queue.')
        data = json.loads(row[3])
        data['message'] = 'Selection cancelled. Any existing Seerr request is retained.'
        self.save(token, row[0], 'cancelled', data, row[1])
        return {'state': 'cancelled'}


def serve(cfg):
    broker = Broker(cfg)
    personal = personal_module.Personal(broker, media, Problem) if cfg.get('personalHome') else None
    if personal:
        threading.Thread(target=personal.run, daemon=True).start()
        threading.Thread(target=personal.next_up.run, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # URLs, headers and response bodies can carry private credentials.

        def respond(self):
            try:
                if self.headers.get('Origin') and self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    raise Problem('Cross-site requests are not allowed.', 403)
                user = broker.identity(self.headers)
                body = {}
                if self.command == 'POST':
                    length = int(self.headers.get('Content-Length', '0'))
                    if length < 1 or length > 16384:
                        raise Problem('Invalid request body.', 400)
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise Problem('Invalid request body.', 400)
                if self.command == 'GET' and self.path == '/disk-usage':
                    # No broker lock: a long release search must not block this read.
                    try:
                        result = disk_usage(broker.cfg['root'])
                    except (OSError, ValueError):
                        raise Problem('Disk usage is temporarily unavailable.', 503) from None
                elif self.path.startswith('/personal-'):
                    if personal is None:
                        raise Problem('Personal discovery is disabled.', 404)
                    snapshot = personal.snapshot(user, self.headers)
                    if self.command == 'GET' and self.path == '/personal-home':
                        result = personal.home(snapshot)
                    elif self.command == 'POST' and self.path == '/personal-next-up-action':
                        result = personal.next_up.action(snapshot, body)
                    elif self.command == 'POST' and self.path == '/personal-action':
                        result = personal.feedback(snapshot, body)
                    elif self.command == 'POST' and self.path == '/personal-movie':
                        mid = body.get('mediaId')
                        kind = body.get('mediaType', 'movie')
                        if body.get('itemId'):
                            key = next((key for key, item in snapshot['items'].items() if item['Id'].replace('-', '').lower() == str(body['itemId']).replace('-', '').lower()), None)
                            if key is None:
                                raise Problem('Open a movie or series in your library.', 404)
                            kind, identifier = key.split(':')
                            mid = int(identifier)
                        result = personal.decorate(personal.detail(mid, snapshot, kind), snapshot, personal.profile(snapshot['owner']))
                    else:
                        raise Problem('Not found.', 404)
                else:
                    result = self.release_request(user, body)
                status = 200
            except Problem as error:
                status, result = error.status, {'error': str(error)}
            except Exception:
                status, result = 502, {'error': 'A media service could not complete this operation. No automatic replacement will be downloaded.'}
            data = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def release_request(self, user, body):
            with broker.lock:
                if self.command == 'GET' and self.path == '/capabilities':
                    result = {'canRemove': bool(user.get('permissions', 0) & 2), 'music': False}
                    if 'lidarr' in broker.cfg['enabled']:
                        try:
                            broker.music.account(user, self.headers)
                            result['music'] = True
                        except Problem:
                            pass
                elif self.path.startswith('/music-') and ((self.command == 'GET' and self.path == '/music-status') or
                                                          (self.command == 'POST' and self.path != '/music-status')):
                    result = broker.music.handle(user, self.headers, self.path[1:], body)
                elif self.command == 'GET' and self.path == '/activity':
                    result = broker.activity.listing(user, self.headers)
                    if 'lidarr' in broker.cfg['enabled']:
                        try:
                            jelly, admin = broker.music.account(user, self.headers)
                            result['music'] = broker.music.status(user, jelly, admin)
                        except Problem as error:
                            if error.status != 403:
                                result['musicError'] = 'Music status is temporarily unavailable.'
                        except Exception:
                            result['musicError'] = 'Music status is temporarily unavailable.'
                elif self.command == 'POST' and self.path == '/acknowledge':
                    token = body.get('id')
                    if not isinstance(token, str) or len(token) > 100:
                        raise Problem('Invalid notification.', 400)
                    result = broker.activity.acknowledge(user, token)
                elif self.command == 'GET' and self.path == '/removal-catalogue':
                    result = broker.removal.catalogue(user)
                elif self.command == 'POST' and self.path == '/removal-preview':
                    result = broker.removal.preview(user, body)
                elif self.command == 'POST' and self.path == '/item-removal-preview':
                    result = broker.removal.item_preview(user, self.headers, body)
                elif self.command == 'POST' and self.path == '/remove':
                    token = body.get('id')
                    if not isinstance(token, str) or len(token) > 100:
                        raise Problem('Invalid removal confirmation.', 400)
                    result = broker.removal.execute(user, token)
                elif self.command == 'POST' and self.path in ('/search', '/episodes', '/select', '/cancel', '/subtitle-search', '/subtitle-download', '/subtitle-status'):
                    if self.path == '/search':
                        result = broker.search(user, body)
                    elif self.path == '/episodes':
                        result = broker.episodes(user, body)
                    elif self.path == '/subtitle-search':
                        result = broker.subtitle_search(user, self.headers, body)
                    else:
                        token = body.get('id')
                        if not isinstance(token, str) or len(token) > 100:
                            raise Problem('Invalid selection.', 400)
                        if self.path == '/subtitle-download':
                            result = broker.subtitle_download(user, self.headers, token)
                        elif self.path == '/subtitle-status':
                            result = broker.subtitle_status(user, self.headers, token)
                        else:
                            result = broker.select(user, token) if self.path == '/select' else broker.cancel(user, token)
                else:
                    raise Problem('Not found.', 404)
                return result

        do_GET = respond
        do_POST = respond

    def pending():
        while True:
            time.sleep(15)
            with broker.lock:
                broker.process()
                try:
                    broker.music.process()
                except Exception:
                    # A temporary music service outage must not stop the worker.
                    print('Music import check unavailable; retrying on the next pass.', flush=True)
    threading.Thread(target=pending, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', cfg['releasePort']), Handler).serve_forever()


if __name__ == '__main__':
    serve(json.loads(Path('/etc/media-stack.json').read_text()))
