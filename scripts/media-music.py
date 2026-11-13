"""Album discovery and explicit, user-bound Lidarr release selection."""
import json
from datetime import datetime
from pathlib import Path
import secrets
import shutil
import time
import uuid
from urllib.parse import urlencode


class Music:
    def __init__(self, broker, media, problem, restricted, torrent_hash):
        self.b, self.media, self.Problem, self.restricted = broker, media, problem, restricted
        self.torrent_hash = torrent_hash
        self.db = broker.db
        for table in ('music_choices', 'music_removals'):
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, owner INTEGER, created REAL, state TEXT, data TEXT)')
        self.db.execute("UPDATE music_choices SET state='uncertain' WHERE state='submitting'")
        self.db.commit()

    def api(self):
        api = self.media.API(self.b.cfg['ports']['lidarr'], '/api/v1', {'X-Api-Key': self.b.creds()['lidarr']['apiKey']})
        api.timeout = 180
        return api

    def account(self, user, headers):
        if 'lidarr' not in self.b.cfg['enabled']:
            raise self.Problem('Music discovery is disabled.', 404)
        api = self.media.API(self.b.cfg['ports']['jellyfin'], headers={k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        info = api.call('/Users/Me'); policy = info.get('Policy', {})
        if (uuid.UUID(info['Id']) != uuid.UUID(user['jellyfinUserId']) or policy.get('IsDisabled')
                or self.restricted(policy) or not user.get('permissions', 0) & (2 | 32 | 262144 | 524288)):
            raise self.Problem('Music discovery requires an unrestricted account with request permission.', 403)
        return api, bool(policy.get('IsAdministrator') and user.get('permissions', 0) & 2)

    def identifier(self, value):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise self.Problem('Invalid music identifier.', 400) from None

    def root(self):
        return Path(self.b.cfg['root'])/'library/music'

    def safe_path(self, value, root=None):
        root = root or self.root()
        path = Path(value or '/')
        if (not path.is_absolute() or path.resolve() == root.resolve() or root.resolve() not in path.resolve().parents
                or any(p.is_symlink() for p in (path, *path.parents))):
            raise self.Problem('Music file is outside its managed folder.')
        return str(path)

    def download_path(self, value):
        # Manual qBittorrent management may use the default downloads directory
        # instead of its category directory. Never accept a shared container.
        root = Path(self.b.cfg['root'])/'downloads'
        path = Path(self.safe_path(value, root))
        relative = path.resolve().relative_to(root.resolve())
        if relative.parts[0] in ('movies', 'tv') or relative in (Path('music'), Path('temp')):
            raise self.Problem('Music download points to a shared or different media folder.')
        return str(path)

    def removal_download_path(self, torrent, q):
        if torrent.get('content_path'):
            return self.download_path(torrent['content_path'])
        # A magnet with no metadata has no content path or files to delete.
        # Validate its destination and remove only its exact torrent entry.
        root = Path(self.b.cfg['root'])/'downloads'
        destination = Path(torrent.get('save_path') or '/')
        if destination != root:
            self.safe_path(str(destination), root)
        if (not destination.is_absolute() or any(p.is_symlink() for p in (destination, *destination.parents))
                or torrent.get('progress', 0) != 0 or torrent.get('downloaded', 0) != 0
                or torrent.get('total_size', -1) > 0
                or q.call('/torrents/files?'+urlencode({'hash':torrent['hash']}))):
            raise self.Problem('Download files changed. Refresh Requests before removing it.')
        return None

    def artist_settings(self, artist):
        api = self.api()
        local = next((a for a in api.call('/artist') if a['foreignArtistId'] == artist['foreignArtistId']), None)
        if local:
            self.safe_path(local['path'])
            return local
        artist = dict(artist)
        artist.pop('id', None); artist.pop('path', None)
        artist.update(rootFolderPath=str(self.root()), monitored=False, monitorNewItems='none',
                      qualityProfileId=next(p['id'] for p in api.call('/qualityprofile') if p['name'] == 'Media stack music'),
                      metadataProfileId=next(p['id'] for p in api.call('/metadataprofile') if p['name'] == 'Media stack music'),
                      addOptions={'monitor':'none', 'monitored':False, 'searchForMissingAlbums':False})
        return artist

    def lookup(self, kind, identifier):
        identifier = self.identifier(identifier)
        rows = self.api().call('/'+kind+'/lookup?'+urlencode({'term':'lidarr:'+identifier}))
        key = 'foreignArtistId' if kind == 'artist' else 'foreignAlbumId'
        row = next((r for r in rows if r.get(key) == identifier), None)
        if not row:
            raise self.Problem('This release is not available in the music catalogue. Try again later.', 404)
        return row

    @staticmethod
    def summary(row, kind='album'):
        if kind == 'artist':
            return {'id': row['foreignArtistId'], 'title': row['artistName'], 'kind':'artist', 'description':row.get('disambiguation', '')}
        return {'id':row['foreignAlbumId'], 'title':row['title'], 'kind':'album',
                'artist':(row.get('artist') or {}).get('artistName', ''), 'year':(row.get('releaseDate') or '')[:4],
                'description':row.get('disambiguation') or row.get('albumType', '')}

    def search(self, body):
        query, kind = body.get('query'), body.get('kind', 'album')
        if kind not in ('artist', 'album') or not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
            raise self.Problem('Enter an artist or album title (2–100 characters).', 400)
        api = self.api(); api.timeout = 25
        try:
            rows = api.call('/'+kind+'/lookup?'+urlencode({'term':query.strip()}))
            return {'items':[self.summary(row, kind) for row in rows[:40]], 'warnings':[]}
        except (self.media.APIError, OSError, ValueError):
            raise self.Problem('Music catalogue is temporarily unavailable. Try again shortly; this is separate from torrent availability.', 503) from None

    def artist(self, body):
        artist = self.artist_settings(self.lookup('artist', body.get('id')))
        api = self.api()
        if not artist.get('id'):
            artist = api.call('/artist', artist)
        rows = api.call('/album?'+urlencode({'artistId':artist['id']}))
        return {'title':artist['artistName'], 'items':[self.summary({**r, 'artist':artist}) for r in rows],
                'message':'' if rows else 'Album metadata is loading. Open this artist again shortly.'}

    def album(self, mid):
        mid = self.identifier(mid); api = self.api()
        rows = api.call('/album?'+urlencode({'foreignAlbumId':mid}))
        if rows:
            album = api.call('/album/'+str(rows[0]['id']))
        else:
            album = dict(self.lookup('album', mid)); album.pop('id', None)
            album['artist'] = self.artist_settings(album['artist'])
            album.update(monitored=False, anyReleaseOk=True, addOptions={'addType':'manual', 'searchForNewAlbum':False})
            album = api.call('/album', album)
        self.safe_path(api.call('/artist/'+str(album['artistId']))['path'])
        return album

    def detail(self, body):
        album = self.album(body.get('id')); api = self.api()
        tracks = api.call('/track?'+urlencode({'albumId':album['id']}))
        editions = [{'title':r.get('title'), 'format':r.get('format'), 'country':r.get('country'),
                     'description':r.get('disambiguation'), 'tracks':r.get('trackCount')} for r in album.get('releases', [])]
        return {**self.summary(album), 'tracks':[{'number':t.get('trackNumber'), 'disc':t.get('mediumNumber'), 'title':t['title']} for t in tracks],
                'editions':editions, 'importedTracks':(album.get('statistics') or {}).get('trackFileCount', 0)}

    def guard(self, album):
        api = self.api()
        if any(s.get('enableRss') or s.get('enableAutomaticSearch') for s in api.call('/indexer')):
            raise self.Problem('Automatic music searches must be disabled. Run media-stack setup.')
        settings = api.call('/config/downloadclient')
        if settings.get('autoRedownloadFailed') or settings.get('autoRedownloadFailedFromInteractiveSearch'):
            raise self.Problem('Automatic music retries must be disabled.')
        if any(x.get('enableAutomaticAdd') for x in api.call('/importlist')):
            raise self.Problem('Disable automatic Lidarr import lists before selecting music.')
        artist = api.call('/artist/'+str(album['artistId']))
        self.safe_path(artist['path'])
        profile = api.call('/qualityprofile/'+str(artist['qualityProfileId']))
        if profile.get('upgradeAllowed'):
            raise self.Problem('Disable automatic upgrades for this artist in Lidarr.')
        for state, raw in self.db.execute("SELECT state,data FROM music_removals WHERE state IN ('removing','failed')"):
            if json.loads(raw)['albumId'] == album['id']:
                raise self.Problem('Finish this album’s removal before downloading again.')

    @staticmethod
    def quality(row):
        return ((row.get('quality') or {}).get('quality') or {}).get('name', 'Unknown')

    @staticmethod
    def manual_album_warning(row):
        if 'Unable to parse albums from release name' not in (row.get('rejections') or []):
            return None
        return 'Lidarr could not parse the release name. Confirm this is the selected album; your selection will be used for automatic import.'

    def reasons(self, row, album, quality):
        reasons = list(row.get('rejections') or [])
        warning = self.manual_album_warning(row)
        if warning:
            reasons = [r for r in reasons if r != 'Unable to parse albums from release name']
        name = self.quality(row).lower()
        if quality == 'flac' and not name.startswith('flac'):
            reasons.append('Choose a FLAC release.')
        if quality == 'mp3-320' and name != 'mp3-320':
            reasons.append('Choose MP3 320 kbps.')
        if quality == 'mp3-v0' and name not in ('mp3-v0', 'mp3-vbr-v0'):
            reasons.append('Choose MP3 V0.')
        if row.get('discography'):
            reasons.append('Choose a single album, not a discography.')
        if str(row.get('protocol')).lower() not in ('torrent', 'torrentdownloadprotocol', '2'):
            reasons.append('Only torrents are supported.')
        if row.get('albumId') not in (None, album['id']) or row.get('artistId') not in (None, album['artistId']):
            reasons.append('This release belongs to another album or artist.')
        if not row.get('guid') or not row.get('indexerId') or not row.get('size'):
            reasons.append('Incomplete release information.')
        if row.get('rejected') and not reasons and not warning:
            reasons.append('Lidarr rejected this release.')
        return reasons

    def save(self, table, token, owner, state, data, created=None):
        self.db.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?,?,?,?)', (token, owner, created or time.time(), state, json.dumps(data)))
        self.db.commit()

    def releases(self, user, body):
        quality = body.get('quality', 'flac')
        if quality not in ('flac', 'mp3-320', 'mp3-v0', 'any'):
            raise self.Problem('Unknown music quality.', 400)
        album = self.album(body.get('id')); self.guard(album)
        api = self.api(); sources = [i for i in api.call('/indexer') if i.get('enableInteractiveSearch')]
        if not sources:
            raise self.Problem('No music indexers are available. Enable a music-capable source in Prowlarr.')
        rows = api.call('/release?'+urlencode({'albumId':album['id']})); result = []
        self.db.execute("DELETE FROM music_choices WHERE state='preview' AND created < ?", (time.time()-900,))
        for row in rows[:100]:
            token = secrets.token_urlsafe(24); reasons = self.reasons(row, album, quality)
            if not reasons:
                self.save('music_choices', token, user['id'], 'preview', {'albumId':album['id'], 'mbid':album['foreignAlbumId'],
                    'title':album['title'], 'artist':album['artist']['artistName'], 'quality':quality, 'release':row})
            result.append({'id':token, 'title':row['title'], 'quality':self.quality(row), 'size':row['size'],
                           'seeders':row.get('seeders'), 'indexer':row.get('indexer'), 'rejections':reasons,
                           'warnings':[warning] if (warning := self.manual_album_warning(row)) else []})
        self.db.commit()
        return {'title':album['title'], 'releases':result}

    def choice(self, table, token, user):
        if not isinstance(token, str) or not 1 <= len(token) <= 100:
            raise self.Problem('Invalid selection.', 400)
        row = self.db.execute(f'SELECT owner,created,state,data FROM {table} WHERE id=?', (token,)).fetchone()
        if not row or row[0] != user['id']:
            raise self.Problem('Selection not found.', 404)
        return row[1], row[2], json.loads(row[3])

    def select(self, user, body):
        token = body.get('id'); created, state, data = self.choice('music_choices', token, user)
        if state == 'submitted':
            return {'message':'This release was already submitted. Open Music downloads.'}
        if state != 'preview' or time.time()-created > 900:
            raise self.Problem('Selection expired or its outcome is uncertain. Check Music downloads before trying again.')
        api = self.api(); album = api.call('/album/'+str(data['albumId'])); self.guard(album)
        if album['foreignAlbumId'] != data['mbid']:
            raise self.Problem('Album changed. Search again.')
        if (album.get('statistics') or {}).get('trackFileCount', 0):
            raise self.Problem('This album already has imported tracks. An administrator must remove it before replacing it.')
        for other, raw in self.db.execute("SELECT id,data FROM music_choices WHERE state IN ('submitted','submitting','uncertain')"):
            if other != token and json.loads(raw)['albumId'] == album['id']:
                raise self.Problem('This album already has a selection. Check its download or ask an administrator to remove it first.')
        rows = api.call('/release?'+urlencode({'albumId':album['id']}))
        fields = ('guid', 'indexerId', 'title', 'size', 'infoHash', 'quality')
        release = next((r for r in rows if all(r.get(k) == data['release'].get(k) for k in fields)), None)
        if (not release or self.reasons(release, album, data['quality'])
                or self.manual_album_warning(release) != self.manual_album_warning(data['release'])):
            raise self.Problem('Release availability or quality changed. Search again.')
        if not self.media.space_ok(self.b.cfg):
            raise self.Problem('The media disk budget or free-space reserve is exhausted.')
        required = 2 * release['size']  # Download plus a separately tagged library copy.
        cfg = self.b.cfg
        if (shutil.disk_usage(cfg['root']).free - required < cfg['minFreeGiB'] * self.media.GIB
                or (cfg['budgetGiB'] is not None and self.media.usage_bytes(cfg['root']) + required > cfg['budgetGiB'] * self.media.GIB)):
            raise self.Problem('There is not enough space for this download and its tagged library copy.')
        self.save('music_choices', token, user['id'], 'submitting', data, created)
        try:
            result = api.call('/release', {'guid':release['guid'], 'indexerId':release['indexerId'], 'albumId':album['id']})
            data['downloadId'] = (result or {}).get('downloadId') or (result or {}).get('infoHash') or release.get('infoHash')
        except Exception:
            self.save('music_choices', token, user['id'], 'uncertain', data, created)
            raise self.Problem('Submission could not be confirmed. Check Lidarr or Music downloads; it will not be retried automatically.') from None
        self.save('music_choices', token, user['id'], 'submitted', data, created)
        return {'message':'Selected release sent to qBittorrent. Follow it in Requests; your chosen album will be used for automatic import, tags and artwork.'}

    def files(self, album_id):
        files = self.api().call('/trackfile?'+urlencode({'albumId':album_id}))
        for file in files:
            self.safe_path(file['path'])
        return files

    def reconcile(self):
        # A timed-out grab may have succeeded. Recover only an exact album/title
        # match recorded after this submission; never submit a replacement here.
        for token, owner, created, state, raw in self.db.execute("SELECT id,owner,created,state,data FROM music_choices WHERE state IN ('submitted','uncertain')").fetchall():
            data = json.loads(raw)
            if state == 'submitted' and self.torrent_hash(data.get('downloadId')):
                continue
            history = self.b.removal.pages(self.api(), '/history?'+urlencode({'albumId':data['albumId']}))
            matches = set()
            for row in history:
                if (row.get('albumId') != data['albumId'] or row.get('eventType') != 'grabbed'
                        or row.get('sourceTitle') != data['release']['title']):
                    continue
                try:
                    recent = datetime.fromisoformat(row['date'].replace('Z', '+00:00')).timestamp() >= created-5
                except (KeyError, ValueError, TypeError):
                    continue
                download = self.torrent_hash(row.get('downloadId'))
                if recent and download:
                    matches.add(download)
            if len(matches) == 1:
                data['downloadId'] = matches.pop()
                self.save('music_choices', token, owner, 'submitted', data, created)

    def process(self):
        """Finish confirmed music downloads without depending on release-name parsing."""
        if 'lidarr' not in self.b.cfg['enabled']:
            return
        self.reconcile()
        selections = self.db.execute("SELECT id,owner,created,data FROM music_choices WHERE state='submitted'").fetchall()
        pending = [(token, owner, created, json.loads(raw)) for token, owner, created, raw in selections
                   if json.loads(raw).get('import', {}).get('phase') != 'done']
        if not pending:
            return
        api = self.api(); api.timeout = 30
        torrents = {self.torrent_hash(t['hash']): t for t in self.b.removal.qbit().call('/torrents/info')}
        blocked = {json.loads(raw)['albumId'] for (raw,) in self.db.execute("SELECT data FROM music_removals WHERE state IN ('removing','failed')")}
        for token, owner, created, data in pending:
            if data['albumId'] in blocked or data.get('import', {}).get('retryAt', 0) > time.time():
                continue
            try:
                self.import_selected(api, data, torrents,
                                     lambda: self.save('music_choices', token, owner, 'submitted', data, created))
            except Exception as error:
                progress = data.setdefault('import', {})
                progress['message'] = str(error) if isinstance(error, self.Problem) else 'Import service is temporarily unavailable; it will retry automatically.'
                progress['retryAt'] = time.time()+60
            self.save('music_choices', token, owner, 'submitted', data, created)

    def import_selected(self, api, data, torrents, persist):
        progress = data.setdefault('import', {})
        album = api.call('/album/'+str(data['albumId']))
        if album['foreignAlbumId'] != data['mbid']:
            raise self.Problem('The selected album changed; import is stopped.')
        artist = api.call('/artist/'+str(album['artistId']))
        self.safe_path(artist['path'])
        tracks = api.call('/track?'+urlencode({'albumId':album['id']}))
        owned = {t['id'] for t in tracks if t.get('hasFile') or t.get('trackFileId')}
        expected = set(progress.get('trackIds', []))
        if expected and expected <= owned:
            progress.update(phase='done', message='Imported; waiting for Jellyfin library discovery.')
            progress.pop('commandId', None); progress.pop('files', None)
            self.b.media_jellyfin_admin().call('/Library/Refresh', method='POST')
            return
        # Resolve a POST whose response was lost, without submitting a second import.
        if progress.get('phase') == 'submitting':
            commands = api.call('/command')
            def identity(files):
                return sorted((f.get('path', ''), f.get('artistId'), f.get('albumId'), f.get('albumReleaseId'),
                               tuple(sorted(f.get('trackIds') or []))) for f in files or [])
            match = next((c for c in commands if identity((c.get('body') or {}).get('files')) == identity(progress.get('files'))
                          and c.get('name', '').lower() == 'manualimport'), None)
            if not match:
                progress['message'] = 'Checking the previous import submission; no duplicate import will be started.'
                return
            progress.update(commandId=match['id'], phase='queued')
        if progress.get('commandId'):
            command = api.call('/command/'+str(progress['commandId']))
            if command.get('status') in ('queued', 'started'):
                progress['message'] = 'Importing into your selected album…'
                return
            progress.pop('commandId', None)
            progress.update(phase='retry', retryAt=time.time()+60,
                            message='Checking imported tracks before retrying any missing files.')
            return
        download = self.torrent_hash(data.get('downloadId')) or self.torrent_hash(data['release'].get('infoHash'))
        transfer = torrents.get(download)
        if not transfer:
            progress['message'] = 'Waiting for the selected download to appear in qBittorrent.'
            return
        if transfer.get('category') != 'music':
            raise self.Problem('The download category changed; import is stopped.')
        if (transfer.get('progress', 0) < 1 or transfer.get('amount_left', 1) != 0
                or transfer.get('state') in ('checkingDL', 'checkingUP', 'checkingResumeData', 'moving', 'error', 'missingFiles')):
            progress['message'] = 'Waiting for the download to finish.'
            return
        folder = Path(self.download_path(transfer.get('content_path')))
        if not folder.exists():
            raise self.Problem('Waiting for the completed download files to become available.')
        def source_path(value):
            path = Path(self.download_path(value))
            if (path != folder and folder not in path.parents) or not path.is_file():
                raise self.Problem('An import file is outside the selected download; import is stopped.')
            return str(path)
        rows = api.call('/manualimport?'+urlencode({'folder':str(folder), 'artistId':album['artistId'],
                                                   'filterExistingFiles':'false', 'replaceExistingFiles':'false'}))
        audio = [r for r in rows if not r.get('additionalFile')]
        if not audio:
            raise self.Problem('Waiting for readable audio files in the completed download.')
        updates = []
        for row in audio:
            updates.append({'id':row['id'], 'path':source_path(row['path']), 'name':row.get('name'),
                'artistId':album['artistId'], 'albumId':album['id'], 'quality':row.get('quality'),
                'releaseGroup':row.get('releaseGroup'), 'indexerFlags':row.get('indexerFlags', 0),
                'replaceExistingFiles':False, 'disableReleaseSwitching':False})
        # Album/artist identity comes from the user's confirmation, not folder names.
        mapped = api.call('/manualimport', updates)
        allowed_paths = {r['path'] for r in updates}
        releases = {r['id'] for r in api.call('/album/'+str(album['id'])).get('releases', [])}
        valid_tracks = set()
        for release_id in {r.get('albumReleaseId') for r in mapped} & releases:
            valid_tracks.update(t['id'] for t in api.call('/track?'+urlencode({'albumReleaseId':release_id})) if t['albumId'] == album['id'])
        files, all_ids, seen_paths, seen_tracks = [], set(), set(), set()
        for row in mapped:
            if row.get('path') not in allowed_paths:
                continue  # Lidarr may include existing library tracks in the comparison.
            path = source_path(row['path']); ids = {t['id'] for t in row.get('tracks', [])}
            if (not ids or not ids <= valid_tracks or (row.get('album') or {}).get('id') != album['id']
                    or (row.get('artist') or {}).get('id') != album['artistId'] or row.get('albumReleaseId') not in releases):
                raise self.Problem('Album selected; waiting for its track metadata to match the audio files.')
            if seen_tracks & ids or path in seen_paths:
                raise self.Problem('Multiple files map to the same track; import needs review in Lidarr.')
            seen_paths.add(path); seen_tracks.update(ids); all_ids.update(ids)
            if ids <= owned:
                continue
            if ids & owned:
                raise self.Problem('A combined track file overlaps existing tracks; import needs review in Lidarr.')
            files.append({'path':path, 'artistId':album['artistId'], 'albumId':album['id'],
                'albumReleaseId':row['albumReleaseId'], 'trackIds':sorted(ids), 'quality':row['quality'],
                'releaseGroup':row.get('releaseGroup'), 'indexerFlags':row.get('indexerFlags', 0),
                # Use a path-based copy import after validating the exact torrent
                # above. Lidarr's queue can outlive its in-memory tracked download;
                # attaching that ID makes ManualImport dereference a missing entry.
                'downloadId':None, 'disableReleaseSwitching':False})
        if seen_paths != allowed_paths:
            raise self.Problem('Waiting for all downloaded audio files to be identified within the selected album.')
        progress['trackIds'] = sorted(all_ids)
        if not files:
            progress.update(phase='done', message='Imported; waiting for Jellyfin library discovery.')
            progress.pop('commandId', None); progress.pop('files', None)
            self.b.media_jellyfin_admin().call('/Library/Refresh', method='POST')
            return
        if len({f['albumReleaseId'] for f in files}) != 1:
            raise self.Problem('Track metadata spans multiple album editions; import needs review in Lidarr.')
        management = api.call('/config/mediamanagement')
        if management.get('copyUsingHardlinks'):
            raise self.Problem('Disable music hardlinks before import so tagging preserves the download.')
        # Persist the exact command before the side effect. Copy mode preserves
        # seeding data, and replaceExistingFiles=false protects library tracks.
        progress.update(phase='submitting', files=files, message='Importing into your selected album…')
        persist()
        command = api.call('/command', {'name':'ManualImport', 'files':files, 'importMode':'copy', 'replaceExistingFiles':False})
        progress.update(phase='queued', commandId=command['id'])
        persist()

    def status(self, user, jelly, admin):
        self.reconcile()
        api = self.api(); api.timeout = 15
        queue = self.b.removal.pages(api, '/queue')
        albums = {a['id']:a for a in api.call('/album')}
        try:
            torrents = {self.torrent_hash(t['hash']):t for t in self.b.removal.qbit().call('/torrents/info')}
        except Exception:
            torrents = {}
        visible, start = {}, 0
        while True:
            result = jelly.call('/Items?'+urlencode({'userId':user['jellyfinUserId'], 'recursive':'true', 'includeItemTypes':'MusicAlbum',
                                                    'fields':'ProviderIds', 'startIndex':start, 'limit':200}))
            for item in result.get('Items', []):
                mid = (item.get('ProviderIds') or {}).get('MusicBrainzReleaseGroup')
                if mid:
                    visible[mid] = item['Id']
            start += len(result.get('Items', []))
            if not result.get('Items') or start >= result.get('TotalRecordCount', start):
                break
        rows = []
        imported = {}
        for token, state, raw in self.db.execute("SELECT id,state,data FROM music_choices WHERE owner=? AND state != 'preview' ORDER BY created DESC LIMIT 40", (user['id'],)):
            data = json.loads(raw)
            if state == 'removed':
                continue
            album = albums.get(data['albumId'], {}); stats = album.get('statistics') or {}
            tasks = [q for q in queue if q.get('albumId') == data['albumId']]
            count = stats.get('trackFileCount', 0); item = visible.get(data['mbid']) if count else None
            if count and data['albumId'] not in imported:
                audio = set()
                for file in api.call('/trackfile?'+urlencode({'albumId':data['albumId']})):
                    info = file.get('mediaInfo') or {}
                    details = [str(info[k]) for k in ('audioCodec', 'audioBitRate') if info.get(k)]
                    audio.add(' · '.join([self.quality(file), *details]))
                imported[data['albumId']] = audio
            message = 'Ready to listen.' if item else 'Waiting for import and Jellyfin library discovery.'
            percent = None
            if tasks:
                task = tasks[0]; size = task.get('size') or 0
                left = task.get('sizeleft', size)
                percent = min(99.9, round(100*(1-left/size), 1)) if size and 0 < left <= size else None
                message = 'Import needs attention in Lidarr.' if task.get('trackedDownloadState') == 'importPending' or task.get('trackedDownloadStatus') in ('warning','error') else str(task.get('status') or 'Downloading')
            if state == 'uncertain':
                message = 'Submission outcome uncertain. Check Lidarr before trying again.'
            transfer = torrents.get(self.torrent_hash(data.get('downloadId')) or self.torrent_hash(data['release'].get('infoHash')))
            if transfer and not item:
                fraction = transfer.get('progress', 0)
                percent = min(99.9, round(100*fraction, 1)) if 0 <= fraction < 1 else None
                if fraction < 1:
                    message = 'Downloading your selected album.'
                    if transfer.get('state') in ('metaDL', 'forcedMetaDL'):
                        percent = None
                        message = 'Waiting for torrent metadata from peers. Try another release if this stays stuck.'
                    elif transfer.get('state') == 'stalledDL':
                        message = 'Waiting for peers to send the selected album.'
                    elif transfer.get('state') in ('stoppedDL', 'pausedDL'):
                        message = 'Download is paused.'
                    elif transfer.get('state') == 'queuedDL':
                        message = 'Queued behind another download.'
                    elif transfer.get('state') in ('error', 'missingFiles'):
                        percent = None
                        message = 'The downloader needs attention. Check qBittorrent.'
                else:
                    message = data.get('import', {}).get('message') or 'Download complete; preparing automatic import.'
            elif not item and data.get('import', {}).get('message'):
                message = data['import']['message']
            if item:
                percent = None
                message = 'Ready to listen.'
            rows.append({'id':token, 'albumId':data['mbid'], 'title':data['title'], 'artist':data['artist'], 'state':state,
                         'message':message, 'percent':percent, 'importedTracks':count, 'itemId':item,
                         'downloadComplete':bool(item or data.get('import', {}).get('phase') == 'done'
                                                 or (transfer and transfer.get('progress', 0) >= 1)),
                         'canChooseAlternative':bool(admin and state == 'submitted' and not count and transfer
                                                     and transfer.get('progress', 0) < 1),
                         'quality':self.quality(data['release']), 'audio':sorted(imported.get(data['albumId'], []))})
        library = [self.summary(a) for a in albums.values()] if admin else []
        return {'selections':rows, 'canRemove':admin, 'albums':library}

    def removal_snapshot(self, mid):
        self.reconcile()
        api = self.api(); mid = self.identifier(mid)
        albums = api.call('/album?'+urlencode({'foreignAlbumId':mid}))
        if not albums:
            raise self.Problem('Album is no longer in Lidarr.', 404)
        album = albums[0]; artist = api.call('/artist/'+str(album['artistId'])); self.safe_path(artist['path'])
        for (raw,) in self.db.execute("SELECT data FROM music_choices WHERE state='submitted'"):
            choice = json.loads(raw)
            if choice['albumId'] != album['id']:
                continue
            progress = choice.get('import', {})
            if progress.get('phase') == 'submitting' or (progress.get('commandId') and
                    api.call('/command/'+str(progress['commandId'])).get('status') in ('queued','started')):
                raise self.Problem('This album is being imported. Wait for import to finish before removing it.')
        files = sorted((f['id'], self.safe_path(f['path'])) for f in self.files(album['id']))
        # History binds download IDs to an album even after its queue entry disappears.
        history = self.b.removal.pages(api, '/history?'+urlencode({'albumId':album['id']}))
        hashes = {self.torrent_hash(h.get('downloadId')) for h in history if h.get('albumId') == album['id']}
        queue = self.b.removal.pages(api, '/queue')
        hashes.update(self.torrent_hash(q.get('downloadId')) for q in queue if q.get('albumId') == album['id'])
        for state, raw in self.db.execute("SELECT state,data FROM music_choices WHERE state IN ('submitted','uncertain')"):
            choice = json.loads(raw)
            if choice['albumId'] != album['id']:
                continue
            known = self.torrent_hash(choice.get('downloadId')) or self.torrent_hash(choice['release'].get('infoHash'))
            hashes.add(known)
            if state == 'uncertain' and not known:
                raise self.Problem('An uncertain submission cannot be matched safely; administrator recovery is required.')
        hashes.discard(None)
        q = self.b.removal.qbit(); torrents = [t for t in q.call('/torrents/info') if t['hash'].lower() in hashes]
        downloads = []
        for torrent in torrents:
            if torrent.get('category') != 'music':
                raise self.Problem('Album transfer has an unexpected category.')
            linked = self.b.removal.pages(api, '/history?'+urlencode({'downloadId':torrent['hash']}))
            if any(h.get('albumId') not in (None, album['id']) for h in linked):
                raise self.Problem('This torrent includes other albums; manage it in Lidarr.')
            if any(q.get('albumId') != album['id'] and q.get('downloadId', '').lower() == torrent['hash'].lower() for q in queue):
                raise self.Problem('Another album shares this transfer; manage it in Lidarr.')
            path = self.removal_download_path(torrent, q)
            downloads.append({'hash':torrent['hash'], 'path':path})
        return {'albumId':album['id'], 'mbid':mid, 'title':album['title'], 'files':files, 'downloads':downloads}

    def removal_preview(self, user, body):
        mid = self.identifier(body.get('id'))
        self.db.execute("DELETE FROM music_removals WHERE state='preview' AND created < ?", (time.time()-300,))
        for token, raw in self.db.execute("SELECT id,data FROM music_removals WHERE owner=? AND state IN ('failed','removing')", (user['id'],)):
            data = json.loads(raw)
            if data['mbid'] == mid:
                return {'id':token, 'title':data['title'], 'files':len(data['files']), 'downloads':len(data['downloads']), 'retry':True}
        data = self.removal_snapshot(mid); token = secrets.token_urlsafe(24)
        self.save('music_removals', token, user['id'], 'preview', data)
        return {'id':token, 'title':data['title'], 'files':len(data['files']), 'downloads':len(data['downloads'])}

    def remove(self, user, body):
        token = body.get('id'); created, state, data = self.choice('music_removals', token, user)
        if state == 'complete':
            return {'message':'Album was already removed.'}
        if state == 'preview':
            current = self.removal_snapshot(data['mbid'])
            if time.time()-created > 300 or json.dumps(current, sort_keys=True) != json.dumps(data, sort_keys=True):
                raise self.Problem('Album or downloads changed. Open the removal confirmation again.')
        elif state not in ('failed','removing'):
            raise self.Problem('Invalid removal state.')
        self.save('music_removals', token, user['id'], 'removing', data, created)
        try:
            q = self.b.removal.qbit()
            api = self.api()
            for download in data['downloads']:
                torrents = q.call('/torrents/info')
                current = next((t for t in torrents if t['hash'] == download['hash']), None)
                if not current:
                    continue
                if current.get('category') != 'music' or self.removal_download_path(current, q) != download['path']:
                    raise self.Problem('Torrent changed; removal stopped.')
                path = Path(download['path']).resolve() if download['path'] else None
                for torrent in torrents:
                    other = torrent.get('content_path')
                    if torrent['hash'] == download['hash'] or not other or path is None:
                        continue
                    other = Path(other).resolve()
                    if path == other or path in other.parents or other in path.parents:
                        raise self.Problem('Another torrent shares this location; manage it in Lidarr.')
                history = self.b.removal.pages(api, '/history?'+urlencode({'downloadId':download['hash']}))
                queue = self.b.removal.pages(api, '/queue')
                if (any(h.get('albumId') not in (None, data['albumId']) for h in history)
                        or any(x.get('albumId') != data['albumId'] and (x.get('downloadId') or '').lower() == download['hash'].lower() for x in queue)):
                    raise self.Problem('Another album shares this transfer; manage it in Lidarr.')
                q.call('/torrents/delete', {'hashes':download['hash'], 'deleteFiles':'true' if path else 'false'}, form=True)
                for _ in range(15):
                    if not any(t['hash'] == download['hash'] for t in q.call('/torrents/info')):
                        break
                    time.sleep(.2)
                else:
                    raise self.Problem('Torrent removal is still pending. Retry removal shortly.')
            remaining = api.call('/album?'+urlencode({'foreignAlbumId':data['mbid']}))
            if remaining:
                current_files = {(f['id'], self.safe_path(f['path'])) for f in self.files(data['albumId'])}
                if not current_files.issubset({tuple(f) for f in data['files']}):
                    raise self.Problem('New tracks arrived; removal stopped. Inspect the album in Lidarr.')
                api.call('/album/'+str(data['albumId'])+'?deleteFiles=true&addImportListExclusion=true', method='DELETE')
            for choice, owner, stamp, raw in self.db.execute('SELECT id,owner,created,data FROM music_choices').fetchall():
                if json.loads(raw)['albumId'] == data['albumId']:
                    self.db.execute("UPDATE music_choices SET state='removed' WHERE id=?", (choice,))
            self.b.media_jellyfin_admin().call('/Library/Refresh', method='POST')
        except Exception:
            self.save('music_removals', token, user['id'], 'failed', data, created)
            raise
        self.save('music_removals', token, user['id'], 'complete', data, created)
        return {'message':'Album and its matched downloads removed. Jellyfin is refreshing.'}

    def handle(self, user, headers, action, body):
        jelly, admin = self.account(user, headers)
        if action in ('music-removal-preview','music-remove') and not admin:
            raise self.Problem('Only an administrator can remove shared music.', 403)
        if action == 'music-search': return self.search(body)
        if action == 'music-artist': return self.artist(body)
        if action == 'music-album': return self.detail(body)
        if action == 'music-releases': return self.releases(user, body)
        if action == 'music-select': return self.select(user, body)
        if action == 'music-status': return self.status(user, jelly, admin)
        if action == 'music-removal-preview': return self.removal_preview(user, body)
        if action == 'music-remove': return self.remove(user, body)
        raise self.Problem('Unknown music action.', 404)
