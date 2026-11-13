/* Personal rows for the pinned Jellyfin web home and Seerr discovery cards. */
(() => {
    'use strict';
    if (window.mediaPersonalLoaded) return;
    window.mediaPersonalLoaded = true;
    const { api, element: el, playItem, every } = window.MediaPicker;
    const state = { owner: '', generation: 0, data: null, busy: false, reload: false, fetched: 0, prefs: null, prefsLoading: false, detail: '', error: '', backdrop: '', backdropGeneration: 0, backdropUrl: '' };
    const defaults = ['smalllibrarytiles', 'resume', 'resumeaudio', 'resumebook', 'livetv', 'nextup', 'latestmedia'];
    const style = el('style');
    style.textContent = `
      .mp-section{margin:1.5em 0;padding:0 max(3.3%,16px);color:inherit}
      .mp-native-next-up{display:none!important}
      .mp-heading{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.mp-heading h2{font-size:1.5em;margin:.3em 0}
      .mp-list{display:flex;gap:16px;overflow-x:auto;padding:12px 2px 18px;scroll-snap-type:x proximity}
      .mp-card{flex:0 0 172px;scroll-snap-align:start;display:flex;flex-direction:column;gap:8px;white-space:normal}
      .mp-poster{width:100%;aspect-ratio:2/3;display:flex;align-items:center;justify-content:center;background:#28313d;border-radius:8px;overflow:hidden;color:#bdc7d4}
      .mp-poster img{width:100%;height:100%;object-fit:cover}
      .mp-card h3{font-size:1em;margin:0}.mp-reason{font-size:.85em;opacity:.8;margin:0;min-height:2.5em}
      .mp-button{border:1px solid #62718a;border-radius:7px;background:#293449;color:#fff;padding:8px 10px;cursor:pointer;font:inherit}
      .mp-button:disabled{opacity:.5;cursor:default}.mp-button:focus-visible{outline:3px solid #82cfff}
      .mp-card details{font-size:.85em}.mp-card details button{display:block;margin-top:6px;width:100%}
      .mp-status{opacity:.8;font-size:.9em}
      .mp-heart[aria-pressed="true"]{color:#ff829e}.mp-heart{font-size:1.35em;line-height:1}.mp-extra{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.mp-library-save{position:fixed;right:18px;bottom:114px;z-index:10010}
      #mp-home-backdrop{position:fixed;inset:0;z-index:0;pointer-events:none;background-size:cover;background-position:center;}
      body.mp-home-background .backgroundContainer{visibility:hidden}
      body.mp-home-background .mainAnimatedPages{position:relative;z-index:1}
      body.mp-home-background .homeSectionsContainer{position:relative;z-index:1}
      @media(max-width:600px){.mp-card{flex-basis:145px}.mp-button{min-height:44px}.mp-library-save{bottom:calc(114px + env(safe-area-inset-bottom))}#mp-home-backdrop{background-position:60% center}}
    `;
    document.head.append(style);
    const currentUser = () => String(window.ApiClient?.getCurrentUserId?.() || '');
    const valid = generation => generation === state.generation && state.owner === currentUser();
    const notify = message => window.JellyfinEnhanced?.toast?.(message, 5000);
    function button(label, action) { const b = el('button', label, 'mp-button'); b.type = 'button'; b.onclick = action; return b; }
    function guardOwner(owner) { if (owner !== currentUser()) throw new Error('Account changed. Reopen this page.'); }

    async function change(mid, action, owner = state.owner, kind = 'movie') {
        guardOwner(owner);
        const result = await api('personal-action', { mediaId: mid, mediaType: kind, action });
        guardOwner(owner);
        notify(result.message); state.fetched = 0; state.reload = state.busy; await load();
        return result;
    }
    async function perform(mid, sourceButton, owner, kind = 'movie') {
        sourceButton.disabled = true;
        try {
            guardOwner(owner);
            const movie = await api('personal-movie', { mediaId: mid, mediaType: kind }); guardOwner(owner);
            const je = window.JellyfinEnhanced;
            if (movie.action === 'open') {
                location.hash = '/details?id='+movie.itemId;
            } else if (movie.action === 'play') {
                await playItem(movie.itemId, owner);
            } else if (movie.action === 'status') {
                if (!je.jellyseerrMoreInfo?.open) throw new Error('Discovery is still loading. Try again shortly.');
                await je.jellyseerrMoreInfo.open(mid, kind);
            } else if (kind === 'movie' && je.jellyseerrAPI?.shouldShowAdvanced?.() && je.jellyseerrUI?.showMovieRequestModal) {
                await je.jellyseerrUI.showMovieRequestModal(mid, movie.title, { id: mid, mediaType: 'movie' });
            } else {
                if (!je.jellyseerrAPI?.requestMedia) throw new Error('Release selection is still loading. Try again shortly.');
                await je.jellyseerrAPI.requestMedia(mid, kind);
            }
        } catch (error) { notify(error.message); }
        finally { sourceButton.disabled = false; }
    }
    function heartButton(mid, kind) {
        const owner = state.owner;
        const b = button('♡', async event => {
            event.preventDefault(); event.stopPropagation(); b.disabled = true;
            try {
                const favorite = state.data?.favorites?.some(m => m.id === mid && m.mediaType === kind);
                await change(mid, favorite ? 'unfavorite' : 'favorite', owner, kind);
            } catch (error) { notify(error.message); }
            finally { b.disabled = false; }
        });
        b.classList.add('mp-heart'); b.dataset.mpHeart = String(mid); b.dataset.mpType = kind;
        b.setAttribute('aria-label', 'Add to Favorites'); b.setAttribute('aria-pressed', 'false');
        return b;
    }
    function episodeButton(mid) {
        const owner = state.owner;
        return button('Choose episode', async () => {
            try { guardOwner(owner); await window.JellyfinEnhanced.jellyseerrAPI.requestMedia(mid, 'tv'); }
            catch (error) { notify(error.message); }
        });
    }
    function card(movie) {
        const owner = state.owner, kind = movie.mediaType || 'movie';
        const node = el('article', undefined, 'mp-card'); node.dataset.mpMovie = movie.id; node.dataset.mpType = kind;
        const image = el('div', 'No poster', 'mp-poster');
        if (/^\/[a-zA-Z0-9_.-]+$/.test(movie.poster || '')) {
            const poster = el('img'); poster.alt = movie.title; poster.loading = 'lazy';
            poster.src = 'https://image.tmdb.org/t/p/w342'+movie.poster;
            poster.onerror = () => { image.textContent = 'No poster'; };
            image.replaceChildren(poster);
        }
        const title = el('h3', movie.title+(movie.year ? ' ('+movie.year+')' : ''));
        node.append(image, title);
        if (movie.reason) node.append(el('p', movie.reason, 'mp-reason'));
        node.append(el('span', kind === 'tv' ? 'Series' : 'Movie', 'mp-status'));
        const primary = button({ play: 'Play', open: 'Open series', status: 'View status', choose: 'Choose release' }[movie.action], () => perform(movie.id, primary, owner, kind));
        node.append(primary);
        if (kind === 'tv') node.append(episodeButton(movie.id));
        node.append(heartButton(movie.id, kind));
        const more = el('details'); more.append(el('summary', 'More'));
        for (const [label, action] of [['Not interested', 'dismiss'], ['Already watched elsewhere', 'watched']]) {
            const owner = state.owner;
            const b = button(label, async () => { b.disabled = true; try { await change(movie.id, action, owner, kind); node.remove(); } catch (error) { notify(error.message); b.disabled = false; } }); more.append(b);
        }
        node.append(more); return node;
    }
    function section(id, title) {
        const node = el('section', undefined, 'mp-section'); node.id = id;
        const heading = el('div', undefined, 'mp-heading'); heading.append(el('h2', title)); node.append(heading);
        node.append(el('p', '', 'mp-status'), el('div', undefined, 'mp-list')); return node;
    }
    function homeContainer() {
        const hash = location.hash.replace(/^#!?/, '');
        if (hash && !/^\/?(?:home|index)(?:\.html)?(?:\?|$)/.test(hash)) return null;
        return [...document.querySelectorAll('.homeSectionsContainer')].find(n => !n.closest('.hide,[hidden]'));
    }
    function clearBackdrop() {
        state.backdropGeneration++;
        state.backdrop = '';
        if (state.backdropUrl) URL.revokeObjectURL(state.backdropUrl);
        state.backdropUrl = '';
        document.getElementById('mp-home-backdrop')?.remove();
        document.body.classList.remove('mp-home-background');
    }
    async function updateBackdrop() {
        const art = state.data?.backdrop;
        if (!homeContainer() || !state.owner || !art || !/^[a-f0-9-]{32,36}$/i.test(art.itemId) || !/^[a-f0-9]+$/i.test(art.tag)) {
            if (state.backdrop) clearBackdrop();
            return;
        }
        const key = state.owner+':'+art.itemId+':'+art.tag;
        if (key === state.backdrop) return;
        clearBackdrop(); state.backdrop = key;
        const generation = state.generation, request = state.backdropGeneration;
        const current = () => valid(generation) && request === state.backdropGeneration && !!homeContainer();
        let url;
        try {
            const client = window.ApiClient;
            const response = await fetch(client.getUrl('Items/'+art.itemId+'/Images/Backdrop/0', { tag: art.tag, maxWidth: 1920, quality: 85 }),
                { headers: { 'X-Emby-Token': client.accessToken() }, cache: 'no-store' });
            if (!response.ok) throw new Error('Artwork unavailable');
            const blob = await response.blob();
            if (!current()) return;
            url = URL.createObjectURL(blob);
            const image = new Image(); image.src = url; await image.decode();
            if (!current()) { URL.revokeObjectURL(url); return; }
            state.backdropUrl = url;
            const layer = el('div'); layer.id = 'mp-home-backdrop'; layer.setAttribute('aria-hidden', 'true');
            layer.style.backgroundImage = `linear-gradient(rgba(10,14,20,.72),rgba(10,14,20,.94)),url("${url}")`;
            document.body.prepend(layer); document.body.classList.add('mp-home-background');
        } catch {
            if (url) URL.revokeObjectURL(url);
            // A failed image leaves the normal background; retry after the next home refresh.
            if (current()) state.backdrop = key;
        }
    }
    function placeRows() {
        const container = homeContainer(); if (!container || !state.owner) return;
        const slots = [...container.children].filter(n => [...n.classList].some(c => /^section\d+$/.test(c)));
        const type = node => {
            const index = Number([...node.classList].find(c => /^section\d+$/.test(c)).slice(7));
            return state.prefs?.['homesection'+index] || defaults[index] || '';
        };
        const media = slots.find(n => ['smalllibrarytiles', 'librarybuttons', 'folders'].includes(type(n))) || container.querySelector('.MyMedia') || slots[0];
        const resume = slots.find(n => type(n) === 'resume' && !n.closest('.hide,[hidden]') && n.getBoundingClientRect().height > 0 && n.textContent.trim());
        let forYou = container.querySelector('#mp-for-you');
        if (!forYou) forYou = section('mp-for-you', 'For you');
        const anchor = resume || media;
        if (anchor && anchor.nextElementSibling !== forYou) anchor.after(forYou);
        else if (!forYou.isConnected) container.prepend(forYou);
        renderRow(forYou, state.data?.recommendations || [], state.data?.needsSeeds ? 'Heart movies or series in search to get started.' : 'No suggestions yet. Heart some titles or check back shortly.');
        const nativeNext = slots.find(n => type(n) === 'nextup');
        for (const slot of slots) slot.classList.toggle('mp-native-next-up', slot === nativeNext);
        let next = container.querySelector('#mp-next-up');
        if (!next) next = section('mp-next-up', 'Next Up');
        if (nativeNext && nativeNext.nextElementSibling !== next) nativeNext.after(next);
        else if (!nativeNext && forYou.nextElementSibling !== next) forYou.after(next);
        renderNextUp(next, (state.data?.nextUp || []).filter(r => !['resume', 'stopped'].includes(r.state)));
    }

    const episodeLabel = row => `S${String(row.season).padStart(2, '0')}E${String(row.episode).padStart(2, '0')}`;
    async function nextUpAction(row, action, owner, season) {
        guardOwner(owner);
        const result = await api('personal-next-up-action', {mediaId: row.mediaId, action, ...(season ? {season} : {})});
        guardOwner(owner); state.fetched = 0; state.reload = state.busy; await load(); notify(result.message);
    }
    function confirmNextUp(row, action, owner, season) {
        const title = action === 'restart' ? 'Restart season?' : action === 'stop' ? 'Stop following?' : 'Start next season?';
        const view = window.MediaPicker.dialog(title); view.panel.dataset.mpDialog = 'next-up';
        view.panel.append(el('p', action === 'restart' ? 'Reset this season to episode 1 in your Next Up list? Jellyfin watch history stays intact.' :
            action === 'stop' ? 'Hide this series from Next Up until you explicitly start or restart a season?' : `Follow season ${season}? Nothing will download automatically.`));
        const confirm = button('Confirm', async () => {
            confirm.disabled = true;
            try { await nextUpAction(row, action, owner, season); view.finish(); }
            catch (error) { view.panel.append(el('p', error.message)); confirm.disabled = false; }
        }); view.actions.append(confirm);
    }
    function nextUpCard(row) {
        const owner = state.owner, node = el('article', undefined, 'mp-card'); node.dataset.mpNext = row.mediaId;
        node.append(el('h3', row.title), el('p', episodeLabel(row)+(row.episodeTitle ? ' — '+row.episodeTitle : '')));
        const messages = {ready: 'Ready to watch', resume: 'Resume your unfinished episode in Continue Watching.',
            missing: 'This episode is not downloaded.', upcoming: 'Not aired yet'+(row.airDate ? ' · '+row.airDate : ''),
            complete: 'Season complete', stopped: 'Following stopped', unavailable: 'Episode information is temporarily unavailable.'};
        node.append(el('p', messages[row.state] || '', 'mp-status'));
        if (row.state === 'ready' && row.itemId) node.append(button('Play episode', async () => {
            try {
                await playItem(row.itemId, owner);
            } catch (error) { notify(error.message); }
        }));
        if (row.state === 'missing' && row.canChoose) node.append(button('Choose release', async () => {
            try {
                guardOwner(owner);
                await window.MediaPicker.choose({mediaType:'tv', mediaId:row.mediaId, season:row.season, episode:row.episode}, [row.season]);
                guardOwner(owner); state.fetched = 0; load();
            } catch (error) { notify(error.message); }
        }));
        if (row.state === 'complete' && row.nextSeason) node.append(button('Start next season', () => confirmNextUp(row, 'next-season', owner, row.nextSeason)));
        const more = el('details'); more.append(el('summary', 'Manage'));
        if (row.state !== 'stopped') more.append(button('Stop following', () => confirmNextUp(row, 'stop', owner)));
        more.append(button('Restart season', () => confirmNextUp(row, 'restart', owner))); node.append(more);
        return node;
    }
    function renderNextUp(node, rows) {
        const signature = JSON.stringify(rows);
        if (node.dataset.rendered !== signature) {
            node.querySelector('.mp-list').replaceChildren(...rows.map(nextUpCard)); node.dataset.rendered = signature;
        }
        const message = state.error || (rows.length ? '' : 'Watch two minutes of an episode, or follow a season from its series page.');
        const status = node.querySelector('.mp-status'); if (status.textContent !== message) status.textContent = message;
    }
    const nextUpMenu = button('Manage Next Up', async () => {
        await load();
        const view = window.MediaPicker.dialog('Manage Next Up'); view.panel.dataset.mpDialog = 'next-up';
        const section = el('div'); section.append(el('p', '', 'mp-status'), el('div', undefined, 'mp-list'));
        view.panel.append(section); renderNextUp(section, state.data?.nextUp || []);
    });
    nextUpMenu.classList.add('mr-launcher'); document.querySelector('#media-controls-menu')?.append(nextUpMenu);
    async function followSeason(mid) {
        const owner = state.owner;
        try {
            guardOwner(owner);
            const data = await api('personal-next-up-action', {mediaId:mid, action:'options'}); guardOwner(owner);
            const view = window.MediaPicker.dialog('Follow a season'); view.panel.dataset.mpDialog = 'next-up';
            const select = el('select'); select.setAttribute('aria-label', 'Season to follow');
            for (const n of data.seasons) { const option = el('option', 'Season '+n); option.value = n; select.append(option); }
            view.panel.append(el('p', 'Start this season at episode 1 in Next Up. No episodes download automatically.'), select);
            const start = button('Start season', async () => {
                start.disabled = true;
                try { await nextUpAction({mediaId:mid}, 'start', owner, Number(select.value)); view.finish(); }
                catch (error) { view.panel.append(el('p', error.message)); start.disabled = false; }
            }); start.disabled = !data.seasons.length; view.actions.append(start);
        } catch (error) { notify(error.message); }
    }
    function renderRow(node, movies, empty) {
        const serialized = JSON.stringify(movies);
        if (node.dataset.rendered !== serialized) {
            node.querySelector('.mp-list').replaceChildren(...movies.map(m => card(m)));
            node.dataset.rendered = serialized;
        }
        const message = state.error || (movies.length ? (node.id === 'mp-for-you' && state.data?.libraryOnly ? 'Recommendations from your accessible library.' : '') : empty);
        const status = node.querySelector('.mp-status'); if (status.textContent !== message) status.textContent = message;
    }
    function favoritesPage() {
        const container = document.querySelector('#favoritesTab');
        if (!container || !state.owner) return;
        let node = container.querySelector('#mp-favorites');
        if (!node) { node = section('mp-favorites', 'From discovery'); container.prepend(node); }
        // Native library favorites remain in Jellyfin's existing sections.
        const external = (state.data?.favorites || []).filter(m => !m.itemId || m.favoritePending);
        node.hidden = !external.length;
        renderRow(node, external, '');
    }
    function extraControls(mid, kind) {
        const controls = el('div', undefined, 'mp-extra'); controls.dataset.mpExtra = kind+':'+mid;
        controls.append(heartButton(mid, kind));
        if (kind === 'tv') controls.append(episodeButton(mid));
        return controls;
    }
    function decorateDiscovery() {
        document.querySelectorAll('.jellyseerr-card,.je-more-info-modal').forEach(node => {
            const link = node.matches('.je-more-info-modal') ? node : node.querySelector('[data-tmdb-id][data-media-type]');
            const kind = link?.dataset.mediaType, id = link?.dataset.tmdbId;
            if (!['movie', 'tv'].includes(kind) || !/^\d+$/.test(id || '')) return;
            const old = node.querySelector('.mp-extra');
            if (old?.dataset.mpExtra === kind+':'+id) return;
            old?.remove();
            const target = node.matches('.je-more-info-modal') ? node.querySelector('[data-mount="actions"],.modal-container') : node.querySelector('.cardBox') || node;
            target?.append(extraControls(Number(id), kind));
        });
        document.querySelectorAll('[data-mp-heart]').forEach(b => {
            const favorite = !!state.data?.favorites?.some(m => m.id === Number(b.dataset.mpHeart) && m.mediaType === b.dataset.mpType);
            const label = favorite ? 'Remove from Favorites' : 'Add to Favorites';
            if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
            b.setAttribute('aria-pressed', String(favorite));
            const icon = favorite ? '♥' : '♡'; if (b.textContent !== icon) b.textContent = icon;
        });
    }
    async function detailsButton() {
        const hash = location.hash.replace(/^#!?/, '');
        if (!/^\/?details\?/.test(hash)) { document.querySelector('.mp-library-save')?.remove(); state.detail = ''; return; }
        const id = new URLSearchParams(hash.split('?')[1]).get('id'); if (!id || state.detail === id) return;
        state.detail = id; const generation = state.generation;
        document.querySelector('.mp-library-save')?.remove();
        try {
            const movie = await api('personal-movie', { itemId: id });
            if (!valid(generation) || state.detail !== id) return;
            const b = extraControls(movie.id, movie.mediaType || 'movie'); b.classList.add('mp-library-save');
            if (movie.mediaType === 'tv') b.append(button('Follow season', () => followSeason(movie.id)));
            const menu = document.querySelector('#media-controls-menu');
            if (menu) { b.style.position = 'static'; b.append(el('span', 'Favorites')); }
            (menu || document.body).append(b); decorateDiscovery();
        } catch { /* Episodes, folders and unindexed movies have no movie-list action. */ }
    }
    async function load() {
        if (state.busy || !state.owner || Date.now()-state.fetched < 30000) return;
        state.busy = true; const generation = state.generation;
        try {
            const result = await api('personal-home');
            if (!valid(generation)) return;
            state.data = result; state.error = ''; state.fetched = Date.now(); updateBackdrop(); placeRows(); favoritesPage(); decorateDiscovery();
        } catch (error) {
            if (valid(generation)) {
                state.fetched = Date.now();
                state.error = state.data ? 'Showing your saved lists; refresh is temporarily unavailable.' : error.message;
                placeRows();
            }
        } finally {
            if (valid(generation)) {
                state.busy = false;
                if (state.reload) { state.reload = false; state.fetched = 0; load(); }
            }
        }
    }
    function update() {
        const owner = currentUser();
        if (owner !== state.owner) {
            clearBackdrop();
            state.owner = owner; state.generation++; state.data = null; state.fetched = 0; state.busy = false; state.reload = false; state.prefs = null; state.prefsLoading = false; state.detail = ''; state.error = '';
            document.querySelectorAll('.mp-section,.mp-extra,.mp-library-save').forEach(n => n.remove());
            document.querySelectorAll('.mp-native-next-up').forEach(n => n.classList.remove('mp-native-next-up'));
            document.querySelectorAll('[data-mp-dialog]').forEach(n => n.closest('.mr-overlay')?.remove());
        }
        updateBackdrop();
        if (!owner) return;
        if (!state.prefsLoading && window.ApiClient.getDisplayPreferences) {
            state.prefsLoading = true; const generation = state.generation;
            Promise.resolve(ApiClient.getDisplayPreferences('usersettings', owner, 'emby')).then(p => { if (valid(generation)) { state.prefs = p.CustomPrefs; placeRows(); } }).catch(() => {});
        }
        placeRows(); favoritesPage(); decorateDiscovery(); detailsButton(); load();
    }
    let scheduled;
    new MutationObserver(() => { if (!scheduled) scheduled = setTimeout(() => { scheduled = null; update(); }, 100); }).observe(document.body, { childList: true, subtree: true });
    const refresh = () => { state.fetched = 0; state.reload = state.busy; update(); };
    window.addEventListener('hashchange', refresh);
    document.addEventListener('viewshow', refresh);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    document.addEventListener('jellyseerr-media-requested', refresh);
    every(() => { if (!document.hidden) return update(); }, 1000);
    update();
})();
