"""User-scoped download progress, readiness and explicit transfer replacement."""
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlencode


def torrent_hash(value):
    value = str(value or '').lower()
    return value if re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', value) else None


class Activity:
    def __init__(self, broker, media, problem):
        self.b, self.media, self.Problem = broker, media, problem
        self.b.db.execute('CREATE TABLE IF NOT EXISTS ready_notices (id TEXT PRIMARY KEY, owner INTEGER, selection TEXT, item TEXT, acknowledged INTEGER DEFAULT 0, UNIQUE(owner,selection,item))')
        self.b.db.commit()

    def read(self, api, path, cache):
        key = (getattr(api, 'base', ''), getattr(api, 'prefix', ''), tuple(sorted(getattr(api, 'headers', {}).items())), path)
        if key not in cache:
            if time.monotonic() >= cache.get('deadline', float('inf')):
                raise TimeoutError('Progress refresh deadline reached.')
            api.timeout = 8
            try:
                cache[key] = api.call(path)
            except Exception as error:
                cache[key] = error
        if isinstance(cache[key], Exception):
            raise cache[key]
        return cache[key]

    def download_id(self, data, cache=None):
        cache = {} if cache is None else cache
        known = torrent_hash(data.get('downloadId')) or torrent_hash(data['release'].get('infoHash'))
        if known:
            return known
        ctx = data['context']; movie = ctx['mediaType'] == 'movie'
        key = 'movieId' if movie else 'seriesId'
        rows = self.read(self.b.arr(ctx['mediaType']), '/history/'+('movie' if movie else 'series')+'?'+urlencode({key: ctx['arrId']}), cache)
        matches = {torrent_hash(row.get('downloadId')) for row in rows
                   if row.get(key) == ctx['arrId'] and row.get('sourceTitle') == data['release']['title']}
        matches.discard(None)
        return next(iter(matches)) if len(matches) == 1 else None

    @staticmethod
    def same_scope(a, b):
        return all(a.get(k) == b.get(k) for k in ('mediaType', 'mediaId', 'arrId', 'season', 'episode'))

    def replacement(self, user, old_id, new_data):
        if not isinstance(old_id, str) or len(old_id) > 100:
            raise self.Problem('Invalid replacement selection.', 400)
        _, state, old = self.b.get(old_id, user)
        if state != 'submitted' or not self.same_scope(old['context'], new_data['context']):
            raise self.Problem('Choose a replacement for the same movie, episode, or full season.')
        hash_id = self.download_id(old)
        if not hash_id:
            raise self.Problem('The original transfer cannot be identified safely. Check the download queue.')
        if torrent_hash(new_data['release'].get('infoHash')) == hash_id or new_data['release'].get('guid') == old['release'].get('guid'):
            raise self.Problem('Choose a different release, not the same torrent.')
        self.check_shared(user, old_id, old, hash_id)
        q = self.b.removal.qbit(timeout=8)
        torrent = next((t for t in q.call('/torrents/info') if torrent_hash(t['hash']) == hash_id), None)
        if not torrent or torrent.get('progress', 0) >= 1:
            raise self.Problem('The original transfer finished or disappeared. Refresh its status.')
        if torrent.get('category') != ('movies' if old['context']['mediaType'] == 'movie' else 'tv'):
            raise self.Problem('The original transfer has an unexpected category.')
        return hash_id

    def check_shared(self, user, old_id, old, hash_id):
        for token, owner, raw in self.b.db.execute("SELECT id,owner,data FROM choices WHERE state IN ('submitted','pending','submitting','uncertain')"):
            if token == old_id:
                continue
            other = json.loads(raw)
            same_hash = (torrent_hash(other.get('downloadId')) or torrent_hash(other['release'].get('infoHash'))) == hash_id
            if same_hash or (owner != user['id'] and self.same_scope(other['context'], old['context'])):
                raise self.Problem('Another selection uses this transfer. Manage shared downloads as administrator.')

    def stop_replaced(self, user, data):
        # Called only after approval, exact-release validation and a durable submitting fence.
        old_id = data['replaces']
        _, state, old = self.b.get(old_id, user)
        if state != 'submitted':
            raise self.Problem('The original selection changed; replacement stopped.')
        hash_id = data['replaceHash']
        self.check_shared(user, old_id, old, hash_id)
        q = self.b.removal.qbit(timeout=8)
        target = next((t for t in q.call('/torrents/info') if torrent_hash(t['hash']) == hash_id), None)
        if not target or target.get('progress', 0) >= 1:
            raise self.Problem('The original transfer finished or disappeared.')
        if target.get('category') != ('movies' if old['context']['mediaType'] == 'movie' else 'tv'):
            raise self.Problem('The original transfer has an unexpected category.')
        q.call('/torrents/stop', {'hashes': hash_id}, form=True)
        for _ in range(10):
            target = next((t for t in q.call('/torrents/info') if torrent_hash(t['hash']) == hash_id), None)
            if target and target['state'] in ('stoppedDL', 'pausedDL'):
                return
            time.sleep(.2)
        raise self.Problem('Could not confirm that the old download stopped. No replacement was sent.')

    def ready_items(self, user, headers, ctx, cache):
        api = self.media.API(self.b.cfg['ports']['jellyfin'], headers={k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        arr = self.b.arr(ctx['mediaType'])
        movie = ctx['mediaType'] == 'movie'
        catalog = self.read(arr, '/movie' if movie else '/series', cache)
        record = next((r for r in catalog if r['id'] == ctx['arrId']), None)
        if not record or record.get('tmdbId' if movie else 'tvdbId') != ctx.get('mediaId' if movie else 'tvdbId'):
            return []
        root = Path(self.b.cfg['root'])/'library'
        folder = Path(record['path']).resolve()
        if folder == root.resolve() or root.resolve() not in folder.parents:
            return []
        query = {'userId': user['jellyfinUserId'], 'Recursive': 'true', 'IncludeItemTypes': 'Movie' if movie else 'Episode',
                 'Fields': 'Path,MediaStreams', 'Limit': 200, 'StartIndex': 0}
        result = []
        while True:
            response = self.read(api, '/Items?'+urlencode(query), cache)
            for item in response.get('Items', []):
                path = Path(item.get('Path') or '/').resolve()
                if folder not in path.parents or not path.is_file() or item.get('IsVirtualItem'):
                    continue
                if not movie and (item.get('ParentIndexNumber') != ctx['season'] or
                                  (ctx.get('episode') is not None and item.get('IndexNumber') != ctx['episode'])):
                    continue
                if not any(s.get('Type') == 'Video' for s in item.get('MediaStreams', [])):
                    continue
                languages = {str(s.get('Language', '')).casefold() for s in item.get('MediaStreams', []) if s.get('Type') == 'Subtitle'}
                result.append({'id': item['Id'], 'title': item.get('Name', ''),
                               'episode': item.get('IndexNumber'), 'season': item.get('ParentIndexNumber'),
                               'subtitles': {'pb': bool(languages & {'pt-br', 'pob', 'pb'}), 'en': bool(languages & {'eng', 'en'})}})
            query['StartIndex'] += len(response.get('Items', []))
            if not response.get('Items') or query['StartIndex'] >= response.get('TotalRecordCount', 0):
                break
        return sorted(result, key=lambda r: (r.get('episode') or 0, r['title']))

    def listing(self, user, headers):
        cache, output, notifications = {'deadline': time.monotonic()+20}, [], []
        q, qerror = None, None
        rows = self.b.db.execute("SELECT id,created,state,data FROM choices WHERE owner=? AND state != 'preview' ORDER BY created DESC LIMIT 40", (user['id'],)).fetchall()
        for token, created, state, raw in rows:
            data = json.loads(raw); ctx = data['context']
            row = {'id': token, 'state': state, 'title': ctx['title'], 'release': data['release']['title'], 'phase': state,
                   'message': data.get('message', ''), 'ready': [], 'canReplace': False, 'downloadComplete': False,
                   'context': {k: ctx.get(k) for k in ('mediaType', 'mediaId', 'profileId', 'season', 'episode')}}
            if state in ('removed', 'replaced', 'cancelled'):
                continue
            try:
                if state == 'pending':
                    request = self.read(self.b.seerr(), '/request/'+str(data['requestId']), cache)
                    approved = request.get('status') == 2
                    row.update(phase='verifying' if approved else 'approval', message='Verifying your selected release.' if approved else 'Waiting for request approval.')
                elif state == 'submitted':
                    row['ready'] = self.ready_items(user, headers, ctx, cache)
                    if row['ready']:
                        row.update(phase='ready', message='Ready to watch.' if ctx.get('episode') is not None or ctx['mediaType'] == 'movie' else f"{len(row['ready'])} episodes ready to watch.")
                        for item in row['ready']:
                            self.b.db.execute('INSERT OR IGNORE INTO ready_notices (id,owner,selection,item) VALUES (?,?,?,?)',
                                              (secrets.token_urlsafe(20), user['id'], token, item['id']))
                            notice = self.b.db.execute('SELECT id,acknowledged FROM ready_notices WHERE owner=? AND selection=? AND item=?', (user['id'], token, item['id'])).fetchone()
                            if not notice[1]:
                                notifications.append({'id': notice[0], 'title': row['title'], 'item': item})
                    if not row['ready'] or (ctx['mediaType'] == 'tv' and ctx.get('episode') is None):
                        hash_id = self.download_id(data, cache)
                        if qerror:
                            raise qerror
                        if q is None:
                            if time.monotonic() >= cache['deadline']:
                                raise TimeoutError('Progress refresh deadline reached.')
                            try:
                                q = self.b.removal.qbit(timeout=8)
                            except Exception as error:
                                qerror = error
                                raise
                        torrents = self.read(q, '/torrents/info', cache)
                        transfer = next((t for t in torrents if torrent_hash(t['hash']) == hash_id), None) if hash_id else None
                        if not row['ready']:
                            row.update(phase='importing', message='Waiting for import and Jellyfin library discovery.')
                        if transfer:
                            status = transfer['state']; progress = transfer.get('progress', 0)
                            row['downloadComplete'] = progress >= 1
                            if progress < 1:
                                if status not in ('metaDL', 'forcedMetaDL', 'error', 'missingFiles'):
                                    row.update(percent=min(99.9, round(progress*100, 1)), speed=transfer.get('dlspeed', 0), peers=transfer.get('num_seeds', 0))
                                row['canReplace'] = bool(hash_id)
                                phases = {'metaDL': ('metadata', 'Waiting for torrent metadata from peers.'),
                                          'forcedMetaDL': ('metadata', 'Waiting for torrent metadata from peers.'),
                                          'queuedDL': ('queued', 'Queued behind another download.'),
                                          'stalledDL': ('peers', 'Waiting for peers to send data.'),
                                          'pausedDL': ('paused', 'Download is paused.'), 'stoppedDL': ('paused', 'Download is stopped.'),
                                          'error': ('error', 'Downloader reported an error; check its queue.'),
                                          'missingFiles': ('error', 'Downloader cannot find its files.')}
                                phase, message = phases.get(status, ('downloading', 'Downloading your selected release.'))
                                row.update(phase=phase, message=message)
            except Exception:
                row.update(phase='unavailable', message='Status is temporarily unavailable. No replacement will start automatically.', canReplace=False)
            output.append(row)
        self.b.db.commit()
        return {'selections': output, 'notifications': notifications[:20]}

    def acknowledge(self, user, token):
        self.b.db.execute('UPDATE ready_notices SET acknowledged=1 WHERE id=? AND owner=?', (token, user['id']))
        self.b.db.commit()
        return {'acknowledged': True}
