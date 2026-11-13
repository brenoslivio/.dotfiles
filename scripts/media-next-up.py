"""Conservative, user-owned episode progression, independent of Jellyfin's Next Up history."""
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode


class NextUp:
    def __init__(self, personal):
        self.p, self.b = personal, personal.broker
        self.db, self.lock = personal.db, personal.lock
        self.previous, self.catalogue_cache, self.series_cache = {}, {}, {}
        self.session_starts = {}
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS next_up_plans(owner TEXT, series INTEGER, season INTEGER,
                cursor INTEGER, stopped INTEGER DEFAULT 0, updated REAL, PRIMARY KEY(owner,series));
            CREATE TABLE IF NOT EXISTS next_up_watches(owner TEXT, series INTEGER, season INTEGER,
                episode INTEGER, seconds REAL DEFAULT 0, completed INTEGER DEFAULT 0, position REAL DEFAULT 0,
                PRIMARY KEY(owner,series,season,episode));
        ''')
        self.db.commit()

    def observe(self, sessions, resolve_series, now=None, resolve_item=None):
        """Sample server sessions; seeks, pauses, idle gaps and previews do not earn viewing time."""
        now = time.monotonic() if now is None else now
        current, credited = {}, set()
        for session in sessions:
            item, play = session.get('NowPlayingItem') or {}, session.get('PlayState') or {}
            if item.get('Type') != 'Episode' or not session.get('UserId') or not item.get('SeriesId'):
                continue
            season, episode = item.get('ParentIndexNumber'), item.get('IndexNumber')
            if type(season) is not int or season < 1 or type(episode) is not int or episode < 1:
                continue
            owner = uuid.UUID(session['UserId']).hex
            position = max(0, float(play.get('PositionTicks') or 0)/10_000_000)
            duration = float(item.get('RunTimeTicks') or 0)/10_000_000
            key = (session['Id'], owner, item['Id'])
            prior = self.previous.get(key)
            paused = bool(play.get('IsPaused'))
            current[key] = (now, position, paused)
            if resolve_item and key not in self.session_starts:
                initial = resolve_item(owner, item['Id'])
                self.session_starts[key] = (item, bool((initial.get('UserData') or {}).get('Played')))
            if not prior or paused or prior[2] or not (0 < now-prior[0] <= 15):
                continue
            elapsed, advance = now-prior[0], position-prior[1]
            if not .25*elapsed <= advance <= 2.5*elapsed+1:
                continue
            series = resolve_series(item['SeriesId'])
            mid = (series.get('ProviderIds') or {}).get('Tmdb')
            if not str(mid).isdigit() or int(mid) < 1:
                continue
            mid = int(mid)
            watch_key = (owner, mid, season, episode)
            if watch_key in credited:  # Multiple devices cannot accelerate enrollment.
                continue
            credited.add(watch_key)
            with self.lock, self.db:
                plan = self.db.execute('SELECT season,cursor,stopped FROM next_up_plans WHERE owner=? AND series=?', (owner, mid)).fetchone()
                if plan and plan[2]:
                    continue
                watched = self.db.execute('SELECT seconds,completed FROM next_up_watches WHERE owner=? AND series=? AND season=? AND episode=?', watch_key).fetchone()
                seconds = (watched[0] if watched else 0)+elapsed
                enough = seconds >= 120 or (plan is not None and plan[0] == season and duration > 0 and seconds >= min(120, duration*.9))
                completed = bool(watched and watched[1]) or (enough and duration > 0 and position >= duration*.9)
                self.db.execute('INSERT OR REPLACE INTO next_up_watches VALUES (?,?,?,?,?,?,?)', (*watch_key, seconds, int(completed), position))
                if seconds >= 120:
                    if not plan or plan[0] != season:
                        self.db.execute('INSERT OR REPLACE INTO next_up_plans VALUES (?,?,?,?,0,?)', (owner, mid, season, episode, time.time()))
                    else:
                        self.db.execute('UPDATE next_up_plans SET updated=? WHERE owner=? AND series=?', (time.time(), owner, mid))
                end = item.get('IndexNumberEnd') or episode
                if completed and type(end) is int and episode < end <= episode+20:
                    for number in range(episode+1, end+1):
                        self.db.execute('INSERT OR REPLACE INTO next_up_watches VALUES (?,?,?,?,?,?,?)', (owner, mid, season, number, seconds, 1, position))
        # A credits skip can end playback between samples. Accept a *new* watched
        # flag only for a session we observed meaningfully; never import old history.
        for key in set(self.session_starts)-set(current):
            item, was_played = self.session_starts.pop(key)
            if was_played or resolve_item is None:
                continue
            owner = key[1]
            try:
                mid = int((resolve_series(item['SeriesId']).get('ProviderIds') or {}).get('Tmdb', 0))
                watch_key = (owner, mid, item['ParentIndexNumber'], item['IndexNumber'])
                with self.lock:
                    watched = self.db.execute('SELECT seconds FROM next_up_watches WHERE owner=? AND series=? AND season=? AND episode=?', watch_key).fetchone()
                    plan = self.db.execute('SELECT stopped FROM next_up_plans WHERE owner=? AND series=?', (owner, mid)).fetchone()
                threshold = min(120, float(item.get('RunTimeTicks') or 0)/10_000_000*.9)
                if not watched or not plan or plan[0] or threshold <= 0 or watched[0] < threshold:
                    continue
                if (resolve_item(owner, item['Id']).get('UserData') or {}).get('Played'):
                    end = item.get('IndexNumberEnd') or item['IndexNumber']
                    if type(end) is int and item['IndexNumber'] <= end <= item['IndexNumber']+20:
                        with self.lock, self.db:
                            for number in range(item['IndexNumber'], end+1):
                                self.db.execute('INSERT OR REPLACE INTO next_up_watches VALUES (?,?,?,?,?,?,?)',
                                                (owner, mid, item['ParentIndexNumber'], number, watched[0], 1, 0))
            except Exception:
                pass  # Missing files/metadata cannot erase or advance the cursor.
        self.previous = current

    def run(self):
        api = None
        while True:
            try:
                if api is None:
                    api = self.b.media_jellyfin_admin()
                    api.timeout = 8
                def series(identifier):
                    cached = self.series_cache.get(identifier)
                    if cached is None or time.monotonic()-cached[0] > 300:
                        cached = (time.monotonic(), api.call('/Items/'+identifier))
                        self.series_cache[identifier] = cached
                    return cached[1]
                self.observe(api.call('/Sessions'), series, resolve_item=lambda owner, item: api.call('/Items/'+item+'?userId='+owner))
            except Exception:
                # Never infer viewing time across service failures or restarts.
                self.previous.clear(); self.session_starts.clear(); api = None
            time.sleep(5)

    def local(self, snapshot, mid):
        show = snapshot['items'].get('tv:'+str(mid))
        if not show:
            raise self.p.Problem('Series is not available to this account.', 404)
        return show

    def episodes(self, snapshot, show):
        api = snapshot.get('api')
        if api is None:
            return []
        rows, start = [], 0
        while True:
            result = api.call('/Shows/'+show['Id']+'/Episodes?'+urlencode({
                'userId': snapshot['owner'], 'fields': 'MediaSources', 'enableUserData': 'true',
                'startIndex': start, 'limit': 200}))
            batch = result.get('Items', [])
            rows.extend(batch); start += len(batch)
            if not batch or start >= result.get('TotalRecordCount', start):
                return rows

    def metadata(self, snapshot, mid, season=None):
        if snapshot['restricted']:
            return None  # Never reveal external episode metadata to restricted accounts.
        key = (snapshot['owner'], mid, season)
        with self.lock:
            cached = self.catalogue_cache.get(key)
        if cached and time.monotonic()-cached[0] < 300:
            return cached[1]
        api = self.b.seerr(snapshot['user']['id']); api.timeout = 8
        path = '/tv/'+str(mid)+(('/season/'+str(season)) if season is not None else '')
        data = api.call(path)
        with self.lock:
            self.catalogue_cache[key] = (time.monotonic(), data)
        return data

    def season_options(self, snapshot, mid):
        show = self.local(snapshot, mid)
        if snapshot['restricted']:
            return sorted({e['ParentIndexNumber'] for e in self.episodes(snapshot, show) if type(e.get('ParentIndexNumber')) is int and e['ParentIndexNumber'] > 0})
        return sorted({s['seasonNumber'] for s in self.metadata(snapshot, mid).get('seasons', []) if s.get('seasonNumber', 0) > 0})

    def row(self, snapshot, plan):
        mid, season, cursor, stopped = plan
        show = self.local(snapshot, mid)
        row = {'mediaId': mid, 'title': show['Name'], 'season': season, 'episode': cursor,
               'state': 'stopped' if stopped else 'unavailable', 'itemId': None}
        if stopped:
            return row
        local = self.episodes(snapshot, show)
        available = {}
        for ep in local:
            if ep.get('ParentIndexNumber') != season or ep.get('IsVirtualItem') or ep.get('LocationType') == 'Virtual':
                continue
            if not ep.get('MediaSources'):  # Metadata alone is not a playable file.
                continue
            start, end = ep.get('IndexNumber'), ep.get('IndexNumberEnd') or ep.get('IndexNumber')
            if type(start) is int and type(end) is int and start <= end <= start+20:
                for n in range(start, end+1):
                    available[n] = ep
        with self.lock:
            watches = self.db.execute('SELECT episode,seconds,completed,position FROM next_up_watches WHERE owner=? AND series=? AND season=?', (snapshot['owner'], mid, season)).fetchall()
            completed = {n for n, _, done, _ in watches if done}
            while cursor in completed:
                cursor += 1
            # Do not overwrite a concurrent stop/restart/season change.
            self.db.execute('UPDATE next_up_plans SET cursor=? WHERE owner=? AND series=? AND season=? AND cursor=? AND stopped=0', (cursor, snapshot['owner'], mid, season, plan[2]))
            self.db.commit()
        row['episode'] = cursor
        if any(n in available and seconds > 0 and not done and position > 0 for n, seconds, done, position in watches):
            return {**row, 'state': 'resume'}
        if cursor in available:
            return {**row, 'state': 'ready', 'itemId': available[cursor]['Id'], 'episodeTitle': available[cursor].get('Name', '')}
        metadata = self.metadata(snapshot, mid, season)
        if metadata is None:
            return {**row, 'state': 'missing', 'canChoose': False}
        episodes = {e['episodeNumber']: e for e in metadata.get('episodes', []) if e.get('episodeNumber', 0) > 0}
        if not episodes:
            return row
        if cursor <= max(episodes):
            episode = episodes.get(cursor)
            if not episode:
                return row  # An unexplained numbering gap is never skipped.
            air = episode.get('airDate') or ''
            aired = bool(air and air[:10] <= datetime.now(timezone.utc).date().isoformat())
            return {**row, 'state': 'missing' if aired else 'upcoming', 'canChoose': aired,
                    'episodeTitle': episode.get('name', ''), 'airDate': air[:10]}
        seasons = self.season_options(snapshot, mid)
        return {**row, 'state': 'complete', 'nextSeason': next((s for s in seasons if s > season), None)}

    def listing(self, snapshot):
        with self.lock:
            plans = self.db.execute('SELECT series,season,cursor,stopped FROM next_up_plans WHERE owner=? ORDER BY updated DESC', (snapshot['owner'],)).fetchall()
        rows = []
        for plan in plans:
            if 'tv:'+str(plan[0]) not in snapshot['items']:
                continue  # Preserve history without exposing removed/hidden titles.
            try:
                rows.append(self.row(snapshot, plan))
            except Exception:
                rows.append({'mediaId': plan[0], 'title': self.local(snapshot, plan[0])['Name'], 'season': plan[1], 'episode': plan[2], 'state': 'unavailable'})
        return rows

    def action(self, snapshot, body):
        mid, action = body.get('mediaId'), body.get('action')
        if type(mid) is not int or mid < 1:
            raise self.p.Problem('Invalid series.', 400)
        self.local(snapshot, mid)
        owner = snapshot['owner']
        if action == 'options':
            return {'seasons': self.season_options(snapshot, mid)}
        with self.lock:
            plan = self.db.execute('SELECT series,season,cursor,stopped FROM next_up_plans WHERE owner=? AND series=?', (owner, mid)).fetchone()
        if action == 'stop' and plan:
            with self.lock, self.db:
                self.db.execute('UPDATE next_up_plans SET stopped=1 WHERE owner=? AND series=?', (owner, mid))
        elif action in ('start', 'restart', 'next-season'):
            season = body.get('season')
            if action == 'restart':
                if not plan:
                    raise self.p.Problem('No followed season.', 404)
                season = plan[1]
            if type(season) is not int or season < 1 or season not in self.season_options(snapshot, mid):
                raise self.p.Problem('Choose an available season.', 400)
            if action == 'next-season':
                current = self.row(snapshot, plan) if plan else {}
                if current.get('state') != 'complete' or current.get('nextSeason') != season:
                    raise self.p.Problem('Season progress changed. Refresh Next Up.')
            with self.lock, self.db:
                self.db.execute('DELETE FROM next_up_watches WHERE owner=? AND series=? AND season=?', (owner, mid, season))
                self.db.execute('INSERT OR REPLACE INTO next_up_plans VALUES (?,?,?,?,0,?)', (owner, mid, season, 1, time.time()))
        else:
            raise self.p.Problem('Unknown Next Up action.', 400)
        return {'message': 'Next Up updated. No download was requested.'}
