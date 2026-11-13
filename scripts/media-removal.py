"""Explicit, administrator-confirmed removal through the owning service APIs."""
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlencode


class Removal:
    def __init__(self, broker, media, problem):
        self.b, self.media, self.Problem = broker, media, problem
        broker.db.execute('CREATE TABLE IF NOT EXISTS removals (id TEXT PRIMARY KEY, owner INTEGER, created REAL, state TEXT, data TEXT)')
        broker.db.commit()

    def admin(self, user):
        if not user.get('permissions', 0) & 2:
            raise self.Problem('Only an administrator can remove shared media.', 403)

    def blocked(self, kind, mid):
        return any(json.loads(raw)['mediaType'] == kind and json.loads(raw)['mediaId'] == mid
                   for (raw,) in self.b.db.execute("SELECT data FROM removals WHERE state IN ('removing','failed')"))

    def item_preview(self, user, headers, body):
        """Resolve the authenticated Jellyfin item before offering full removal."""
        self.admin(user)
        item_id = str(body.get('itemId') or '').replace('-', '')
        if not re.fullmatch(r'[a-fA-F0-9]{32}', item_id):
            raise self.Problem('Invalid library item.', 400)
        jelly = self.media.API(self.b.cfg['ports']['jellyfin'], headers={
            k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        account = jelly.call('/Users/Me')
        if (not account.get('Policy', {}).get('IsAdministrator')
                or account.get('Policy', {}).get('IsDisabled')
                or account['Id'].replace('-', '').lower() != user['jellyfinUserId'].replace('-', '').lower()):
            raise self.Problem('Only a Jellyfin administrator can remove shared media.', 403)
        def get_item(identifier):
            if not re.fullmatch(r'[a-fA-F0-9-]{32,36}', str(identifier or '')):
                raise self.Problem('The parent library item could not be identified.')
            return jelly.call('/Users/'+account['Id']+'/Items/'+identifier)
        item = get_item(item_id)
        if item.get('Type') in ('Episode', 'Season'):
            item = get_item(item.get('SeriesId'))
        elif item.get('Type') == 'Audio':
            item = get_item(item.get('AlbumId'))
        kind = {'Movie':'movie', 'Series':'tv', 'MusicAlbum':'music'}.get(item.get('Type'))
        if not kind:
            raise self.Problem('Full removal supports movies, series and music albums. Open the title itself to remove it.')
        path = Path(self.safe_path(item.get('Path') or '/', 'library/'+{'movie':'movies','tv':'tv','music':'music'}[kind])).resolve()
        if kind == 'music':
            broker_music = self.b.music
            _, admin = broker_music.account(user, headers)
            if not admin:
                raise self.Problem('Only an administrator can remove shared music.', 403)
            mid = broker_music.identifier((item.get('ProviderIds') or {}).get('MusicBrainzReleaseGroup'))
            albums = broker_music.api().call('/album?'+urlencode({'foreignAlbumId':mid}))
            files = broker_music.files(albums[0]['id']) if albums else []
            if not files or any(path not in Path(f['path']).resolve().parents for f in files):
                raise self.Problem('The music library identity changed. Use Music downloads to review removal.')
            return {**broker_music.removal_preview(user, {'id':mid}), 'mediaType':'music'}
        provider = (item.get('ProviderIds') or {}).get('Tmdb')
        if not str(provider or '').isdigit():
            raise self.Problem('This title has no TMDB identity. Use Remove from server in Requests to select it.')
        mid = int(provider)
        # Verify both catalogue identity and physical location; provider metadata alone
        # must not authorize deletion of a different managed title.
        snapshot = self.snapshot(kind, mid)
        folder = Path(snapshot['libraryPath']).resolve() if snapshot['libraryPath'] else None
        if not folder or not (path == folder or folder in path.parents):
            raise self.Problem('Jellyfin and the library manager disagree about this title’s folder. Removal stopped.')
        for token, raw in self.b.db.execute("SELECT id,data FROM removals WHERE owner=? AND state IN ('removing','failed')", (user['id'],)):
            saved = json.loads(raw)
            if saved['mediaType'] == kind and saved['mediaId'] == mid:
                return {'id':token, 'title':saved['title'], 'mediaType':kind, 'retry':True}
        if self.blocked(kind, mid):
            raise self.Problem('This removal is incomplete. Use Retry removal in the list.')
        return self.save_preview(user, snapshot)

    def pages(self, api, endpoint):
        result, page = [], 1
        while True:
            data = api.call(endpoint+('&' if '?' in endpoint else '?')+urlencode({'page': page, 'pageSize': 100}))
            rows = data['records']; result.extend(rows)
            if len(result) >= data['totalRecords']:
                return result
            if not rows:
                raise self.Problem('The download queue changed. Refresh before removing.')
            page += 1

    def catalogue(self, user):
        self.admin(user)
        titles = {}
        for kind, endpoint in (('movie', '/movie'), ('tv', '/series')):
            for item in self.b.arr(kind).call(endpoint):
                mid = item.get('tmdbId')
                if mid:
                    titles[kind, mid] = {'mediaType': kind, 'mediaId': mid, 'title': item['title']}
        # Includes pending requests and titles whose library entry was already deleted.
        offset = 0
        while True:
            rows = self.b.seerr().call(f'/request?take=100&skip={offset}')['results']
            for row in rows:
                info = row['media']; kind, mid = info['mediaType'], info['tmdbId']
                if kind in ('movie', 'tv') and (kind, mid) not in titles:
                    detail = self.b.seerr().call(f'/{kind}/{mid}')
                    titles[kind, mid] = {'mediaType': kind, 'mediaId': mid, 'title': detail.get('title') or detail.get('name') or str(mid)}
            if len(rows) < 100:
                break
            offset += 100
        for token, state, raw in self.b.db.execute("SELECT id,state,data FROM removals WHERE state IN ('removing','failed')"):
            data = json.loads(raw)
            titles[data['mediaType'], data['mediaId']] = {k: data[k] for k in ('mediaType', 'mediaId', 'title')}
            titles[data['mediaType'], data['mediaId']]['retryId'] = token
        return sorted(titles.values(), key=lambda row: row['title'].casefold())

    def safe_path(self, value, area):
        path, root = Path(value), Path(self.b.cfg['root'])/area
        if not path.is_absolute() or path.resolve() == root.resolve() or root.resolve() not in path.resolve().parents:
            raise self.Problem('Refusing removal outside the managed media folders.')
        if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
            raise self.Problem('Refusing removal through a symbolic link.')
        return str(path)

    def qbit(self, timeout=30):
        api = self.media.API(self.b.cfg['ports']['qbittorrent'], '/api/v2')
        api.timeout = timeout
        api.call('/auth/login', {'username': 'admin', 'password': self.b.creds()['qbittorrent']['password']}, form=True)
        return api

    def safe_download_path(self, value):
        # Manual torrent management can use the default save directory instead
        # of its category directory. The exact hash/category still binds the
        # torrent to the title; never allow removal of a shared container itself.
        path = Path(self.safe_path(value, 'downloads')).resolve()
        root = (Path(self.b.cfg['root'])/'downloads').resolve()
        if path in (root/'movies', root/'tv', root/'temp'):
            raise self.Problem('Refusing removal of a shared download folder.')
        return str(value)

    def snapshot(self, kind, mid):
        detail = self.b.seerr().call(f'/{kind}/{mid}')
        field = 'tmdbId' if kind == 'movie' else 'tvdbId'
        external = mid if kind == 'movie' else detail.get('externalIds', {}).get('tvdbId')
        endpoint = '/movie' if kind == 'movie' else '/series'
        api = self.b.arr(kind)
        catalog = api.call(endpoint)
        item = next((x for x in catalog if external and x.get(field) == external), None)
        data = {'mediaType': kind, 'mediaId': mid, 'externalId': external, 'arrId': item['id'] if item else None,
                'title': detail.get('title') or detail.get('name') or (item or {}).get('title') or str(mid),
                'seerrId': (detail.get('mediaInfo') or {}).get('id'), 'hashes': [], 'paths': [], 'libraryPath': None}
        hashes = set()
        if item:
            area = 'library/movies' if kind == 'movie' else 'library/tv'
            data['libraryPath'] = self.safe_path(item['path'], area)
            path = Path(data['libraryPath']).resolve()
            if any(x['id'] != item['id'] and (Path(x['path']).resolve() == path or path in Path(x['path']).resolve().parents or Path(x['path']).resolve() in path.parents) for x in catalog):
                raise self.Problem('This library folder is shared with another title. Remove it manually.')
            key = 'movieId' if kind == 'movie' else 'seriesId'
            history = api.call('/history/'+('movie' if kind == 'movie' else 'series')+'?'+urlencode({key: item['id']}))
            queue = self.pages(api, '/queue')
            hashes.update(str(x['downloadId']).lower() for x in history+queue if x.get(key) == item['id'] and x.get('downloadId'))
        for (raw,) in self.b.db.execute("SELECT data FROM choices WHERE state IN ('submitted','uncertain','submitting','replaced')"):
            choice = json.loads(raw)
            if choice['context']['mediaType'] == kind and choice['context']['mediaId'] == mid:
                hashes.add(str(choice['release'].get('infoHash', '')).lower())
                hashes.add(str(choice.get('downloadId', '')).lower())
        torrents = self.qbit().call('/torrents/info')
        for torrent in torrents:
            hash_id = torrent['hash'].lower()
            if hash_id not in hashes or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', hash_id):
                continue
            # A torrent associated with another title must never be deleted by this action.
            for other_kind in ('movie', 'tv'):
                key = 'movieId' if other_kind == 'movie' else 'seriesId'
                rows = self.pages(self.b.arr(other_kind), '/history?'+urlencode({'downloadId': hash_id}))
                rows += self.pages(self.b.arr(other_kind), '/queue')
                if any(str(x.get('downloadId', '')).lower() == hash_id and x.get(key) and (other_kind != kind or x[key] != data['arrId']) for x in rows):
                    raise self.Problem('A download is shared with another title. Remove it manually.')
            if torrent.get('category') != ('movies' if kind == 'movie' else 'tv'):
                raise self.Problem('A linked torrent has an unexpected category. Check qBittorrent.')
            path = Path(self.safe_download_path(torrent['content_path'])).resolve()
            for other in torrents:
                if other['hash'].lower() == hash_id or not other.get('content_path'):
                    continue
                other_path = Path(other['content_path']).resolve()
                if other_path == path or other_path in path.parents or path in other_path.parents:
                    raise self.Problem('Download files overlap another torrent. Remove it manually.')
            data['paths'].append(str(torrent['content_path']))
            data['hashes'].append(hash_id)
        data['hashes'].sort(); data['paths'].sort()
        return data

    def preview(self, user, body):
        self.admin(user)
        kind, mid = body.get('mediaType'), body.get('mediaId')
        if kind not in ('movie', 'tv') or type(mid) is not int or mid < 1:
            raise self.Problem('Invalid title.', 400)
        if self.blocked(kind, mid):
            raise self.Problem('This removal is incomplete. Use Retry removal in the list.')
        data = self.snapshot(kind, mid)
        return self.save_preview(user, data)

    def save_preview(self, user, data):
        token = secrets.token_urlsafe(24)
        self.b.db.execute("DELETE FROM removals WHERE state='preview' AND created < ?", (time.time()-300,))
        self.b.db.execute('INSERT INTO removals VALUES (?,?,?,?,?)', (token, user['id'], time.time(), 'preview', json.dumps(data)))
        self.b.db.commit()
        return {'id': token, 'title': data['title'], 'mediaType': data['mediaType'], 'downloads': len(data['hashes']), 'hasLibrary': bool(data['arrId'])}

    def execute(self, user, token):
        self.admin(user)
        row = self.b.db.execute('SELECT owner,created,state,data FROM removals WHERE id=?', (token,)).fetchone()
        if not row or row[0] != user['id']:
            raise self.Problem('Removal confirmation not found.', 404)
        owner, created, state, raw = row
        data = json.loads(raw)
        if state == 'complete':
            return {'state': 'complete', 'message': 'Removed from the server. Jellyfin is refreshing.'}
        if state == 'preview':
            if self.blocked(data['mediaType'], data['mediaId']):
                raise self.Problem('Another removal is already in progress. Refresh the list.')
            if time.time()-created > 300 or self.snapshot(data['mediaType'], data['mediaId']) != data:
                raise self.Problem('The title or downloads changed. Close and preview removal again.')
        self.b.db.execute("UPDATE removals SET state='removing' WHERE id=?", (token,))
        for choice_id, choice_owner, choice_created, choice_raw in self.b.db.execute('SELECT id,owner,created,data FROM choices').fetchall():
            choice = json.loads(choice_raw)
            if all(choice['context'][k] == data[k] for k in ('mediaType', 'mediaId')):
                choice['message'] = 'Removed by an administrator.'
                self.b.save(choice_id, choice_owner, 'removed', choice, choice_created)
        self.b.db.commit()  # Durable fence: pending choices cannot restart this title.
        try:
            q = self.qbit()
            live = {t['hash'].lower(): t for t in q.call('/torrents/info')}
            for hash_id in data['hashes']:
                if hash_id in live and live[hash_id]['content_path'] not in data['paths']:
                    raise self.Problem('A download moved since confirmation. Check qBittorrent before retrying.')
                if hash_id in live:
                    self.safe_download_path(live[hash_id]['content_path'])
            if data['hashes']:
                q.call('/torrents/stop', {'hashes': '|'.join(data['hashes'])}, form=True)
                q.call('/torrents/delete', {'hashes': '|'.join(data['hashes']), 'deleteFiles': 'true'}, form=True)
                for _ in range(20):
                    if not any(t['hash'].lower() in data['hashes'] for t in q.call('/torrents/info')) and not any(Path(p).exists() for p in data['paths']):
                        break
                    time.sleep(.25)
                else:
                    raise self.Problem('Download removal is still pending. Retry after qBittorrent finishes.')
            kind = data['mediaType']; endpoint = '/movie' if kind == 'movie' else '/series'
            api = self.b.arr(kind)
            if data['arrId']:
                current = next((x for x in api.call(endpoint) if x['id'] == data['arrId']), None)
                if current:
                    field = 'tmdbId' if kind == 'movie' else 'tvdbId'
                    if current.get(field) != data['externalId'] or current['path'] != data['libraryPath']:
                        raise self.Problem('Library identity changed. Removal stopped; review the library manager.')
                    self.safe_path(current['path'], 'library/movies' if kind == 'movie' else 'library/tv')
                    api.call(endpoint+'/'+str(data['arrId'])+'?deleteFiles=true', method='DELETE')
                # The library manager may return before its deletion event finishes.
                # Wait for the files, rather than treating that short delay as a
                # permissions failure and leaving the request record behind.
                for _ in range(20):
                    if not Path(data['libraryPath']).exists() or not any(Path(data['libraryPath']).rglob('*')):
                        break
                    time.sleep(.25)
                else:
                    raise self.Problem('Library cleanup has not finished. Retry removal shortly; inspect permissions only if files continue to remain.')
            if data['seerrId']:
                try:
                    self.b.seerr().call('/media/'+str(data['seerrId']), method='DELETE')
                except self.media.APIError as error:
                    if error.status != 404:
                        raise self.Problem(f'Request-record cleanup failed (HTTP {error.status}). Retry removal.') from None
            self.b.media_jellyfin_admin().call('/Library/Refresh', method='POST')
        except Exception as error:
            self.b.db.execute("UPDATE removals SET state='failed' WHERE id=?", (token,)); self.b.db.commit()
            reason = str(error) if isinstance(error, self.Problem) else 'A media service could not finish the operation.'
            raise self.Problem('Removal is incomplete. '+reason+' Some files may already be deleted. Use Retry removal; no automatic download will resume.') from None
        self.b.db.execute("UPDATE removals SET state='complete' WHERE id=?", (token,)); self.b.db.commit()
        return {'state': 'complete', 'message': 'Removed from the server. Jellyfin is refreshing.'}
