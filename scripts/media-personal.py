"""Per-user movie/series discovery and Jellyfin favorite synchronization; never creates requests."""
import hashlib
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlencode

next_up_spec = importlib.util.spec_from_file_location('media_next_up', Path(__file__).with_name('media-next-up.py'))
next_up_module = importlib.util.module_from_spec(next_up_spec)
next_up_spec.loader.exec_module(next_up_module)


def media_key(mid, kind="movie"):
    if kind not in ("movie", "tv") or type(mid) is not int or mid < 1:
        raise ValueError("Invalid media identifier")
    return f"{kind}:{mid}"


def movie(raw, kind="movie"):
    genres = raw.get('genreIds', raw.get('genre_ids', []))
    if raw.get('genres'):
        genres = [g['id'] for g in raw['genres']]
    return {'id': int(raw['id']), 'mediaType': kind, 'title': raw.get('title') or raw.get('name') or 'Untitled',
            'poster': raw.get('posterPath', raw.get('poster_path')), 'genres': genres,
            'adult': bool(raw.get('adult')), 'year': (raw.get('releaseDate', raw.get('release_date')) or raw.get('firstAirDate', raw.get('first_air_date')) or '')[:4],
            'status': (raw.get('mediaInfo') or {}).get('status', 1)}


def restricted(policy):
    # External metadata cannot prove folder/tag/rating eligibility. In these
    # accounts, recommendations are limited to Jellyfin's own visible movies.
    return (policy.get('MaxParentalRating') is not None or not policy.get('EnableAllFolders', True)
            or bool(policy.get('BlockedTags') or policy.get('AllowedTags') or policy.get('BlockUnratedItems')))


def seeds(profile, limit):
    eligible = [r for r in profile.values() if not r.get('dismissed')]
    favorites = sorted([r for r in eligible if r.get('favorite')], key=lambda r: r.get('favoritedAt', 0), reverse=True)[:5]
    watched = sorted([r for r in eligible if r.get('watched') or r.get('externalWatched')], key=lambda r: r.get('playedAt', 0), reverse=True)[:30]
    chosen = watched[:max(0, limit-min(len(favorites), max(1, limit//5)))]
    for row in favorites + watched:
        if row not in chosen and len(chosen) < limit:
            chosen.append(row)
    result = []
    for row in chosen:
        if row.get('watched') or row.get('externalWatched'):
            weight, reason = 1.5, 'watched'
        else:
            weight, reason = 0.35, 'favorited'
        result.append((row, weight, f"Because you {reason} {row['movie']['title']}"))
    return result


def rank(candidates, profile, count):
    excluded = {k for k, r in profile.items() if any(r.get(flag) for flag in ('watched', 'externalWatched', 'dismissed', 'favorite'))}
    remaining = {mid: row for mid, row in candidates.items() if mid not in excluded and not row['movie'].get('adult')}
    result, genres = [], {}
    while remaining and len(result) < count:
        def score(pair):
            mid, row = pair
            penalty = sum(genres.get(g, 0) for g in row['movie'].get('genres', []))
            return row['score']/(1+0.3*penalty), -row['movie']['id'], row['movie'].get('mediaType', 'movie')
        mid, row = max(remaining.items(), key=score)
        remaining.pop(mid)
        result.append({**row['movie'], 'reason': row['reason']})
        for genre in row['movie'].get('genres', []):
            genres[genre] = genres.get(genre, 0)+1
    return result


class Personal:
    def __init__(self, broker, media, problem):
        self.broker, self.media, self.Problem = broker, media, problem
        self.cfg = broker.cfg
        self.lock = threading.RLock()
        database = Path(self.cfg['stateDir'])/'personal.sqlite'
        existed = database.exists()
        self.db = sqlite3.connect(database, check_same_thread=False)
        if existed and self.db.execute('PRAGMA user_version').fetchone()[0] < 3:
            backup = database.with_name('personal.before-favorites-v3.sqlite')
            if not backup.exists():
                fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                try:
                    with closing(sqlite3.connect(backup)) as target:
                        self.db.backup(target)
                except Exception:
                    backup.unlink()
                    raise
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS entries(owner TEXT, media_key TEXT, data TEXT, PRIMARY KEY(owner,media_key));
            CREATE TABLE IF NOT EXISTS recommendations(owner TEXT PRIMARY KEY, generated REAL, data TEXT);
            CREATE TABLE IF NOT EXISTS catalogue_v2(media_key TEXT PRIMARY KEY, fetched REAL, data TEXT);
        ''')
        # Keep the old table untouched for rollback. Migrate only once so removed
        # favorites cannot be resurrected on subsequent service restarts.
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 2:
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='movies'").fetchone():
                for owner, mid, raw in self.db.execute('SELECT owner,tmdb,data FROM movies').fetchall():
                    row = json.loads(raw)
                    row['movie']['mediaType'] = 'movie'
                    if row.pop('seed', False):
                        row.update(favorite=True, favoritePending=True)
                    self.put(owner, media_key(mid), row)
            self.db.execute('DELETE FROM recommendations')
            self.db.execute('PRAGMA user_version=2')
            self.db.commit()
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 3:
            with self.db:
                for owner, key, raw in self.db.execute('SELECT owner,media_key,data FROM entries').fetchall():
                    row = json.loads(raw)
                    if row.pop('saved', False):
                        row.update(favorite=True, favoritePending=True, dismissed=False)
                        row.setdefault('favoritedAt', row.get('savedAt', 0))
                    row.pop('savedAt', None)
                    self.put(owner, key, row)
                self.db.execute('DELETE FROM recommendations')
                self.db.execute('PRAGMA user_version=3')
        self.jobs, self.attempted = {}, {}
        self.wake = threading.Event()
        self.next_up = next_up_module.NextUp(self)

    def profile(self, owner):
        with self.lock:
            return {mid: json.loads(data) for mid, data in self.db.execute('SELECT media_key,data FROM entries WHERE owner=?', (owner,))}

    def put(self, owner, mid, data):
        self.db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?)', (owner, mid, json.dumps(data)))

    def visible(self, api, owner):
        def query(kind, **extra):
            start = 0
            while True:
                result = api.call('/Items?'+urlencode({'userId': owner, 'recursive': 'true', 'includeItemTypes': kind,
                    'fields': 'ProviderIds,Genres', 'enableUserData': 'true', 'startIndex': start, 'limit': 100, **extra}))
                rows = result['Items']
                yield from rows
                if len(rows) < 100:
                    break
                start += 100
        items, series = {}, {}
        for item in query('Movie,Series'):
            mid = (item.get('ProviderIds') or {}).get('Tmdb')
            if str(mid).isdigit() and int(mid) > 0:
                key = media_key(int(mid), 'tv' if item.get('Type') == 'Series' else 'movie')
                items[key] = item
                if item.get('Type') == 'Series':
                    series[item['Id']] = item
        # One signal per series, regardless of how many episodes were watched.
        if series:
            for episode in query('Episode'):
                show = series.get(episode.get('SeriesId'))
                if show is not None:
                    if (episode.get('UserData') or {}).get('Played'):
                        show['PersonalWatched'] = True
                    played = (episode.get('UserData') or {}).get('LastPlayedDate') or ''
                    show['PersonalLastPlayedDate'] = max(show.get('PersonalLastPlayedDate', ''), played)
        return items

    def snapshot(self, user, headers):
        api = self.media.API(self.cfg['ports']['jellyfin'], headers={
            k: headers[k] for k in ('Authorization', 'X-Emby-Token') if headers.get(k)})
        info = api.call('/Users/Me')
        owner = uuid.UUID(info['Id']).hex
        if info.get('Policy', {}).get('IsDisabled') or owner != uuid.UUID(user['jellyfinUserId']).hex:
            raise self.Problem('Account unavailable.', 403)
        items = self.visible(api, owner)
        self.sync(owner, items, api)
        return {'owner': owner, 'user': user, 'items': items, 'api': api, 'restricted': restricted(info.get('Policy', {}))}

    def native_favorite(self, api, owner, item, favorite):
        api.call('/UserFavoriteItems/'+item['Id']+'?'+urlencode({'userId': owner}),
                 method='POST' if favorite else 'DELETE')

    def sync(self, owner, items, api=None):
        with self.lock:
            profile = self.profile(owner)
            for key, item in items.items():
                kind, mid = key.split(':')
                row = profile.get(key, {'movie': {'id': int(mid), 'mediaType': kind, 'genres': []}})
                row['movie'].update(title=item['Name'], year=str(item.get('ProductionYear', '')))
                data = item.get('UserData') or {}
                # External favorites migrate into the native library exactly once.
                if row.get('favoritePending'):
                    if api:
                        try:
                            self.native_favorite(api, owner, item, row.get('favorite', False))
                        except Exception:
                            pass  # Retry pending synchronization; retain the user's choice.
                        else:
                            row['favoritePending'] = False
                else:
                    row['favorite'] = bool(data.get('IsFavorite'))
                was_watched = row.get('watched', False)
                row['watched'] = bool(data.get('Played') or item.get('PersonalWatched'))
                if row['watched']:
                    if not was_watched:
                        row['playedAt'] = time.time()
                    played = item.get('PersonalLastPlayedDate') or data.get('LastPlayedDate')
                    if played:
                        from datetime import datetime
                        try:
                            row['playedAt'] = datetime.fromisoformat(played.replace('Z', '+00:00')).timestamp()
                        except ValueError:
                            pass
                self.put(owner, key, row)
            self.db.commit()

    def signature(self, owner):
        return hashlib.sha256(json.dumps(self.profile(owner), sort_keys=True).encode()).hexdigest()

    def schedule(self, snapshot, force=False):
        owner = snapshot['owner']
        with self.lock:
            cached = self.db.execute('SELECT generated,data FROM recommendations WHERE owner=?', (owner,)).fetchone()
            fresh = cached and time.time()-cached[0] < self.cfg.get('recommendationRefreshHours', 24)*3600
            same = cached and json.loads(cached[1]).get('signature') == self.signature(owner)
            if force or not (fresh and same):
                if force or time.time()-self.attempted.get(owner, 0) > 300:
                    self.jobs[owner] = snapshot
                    self.wake.set()

    def decorate(self, row, snapshot, profile):
        mid = media_key(row['id'], row.get('mediaType', 'movie'))
        local = snapshot['items'].get(mid)
        if row.get('adult') or (snapshot['restricted'] and not local):
            return None
        state = profile.get(mid, {})
        return {**row, 'itemId': local['Id'] if local else None,
                'favorite': bool(state.get('favorite')), 'favoritePending': bool(state.get('favoritePending')),
                'action': ('open' if row.get('mediaType') == 'tv' else 'play') if local else ('status' if row.get('status') in (2, 3, 4, 5) else 'choose')}

    def backdrop(self, snapshot):
        # Use only this account's currently visible library and playback dates.
        candidates = [(max(item.get('PersonalLastPlayedDate') or '', (item.get('UserData') or {}).get('LastPlayedDate') or ''), item)
                      for item in snapshot['items'].values()]
        candidates = [(played, item) for played, item in candidates if played]
        if not candidates:
            return None
        _, item = max(candidates, key=lambda pair: pair[0])
        tags = item.get('BackdropImageTags') or []
        return {'itemId': item['Id'], 'tag': tags[0]} if tags else None

    def home(self, snapshot):
        owner = snapshot['owner']
        self.schedule(snapshot)
        with self.lock:
            cached = self.db.execute('SELECT generated,data FROM recommendations WHERE owner=?', (owner,)).fetchone()
            profile = self.profile(owner)
        entries = json.loads(cached[1]).get('movies', []) if cached else []
        recommendations = [self.decorate(r, snapshot, profile) for r in entries
            if not any(profile.get(media_key(r['id'], r.get('mediaType', 'movie')), {}).get(k) for k in ('watched', 'externalWatched', 'dismissed', 'favorite'))]
        return {'enabled': True, 'recommendations': [r for r in recommendations if r],
                'nextUp': self.next_up.listing(snapshot),
                'backdrop': self.backdrop(snapshot),
                'favorites': [d for r in profile.values() if r.get('favorite') and (d := self.decorate(r['movie'], snapshot, profile))],
                'generated': cached[0] if cached else None, 'building': owner in self.jobs,
                'needsSeeds': not seeds(profile, self.cfg.get('recommendationSeedLimit', 30)),
                'libraryOnly': snapshot['restricted']}

    def detail(self, mid, snapshot, kind="movie"):
        try:
            key = media_key(mid, kind)
        except ValueError:
            raise self.Problem('Invalid media identifier.', 400) from None
        local = snapshot['items'].get(key)
        if snapshot['restricted'] and not local:
            raise self.Problem('This title is outside your accessible library.', 403)
        if snapshot['restricted']:
            return self.profile(snapshot['owner'])[key]['movie']
        try:
            result = movie(self.broker.seerr(snapshot['user']['id']).call('/'+kind+'/'+str(mid)), kind)
        except Exception:
            known = self.profile(snapshot['owner']).get(key)
            if not known:
                raise self.Problem('Title details are temporarily unavailable. Try again later.', 502) from None
            result = known['movie']
        if result.get('adult'):
            raise self.Problem('This title is not available for personal discovery.', 403)
        return result

    def feedback(self, snapshot, body):
        action, mid, owner = body.get('action'), body.get('mediaId'), snapshot['owner']
        kind = body.get('mediaType', 'movie')
        if kind not in ('movie', 'tv') or type(mid) is not int or mid < 1 or action not in ('dismiss', 'watched', 'favorite', 'unfavorite'):
            raise self.Problem('Invalid list action.', 400)
        key = media_key(mid, kind)
        detail = self.detail(mid, snapshot, kind) if action != 'unfavorite' else None
        with self.lock:
            row = self.profile(owner).get(key, {'movie': detail})
            if detail:
                row['movie'] = detail
            if not row['movie']:
                raise self.Problem('Movie not found in your list.', 404)
            if action == 'dismiss':
                row.update(dismissed=True)
            elif action == 'watched':
                row.update(externalWatched=True, playedAt=time.time())
            else:
                row.update(favorite=action == 'favorite', favoritePending=True, favoritedAt=time.time())
                if row['favorite']:
                    row['dismissed'] = False
                local = snapshot['items'].get(key)
                if local and snapshot.get('api'):
                    self.native_favorite(snapshot['api'], owner, local, row['favorite'])
                    row['favoritePending'] = False
            self.put(owner, key, row)
            self.db.commit()
        self.schedule(snapshot, force=True)
        return {'message': 'Your preferences were updated.'}

    def build(self, snapshot):
        owner = snapshot['owner']
        profile = self.profile(owner)
        selected = seeds(profile, self.cfg.get('recommendationSeedLimit', 30))
        candidates, successes = {}, 0
        for seed, weight, reason in selected:
            mid = seed['movie']['id']
            kind = seed['movie'].get('mediaType', 'movie')
            key = media_key(mid, kind)
            if snapshot['restricted']:
                # Jellyfin has already applied the account's access restrictions.
                origin = snapshot['items'].get(key, {})
                rows = []
                for target, item in snapshot['items'].items():
                    if set(origin.get('Genres', [])) & set(item.get('Genres', [])):
                        rows.append(profile[target]['movie'])
                successes += 1
            else:
                with self.lock:
                    cache = self.db.execute('SELECT fetched,data FROM catalogue_v2 WHERE media_key=?', (key,)).fetchone()
                try:
                    if cache and time.time()-cache[0] < 86400:
                        rows = json.loads(cache[1])
                    else:
                        response = self.broker.seerr(snapshot['user']['id']).call(f'/{kind}/{mid}/recommendations?page=1')
                        rows = [movie(r, kind) for r in response['results'] if not r.get('adult')]
                        with self.lock:
                            self.db.execute('INSERT OR REPLACE INTO catalogue_v2 VALUES (?,?,?)', (key, time.time(), json.dumps(rows)))
                            self.db.commit()
                    successes += 1
                except Exception:
                    if not cache:
                        continue
                    rows = json.loads(cache[1])
            for index, row in enumerate(rows):
                score = weight/(1+index*0.1)
                entry = candidates.setdefault(media_key(row['id'], row.get('mediaType', 'movie')), {'movie': row, 'score': 0, 'best': 0, 'reason': reason})
                entry['score'] += score
                if score > entry['best']:
                    entry.update(best=score, reason=reason)
        if selected and not successes and not candidates:
            return  # Preserve the last successful row during a provider outage.
        result = rank(candidates, profile, self.cfg.get('recommendationCount', 20))
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO recommendations VALUES (?,?,?)',
                            (owner, time.time(), json.dumps({'movies': result, 'signature': hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()})))
            self.db.commit()

    def scan_users(self):
        api = self.media.API(self.cfg['ports']['jellyfin'], headers={
            'Authorization': 'MediaBrowser Client="Personal discovery", Device="Server", DeviceId="personal-discovery", Version="1"'})
        creds = self.broker.creds()['jellyfin']
        login = api.call('/Users/AuthenticateByName', {'Username': 'admin', 'Pw': creds['password']})
        api.headers['Authorization'] += ', Token="'+login['AccessToken']+'"'
        users = {uuid.UUID(u['Id']).hex: u for u in api.call('/Users') if not u.get('Policy', {}).get('IsDisabled')}
        offset = 0
        while True:
            linked = self.broker.seerr().call(f'/user?take=100&skip={offset}')['results']
            for user in linked:
                try:
                    owner = uuid.UUID(user.get('jellyfinUserId', '')).hex
                except (ValueError, TypeError, AttributeError):
                    continue
                if owner not in users:
                    continue
                items = self.visible(api, owner)
                self.sync(owner, items, api)
                self.schedule({'owner': owner, 'user': user, 'items': items, 'restricted': restricted(users[owner].get('Policy', {}))})
            if len(linked) < 100:
                break
            offset += 100

    def run(self):
        last_scan = 0
        while True:
            try:
                if time.time()-last_scan > 300:
                    last_scan = time.time()
                    self.scan_users()
                with self.lock:
                    job = self.jobs.pop(next(iter(self.jobs))) if self.jobs else None
                if job:
                    self.attempted[job['owner']] = time.time()
                    self.build(job)
                    continue
            except Exception:
                pass  # Provider/network errors leave the existing cache intact.
            self.wake.wait(30)
            self.wake.clear()
