/* Manual release selection: extends the pinned Jellyfin Enhanced request UI. */
(() => {
    'use strict';
    if (window.mediaReleasePickerLoaded) return;
    window.mediaReleasePickerLoaded = true;
    // One heartbeat for periodic UI work. Events still update the affected
    // controls immediately; slow jobs cannot overlap their next scheduled run.
    const periodicJobs = new Set();
    function every(run, interval) {
        const job = {run, interval, next: performance.now()+interval, busy: false};
        periodicJobs.add(job);
        return () => periodicJobs.delete(job);
    }
    setInterval(() => {
        const now = performance.now();
        for (const job of periodicJobs) {
            if (job.busy || now < job.next) continue;
            job.next = now+job.interval; job.busy = true;
            Promise.resolve().then(() => { if (periodicJobs.has(job)) return job.run(); })
                .catch(() => { /* Keep independent controls running during failures. */ })
                .finally(() => { job.busy = false; });
        }
    }, 1000);
    const style = document.createElement('style');
    style.textContent = `
      .mr-overlay{position:fixed;inset:0;z-index:1000000;background:#000b;display:grid;place-items:center;padding:16px}
      .mr-dialog{background:#181c24;color:#f5f6fa;border:1px solid #465066;border-radius:14px;padding:24px;width:min(1050px,94vw);max-height:88vh;overflow:auto;box-sizing:border-box;font:16px sans-serif}
      .mr-dialog h2{margin:0 0 8px}.mr-dialog p{line-height:1.5;color:#c5ccda}
      .mr-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:16px 0}
      .mr-dialog button,.mr-dialog select{background:#293449;color:white;border:1px solid #62718a;border-radius:7px;padding:10px;cursor:pointer;font:inherit}
      .mr-dialog button:disabled{opacity:.45;cursor:default}.mr-dialog button:focus-visible,.mr-dialog select:focus-visible{outline:3px solid #82cfff}
      .mr-row{border-top:1px solid #414957;padding:14px 0;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}
      .mr-title{overflow-wrap:anywhere;font-weight:600}.mr-details{margin:6px 0;color:#aebcd2;font-size:14px}.mr-rejected{color:#ffc0a7;font-size:14px}
      .mr-status{white-space:pre-wrap}.mr-launcher{position:fixed;bottom:18px;right:18px;z-index:10010;border:1px solid #62718a;border-radius:20px;background:#202c40;color:white;padding:10px 16px;cursor:pointer}
      .mr-launcher[hidden]{display:none}
      #randomItemButtonContainer,#randomItemButton{display:none!important}
      .mr-subtitles{z-index:100000;bottom:calc(66px + env(safe-area-inset-bottom))}
      .mr-menu{position:fixed;right:18px;bottom:calc(70px + env(safe-area-inset-bottom));z-index:100001;background:#181c24;color:white;padding:12px;border:1px solid #62718a;border-radius:12px;width:min(310px,85vw);max-height:70vh;overflow:auto;font:15px sans-serif}
      .mr-menu[hidden],.mr-ready-toast[hidden]{display:none}.mr-menu .mr-launcher{position:static;display:block;width:100%;margin:5px 0;text-align:left;min-height:44px}.mr-menu .mr-launcher[hidden]{display:none}
      .mr-menu-toggle{bottom:calc(18px + env(safe-area-inset-bottom));z-index:100001;min-height:44px}
      .mr-ready-toast{position:fixed;top:70px;right:18px;z-index:100002;background:#181c24;color:white;padding:16px;border:1px solid #62718a;border-radius:12px;max-width:min(360px,85vw)}
      .mr-ready-card{padding:10px 0;border-top:1px solid #465066}.mr-badges{font-size:13px;color:#a9d8ba;margin:6px 0}.mr-ready-card button,.mr-inline-activity button{padding:10px;min-height:44px;background:#293449;color:white;border:1px solid #62718a;border-radius:7px;margin:4px}
      .mr-inline-activity{margin:16px 0;padding:16px;background:#181c24;border-radius:12px;color:white}.mr-inline-activity progress{width:100%;max-width:320px}
      #media-disk-usage{display:inline-flex;align-items:center;gap:6px;flex:0 0 auto;vertical-align:middle;min-height:44px;padding:4px 9px;margin:0 4px 0 0;border:0;border-radius:8px;background:transparent;color:inherit;font:inherit;font-size:13px;white-space:nowrap;cursor:pointer}
      #media-disk-usage:hover{background:#ffffff15}#media-disk-usage:focus-visible{outline:2px solid #82cfff}
      .mr-disk-ring{display:inline-block;width:22px;height:22px;flex:0 0 22px;border-radius:50%;background:conic-gradient(var(--disk-color,#8b97a9) var(--disk-used,0%),#ffffff30 0);mask:radial-gradient(transparent 52%,#000 56%)}
      @media(max-width:600px){#media-disk-usage{padding:4px;gap:4px;margin-right:2px;font-size:12px}#media-disk-usage .mr-disk-free{display:none}}
      body:has(.videoPlayerContainer:not(.hide)) > .mr-launcher:not(.mr-menu-toggle){display:none}
      @media(max-width:600px){.mr-dialog{padding:16px;max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))}.mr-row{grid-template-columns:1fr}.mr-dialog button,.mr-dialog select{min-height:44px}.mr-overlay{padding-bottom:calc(16px + env(safe-area-inset-bottom))}}
    `;
    document.head.appendChild(style);

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    }
    const controlsMenu = element('div', undefined, 'mr-menu'); controlsMenu.hidden = true;
    controlsMenu.id = 'media-controls-menu'; controlsMenu.setAttribute('aria-label', 'Media controls');
    const controlsToggle = element('button', 'Media', 'mr-launcher mr-menu-toggle');
    controlsToggle.setAttribute('aria-expanded', 'false'); controlsToggle.setAttribute('aria-controls', controlsMenu.id);
    controlsToggle.onclick = () => { controlsMenu.hidden = !controlsMenu.hidden; controlsToggle.setAttribute('aria-expanded', String(!controlsMenu.hidden)); };
    controlsMenu.addEventListener('keydown', event => { if (event.key === 'Escape') { controlsMenu.hidden = true; controlsToggle.setAttribute('aria-expanded', 'false'); controlsToggle.focus(); } });
    controlsMenu.addEventListener('click', event => { if (event.target.closest('button.mr-launcher')) { controlsMenu.hidden = true; controlsToggle.setAttribute('aria-expanded', 'false'); } });
    document.body.append(controlsMenu, controlsToggle);
    function mountControls() {
        const fullscreen = document.fullscreenElement;
        const host = fullscreen && fullscreen.tagName !== 'VIDEO' ? fullscreen : document.body;
        for (const node of [controlsMenu, controlsToggle]) if (node.parentElement !== host) host.append(node);
        const route = location.hash.replace(/^#!?/, '') || location.pathname.replace(/^.*\/web\/?/, '/');
        const videoPage = /^\/?(?:video|videoosd|videoplayer)(?:\.html)?\/?(?:\?|$)/.test(route);
        const visibleVideo = [...document.querySelectorAll('video')].some(node =>
            node.getClientRects().length && !node.closest('.hide,[hidden],[aria-hidden="true"]'));
        // Keep the menu away from the player, including paused and fullscreen video.
        controlsToggle.hidden = !window.ApiClient?.getCurrentUserId?.() || videoPage || visibleVideo;
        if (controlsToggle.hidden) { controlsMenu.hidden = true; controlsToggle.setAttribute('aria-expanded', 'false'); }
    }
    document.addEventListener('fullscreenchange', mountControls);
    document.addEventListener('je:user-changed', mountControls);
    every(mountControls, 1000); mountControls();
    async function api(path, data, signal) {
        const token = window.ApiClient?.accessToken();
        if (!token) throw new Error('Sign in to Jellyfin.');
        const device = window.ApiClient.deviceId?.() || 'media-picker';
        const response = await fetch(ApiClient.getUrl('MediaReleases/'+path), {
            method: data === undefined ? 'GET' : 'POST',
            headers: { 'Authorization': `MediaBrowser Client="Media picker", Device="Browser", DeviceId=${JSON.stringify(device)}, Version="1", Token=${JSON.stringify(token)}`, 'Content-Type': 'application/json' },
            body: data === undefined ? undefined : JSON.stringify(data), signal
        });
        const text = await response.text();
        let result;
        try { result = text ? JSON.parse(text) : null; } catch { /* Handle non-JSON error pages below. */ }
        if (response.status === 401) throw new Error('Your Jellyfin session was rejected. Sign out and sign in again.');
        if (!response.ok) throw new Error(result?.error || `The media service returned HTTP ${response.status}. Try again after checking its status.`);
        if (!result || typeof result !== 'object') throw new Error('The media service returned an empty or invalid response. Try again.');
        return result;
    }
    const subtitleLanguage = value => ({ en: 'en', eng: 'en', pb: 'pb', pob: 'pb', por: 'pb', 'pt-br': 'pb' })[String(value).toLowerCase()];
    function nativeSubtitleStatus(message) {
        const editor = document.querySelector('.subtitleEditorDialog');
        if (!editor) return;
        let status = editor.querySelector('.mr-provider-status');
        if (!status) { status = element('p', '', 'mr-status mr-provider-status'); status.setAttribute('role', 'status'); editor.querySelector('.subtitleSearchForm')?.after(status); }
        status.textContent = message;
    }
    const adaptedClients = new WeakSet();
    function installSubtitleBridge() {
        const client = window.ApiClient;
        if (!client?.getJSON || !client.ajax || adaptedClients.has(client)) return;
        adaptedClients.add(client);
        const getJSON = client.getJSON, ajax = client.ajax;
        function route(url) {
            try {
                const target = new URL(url, location.href), base = new URL(client.getUrl(''), location.href);
                return target.origin === base.origin && target.pathname.match(/\/Items\/([a-f0-9-]{32,36})\/RemoteSearch\/Subtitles\/([^/]+)$/i);
            } catch { return null; }
        }
        client.getJSON = async function(url, ...args) {
            const match = route(url); if (!match) return getJSON.call(this, url, ...args);
            const owner = client.getCurrentUserId?.(), language = subtitleLanguage(decodeURIComponent(match[2]));
            const current = () => client === window.ApiClient && owner === client.getCurrentUserId?.();
            nativeSubtitleStatus('Searching Bazarr providers…');
            if (!language) { nativeSubtitleStatus('Choose English or Brazilian Portuguese; these are the configured subtitle languages.'); return []; }
            try {
                const result = await api('subtitle-search', { itemId: match[1] });
                if (!current()) return [];
                nativeSubtitleStatus((result.warnings || []).join(' '));
                return result.subtitles.filter(row => row.language === language).map(row => ({
                    Id: 'media-bazarr-'+row.id,
                    ProviderName: String(row.provider).replace(/[<>&"']/g, ''),
                    Name: row.release || row.provider, Format: 'Subtitle',
                    Comment: `${row.score}% match${row.missing.length ? ' · Does not match: '+row.missing.join(', ') : ''}`,
                    HearingImpaired: row.hearingImpaired, Forced: row.forced
                }));
            } catch (error) { if (current()) nativeSubtitleStatus(error.message); return []; }
        };
        client.ajax = async function(options, ...args) {
            const match = route(options?.url);
            if (!match || String(options.type || options.method).toUpperCase() !== 'POST' || !match[2].startsWith('media-bazarr-')) return ajax.call(this, options, ...args);
            const owner = client.getCurrentUserId?.(), id = decodeURIComponent(match[2]).slice('media-bazarr-'.length);
            try {
                const result = await api('subtitle-download', { id });
                if (owner === client.getCurrentUserId?.()) {
                    nativeSubtitleStatus(result.message);
                    followSubtitle(id, nativeSubtitleStatus, () => owner === client.getCurrentUserId?.() && !!document.querySelector('.subtitleEditorDialog'));
                }
                return result;
            } catch (error) { nativeSubtitleStatus(error.message); throw error; }
        };
    }
    async function followSubtitle(id, show, current) {
        for (let attempt = 0; attempt < 30 && current(); attempt++) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            if (!current()) return;
            try {
                const result = await api('subtitle-status', { id });
                if (!current()) return;
                show(result.message);
                if (result.state === 'ready' || result.state === 'uncertain') return;
            } catch (error) { if (current()) show(error.message); return; }
        }
        if (current()) show('Still waiting for Bazarr/Jellyfin. Check Bazarr activity before submitting again.');
    }
    installSubtitleBridge();
    every(installSubtitleBridge, 1000);

    let versionChecked = 0;
    async function checkClientVersion() {
        if (!window.mediaUIRevision || !window.ApiClient || document.hidden || Date.now()-versionChecked < 60000) return;
        versionChecked = Date.now();
        try {
            const response = await fetch(ApiClient.getUrl('MediaReleases/client-version'), { cache: 'no-store' });
            const { revision } = await response.json();
            if (!/^[a-f0-9]{16}$/.test(revision || '') || revision === window.mediaUIRevision || document.querySelector('.mr-ui-update')) return;
            const refresh = element('button', 'Interface updated — reload', 'mr-launcher mr-ui-update');
            refresh.style.bottom = '162px';
            refresh.onclick = () => { const url = new URL(location.href); url.searchParams.set('media_ui', revision); location.replace(url.href); };
            controlsMenu.append(refresh);
        } catch { /* Offline/resuming clients keep their current interface. */ }
    }
    document.addEventListener('visibilitychange', checkClientVersion);
    window.addEventListener('focus', checkClientVersion);
    every(checkClientVersion, 60000);
    checkClientVersion();

    function dialog(title, close) {
        const previous = document.activeElement;
        const overlay = element('div', undefined, 'mr-overlay');
        const panel = element('section', undefined, 'mr-dialog');
        panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true');
        panel.setAttribute('aria-label', title); panel.tabIndex = -1;
        const heading = element('h2', title);
        const done = element('button', 'Close');
        const actions = element('div', undefined, 'mr-actions');
        actions.append(done); panel.append(heading, actions); overlay.append(panel);
        const finish = () => { overlay.remove(); previous?.focus(); close?.(); };
        done.onclick = finish;
        overlay.onkeydown = event => {
            if (event.key === 'Escape') { event.stopPropagation(); finish(); }
            if (event.key === 'Tab') {
                const controls = [...panel.querySelectorAll('button:not(:disabled),input:not(:disabled),select,a[href]')];
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
        };
        const fullscreen = document.fullscreenElement;
        (fullscreen && fullscreen.tagName !== 'VIDEO' ? fullscreen : document.body).append(overlay); panel.focus();
        return { panel, actions, finish };
    }

    const diskButton = element('button'); diskButton.id = 'media-disk-usage'; diskButton.type = 'button';
    const diskRing = element('span', undefined, 'mr-disk-ring'); diskRing.setAttribute('aria-hidden', 'true');
    const diskPercent = element('span', '…'), diskFree = element('span', '', 'mr-disk-free');
    diskButton.append(diskRing, diskPercent, diskFree);
    let diskOwner, diskClient, diskData = null, diskLastCheck = 0, diskRequest = null, diskDialog = null;
    let diskTab = null, diskTabMargin = '', diskTabParent = null, diskParentPosition = '';
    function clearDiskPlacement() {
        if (diskTab) diskTab.style.marginLeft = diskTabMargin;
        if (diskTabParent) diskTabParent.style.position = diskParentPosition;
        diskTab = null; diskTabParent = null;
        diskButton.style.position = ''; diskButton.style.left = ''; diskButton.style.top = '';
    }
    const diskSize = bytes => (bytes / 1e9).toLocaleString(undefined, {maximumFractionDigits:1})+' GB';
    function renderDisk() {
        const value = diskData;
        diskPercent.textContent = value ? Math.round(value.usedPercent)+'%' : 'Unavailable';
        diskFree.textContent = value ? '· '+diskSize(value.availableBytes)+' free' : '';
        diskRing.style.setProperty('--disk-used', (value?.usedPercent || 0)+'%');
        diskRing.style.setProperty('--disk-color', !value ? '#8b97a9' : value.usedPercent >= 90 ? '#ff7474' : value.usedPercent >= 80 ? '#f5bd58' : '#6bceae');
        const details = value ? `${value.usedPercent}% used · ${diskSize(value.usedBytes)} used / ${diskSize(value.totalBytes)} total · ${diskSize(value.availableBytes)} available` : 'Disk usage unavailable';
        diskButton.title = details; diskButton.setAttribute('aria-label', details+'. Show disk details');
        if (diskDialog?.panel.isConnected) diskDialog.status.textContent = details;
    }
    diskButton.onclick = event => {
        // This is a status control beside the tab, never another tab selection.
        event.preventDefault(); event.stopPropagation();
        if (!diskOwner || diskOwner !== window.ApiClient?.getCurrentUserId?.()) return;
        diskDialog?.finish(); diskDialog = dialog('Media disk');
        diskDialog.status = element('p'); diskDialog.status.setAttribute('role', 'status');
        diskDialog.panel.append(diskDialog.status, element('p', 'Usage includes everything on the disk containing your media. Available space excludes filesystem reserves. Refreshes every minute.'));
        renderDisk();
    };
    function mountDisk() {
        const client = window.ApiClient, owner = client?.getCurrentUserId?.();
        if (owner !== diskOwner || client !== diskClient) {
            diskRequest?.abort(); diskRequest = null; diskData = null; diskLastCheck = 0;
            diskDialog?.finish(); diskDialog = null; clearDiskPlacement(); diskButton.remove();
            diskOwner = owner; diskClient = client; renderDisk();
        }
        if (!owner) return;
        const target = [...document.querySelectorAll('#je-native-tab-btn-requests, #je-native-tab-link-requests')].find(node =>
            node.getClientRects().length && !node.closest('.hide,[hidden],[aria-hidden="true"],.osdHeader'));
        if (!target) { clearDiskPlacement(); diskButton.remove(); return; }
        if (target.id === 'je-native-tab-btn-requests') {
            // Keep non-tab controls out of JE's indexed tab ordering. Reserve
            // room beside Requests, while appending this control after the tabs.
            if (diskTab !== target || diskTabParent !== target.parentElement) {
                clearDiskPlacement(); diskTab = target; diskTabMargin = target.style.marginLeft;
                diskTabParent = target.parentElement; diskParentPosition = diskTabParent.style.position;
                if (getComputedStyle(diskTabParent).position === 'static') diskTabParent.style.position = 'relative';
                diskButton.style.position = 'absolute'; diskTabParent.append(diskButton);
            }
            const width = diskButton.getBoundingClientRect().width + 4;
            if (target.style.marginLeft !== width+'px') {
                target.style.marginLeft = width+'px';
                document.querySelector('[is="emby-tabs"]')?.refresh?.();
            }
            diskButton.style.left = (target.offsetLeft-width)+'px';
            diskButton.style.top = (target.offsetTop+(target.offsetHeight-diskButton.offsetHeight)/2)+'px';
        } else {
            clearDiskPlacement();
            if (diskButton.nextElementSibling !== target) target.before(diskButton);
        }
        if (document.hidden || diskRequest || Date.now()-diskLastCheck < 60000) return;
        diskLastCheck = Date.now();
        const controller = new AbortController(); diskRequest = controller;
        const timeout = setTimeout(() => controller.abort(), 10000);
        const current = () => diskRequest === controller && owner === window.ApiClient?.getCurrentUserId?.() && client === window.ApiClient;
        api('disk-usage', undefined, controller.signal).then(value => {
            if (!current()) return;
            if (![value.totalBytes,value.usedBytes,value.availableBytes,value.usedPercent].every(Number.isFinite)
                || value.totalBytes <= 0 || value.usedBytes < 0 || value.availableBytes < 0
                || value.usedBytes > value.totalBytes || value.availableBytes > value.totalBytes
                || value.usedPercent < 0 || value.usedPercent > 100) throw new Error('Invalid disk reading');
            diskData = value; renderDisk();
        }).catch(() => { if (current()) { diskData = null; renderDisk(); } })
            .finally(() => { clearTimeout(timeout); if (diskRequest === controller) diskRequest = null; });
    }
    every(mountDisk, 2000);
    for (const name of ['viewshow', 'je:user-changed', 'visibilitychange']) document.addEventListener(name, mountDisk);
    window.addEventListener('resize', mountDisk); window.addEventListener('hashchange', mountDisk);
    mountDisk();
    const episodeLabel = (season, episode) => `S${String(season).padStart(2, '0')}${episode == null ? ' · Full season' : 'E'+String(episode).padStart(2, '0')}`;
    function choose(body, seasons = []) {
        return new Promise((resolve, reject) => {
            let settled = false, submitting = false, generation = 0, scope;
            const owner = window.ApiClient?.getCurrentUserId?.();
            const current = () => owner === window.ApiClient?.getCurrentUserId?.();
            const tv = body.mediaType === 'tv';
            const fixedEpisode = tv && Number.isInteger(body.episode);
            const view = dialog('Choose a release', () => {
                generation++;
                if (!settled) reject(new Error(submitting ? 'Check Download status for the submission outcome.' : 'Selection cancelled; no download requested.'));
            });
            const status = element('p', '', 'mr-status'); status.setAttribute('role', 'status');
            const results = element('div'), episodeRows = element('div', undefined, 'mr-episodes');
            const sort = element('select'); sort.setAttribute('aria-label', 'Sort releases'); sort.hidden = true;
            for (const [value, label] of [['seeders', 'Most seeders'], ['size', 'Smallest size'], ['quality', 'Quality']]) { const option = element('option', label); option.value = value; sort.append(option); }
            let renderReleases;
            const search = element('button', 'Search releases'); search.hidden = tv;
            let seasonSelect, fullSeason, backToEpisodes;
            async function loadEpisodes() {
                const version = ++generation; scope = undefined;
                results.replaceChildren(); episodeRows.replaceChildren(); search.hidden = true;
                episodeRows.hidden = false; backToEpisodes.hidden = true;
                fullSeason.disabled = true; search.disabled = false; status.textContent = 'Loading episodes…';
                try {
                    const data = await api('episodes', { mediaId: body.mediaId, season: Number(seasonSelect.value) });
                    if (!current() || version !== generation || !view.panel.isConnected) return;
                    status.textContent = 'Choose an episode, or explicitly choose the full season. Nothing downloads until you select a release.';
                    for (const episode of data.episodes) {
                        const row = element('div', undefined, 'mr-row'); row.dataset.episode = episode.number;
                        const info = element('div');
                        info.append(element('div', `${episodeLabel(data.season, episode.number)} — ${episode.title}`, 'mr-title'));
                        info.append(element('div', `${episode.airDate || 'Air date unknown'} · ${episode.available ? 'In library' : 'Not in library'}`, 'mr-details'));
                        const select = element('button', episode.aired ? 'Choose release' : 'Not aired / date unknown');
                        select.disabled = !episode.aired;
                        select.onclick = () => { scope = episode.number; search.hidden = false; search.onclick(); };
                        row.append(info, select); episodeRows.append(row);
                    }
                    if (!data.episodes.length) episodeRows.append(element('p', 'Episode metadata is not ready. Reload this season shortly.'));
                    fullSeason.disabled = false;
                } catch (error) { if (version === generation) status.textContent = error.message; }
            }
            if (tv) {
                seasonSelect = element('select'); seasonSelect.setAttribute('aria-label', 'Season');
                seasons.forEach(number => { const option = element('option', 'Season '+number); option.value = number; seasonSelect.append(option); });
                if (seasons.includes(body.season)) seasonSelect.value = body.season;
                seasonSelect.onchange = loadEpisodes;
                fullSeason = element('button', 'Full season');
                fullSeason.onclick = () => { scope = null; search.hidden = false; search.onclick(); };
                const reload = element('button', 'Reload episodes'); reload.onclick = loadEpisodes; reload.hidden = !!body.replacementOf || fixedEpisode;
                backToEpisodes = element('button', 'Choose another episode'); backToEpisodes.hidden = true;
                backToEpisodes.onclick = loadEpisodes;
                view.actions.append(seasonSelect, reload, fullSeason, backToEpisodes);
            }
            view.actions.append(search, sort); view.panel.append(status, episodeRows, results);
            sort.onchange = () => { if (!submitting) renderReleases?.(); };
            search.onclick = async () => {
                if (submitting || !current() || (tv && scope === undefined)) return;
                const version = ++generation;
                search.disabled = true; sort.hidden = true; results.replaceChildren();
                const query = { ...body }; delete query.episode;
                let label = '';
                if (tv) {
                    episodeRows.hidden = true; backToEpisodes.hidden = !!body.replacementOf || fixedEpisode;
                    query.season = Number(seasonSelect.value);
                    if (scope !== null) query.episode = scope;
                    label = episodeLabel(query.season, query.episode);
                }
                status.textContent = `${label} Searching indexers…`;
                try {
                    const response = await api('search', query);
                    if (!current() || version !== generation || !view.panel.isConnected) return;
                    status.textContent = response.releases.length ? `${response.title} ${label} — ${response.releases.length} results. Existing titles use their current quality profile.` : `${label} No releases found. No alternative episode or season will be downloaded.`;
                    sort.hidden = !response.releases.length;
                    renderReleases = () => {
                    if (version !== generation || !current()) return;
                    results.replaceChildren();
                    const ordered = [...response.releases].sort((a, b) => sort.value === 'size' ? a.size-b.size : sort.value === 'quality' ? String(a.quality).localeCompare(String(b.quality)) : (b.seeders ?? -1)-(a.seeders ?? -1));
                    for (const release of ordered) {
                        const row = element('div', undefined, 'mr-row');
                        const info = element('div');
                        info.append(element('div', release.title, 'mr-title'));
                        info.append(element('div', `${release.quality || 'Unknown quality'} · ${(release.size/1024**3).toFixed(2)} GiB · ${release.seeders ?? '?'} seeders · ${release.indexer || 'Unknown indexer'}`, 'mr-details'));
                        if (release.rejections.length) info.append(element('div', release.rejections.join(' · '), 'mr-rejected'));
                        const select = element('button', 'Select this release'); select.disabled = !!release.rejections.length;
                        select.onclick = async () => {
                            if (submitting || version !== generation || !current()) return;
                            submitting = true;
                            for (const control of view.panel.querySelectorAll('button,select')) control.disabled = true;
                            view.actions.firstChild.disabled = false; // Keep Close available.
                            status.textContent = `${label} ${body.replacementOf ? 'Confirm the replacement to continue.' : 'Saving your selection… Existing downloads will not be cancelled.'}`;
                            try {
                                if (body.replacementOf && !await confirmReplacement(release.title)) {
                                    submitting = false;
                                    for (const control of view.panel.querySelectorAll('button,select')) control.disabled = false;
                                    renderReleases(); return;
                                }
                                if (!current()) throw new Error('Account changed. Reopen release selection.');
                                const response = await api('select', { id: release.id });
                                settled = true; status.textContent = `${label} ${response.message || response.state}`;
                                window.JellyfinEnhanced?.toast(status.textContent, 5000);
                                resolve(response);
                            } catch (error) { status.textContent = error.message+' Open Download status to check its status.'; }
                        };
                        row.append(info, select); results.append(row);
                    }
                    }; renderReleases();
                } catch (error) { if (version === generation) status.textContent = error.message; }
                finally { if (!submitting && version === generation) search.disabled = false; }
            };
            if (tv && (body.replacementOf || fixedEpisode)) {
                scope = body.episode ?? null; seasonSelect.value = body.season; seasonSelect.disabled = true;
                fullSeason.hidden = true; backToEpisodes.hidden = true;
                search.hidden = false; search.click();
            } else if (tv) loadEpisodes(); else search.click();
        });
    }

    function confirmReplacement(title) {
        return new Promise(resolve => {
            let accepted = false;
            const view = dialog('Replace this download?', () => resolve(accepted));
            view.panel.append(element('p', `Use “${title}”? Once approved and verified, this stops the previous transfer and submits this release. Existing files are retained. Nothing else is selected automatically.`));
            const confirm = element('button', 'Confirm replacement'); view.actions.append(confirm);
            confirm.onclick = () => { accepted = true; view.finish(); };
        });
    }

    const phaseLabels = { approval: 'Awaiting approval', verifying: 'Verifying release', metadata: 'Finding peers',
        queued: 'Queued', peers: 'Finding peers', downloading: 'Downloading', importing: 'Importing', ready: 'Ready to watch',
        paused: 'Stopped', failed: 'Needs attention', uncertain: 'Check download queue', unavailable: 'Status unavailable', error: 'Download error' };
    let activityOwner, activityData, activityBusy = false, activityGeneration = 0;
    const readyMenu = element('section'); readyMenu.setAttribute('aria-label', 'Ready to watch'); controlsMenu.append(readyMenu);
    const readyToast = element('section', undefined, 'mr-ready-toast'); readyToast.hidden = true;
    readyToast.setAttribute('role', 'status'); document.body.append(readyToast);
    let toasted = new Set(), toastTimer;
    const badges = item => `Subtitles: PT-BR ${item.subtitles.pb ? '✓' : 'not available'} · English ${item.subtitles.en ? '✓' : 'not available'}`;
    async function playItem(itemId, owner) {
        if (owner !== window.ApiClient?.getCurrentUserId?.()) throw new Error('Account changed.');
        const client = window.ApiClient;
        const sessions = await client.ajax({type: 'GET', url: client.getUrl('Sessions'), dataType: 'json'});
        if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
        const session = sessions.find(s => s.DeviceId === client.deviceId?.() && String(s.UserId).replaceAll('-', '') === owner.replaceAll('-', ''));
        if (session) await client.ajax({type: 'POST', url: client.getUrl(`Sessions/${session.Id}/Playing`, {playCommand: 'PlayNow', itemIds: itemId})});
        else location.hash = '/details?id='+itemId;
    }
    function readyCard(notice, owner) {
        const card = element('div', undefined, 'mr-ready-card');
        card.append(element('strong', notice.title+' — ready to watch'), element('div', notice.item.title), element('div', badges(notice.item), 'mr-badges'));
        const play = element('button', 'Play now'), dismiss = element('button', 'Dismiss');
        const act = async shouldPlay => {
            if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
            play.disabled = true; dismiss.disabled = true;
            try {
                if (shouldPlay) await playItem(notice.item.id, owner);
                if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
                await api('acknowledge', {id: notice.id}); readyToast.hidden = true;
                activityData = null; await pollActivity();
            } catch (error) { card.append(element('p', error.message)); play.disabled = false; dismiss.disabled = false; }
        };
        play.onclick = () => act(true); dismiss.onclick = () => act(false); card.append(play, dismiss); return card;
    }
    function renderActivity(list, data, owner) {
        list.replaceChildren();
        const selections = data.selections.filter(row => !row.downloadComplete && row.phase !== 'ready');
        const music = data.music ? {...data.music, selections: (data.music.selections || []).filter(row => !row.downloadComplete && !row.itemId)} : null;
        if (!selections.length && !music?.selections?.length && !data.musicError) list.append(element('p', 'No active downloads.'));
        for (const row of selections) {
            const item = element('div', undefined, 'mr-row'), info = element('div');
            const scope = row.context.mediaType === 'tv' ? ' — '+episodeLabel(row.context.season, row.context.episode) : '';
            info.append(element('div', row.title+scope, 'mr-title'), element('p', (phaseLabels[row.phase] || row.phase)+' — '+row.message));
            if (row.percent != null && row.percent < 100) {
                const progress = element('progress'); progress.max = 100; progress.value = row.percent; progress.setAttribute('aria-label', 'Download progress'); info.append(progress);
                info.append(element('div', `${row.percent}% · ${Math.round((row.speed || 0)/1024)} KiB/s · ${row.peers || 0} connected seeds`, 'mr-details'));
            }
            for (const playable of row.ready) {
                const play = element('button', 'Play '+(playable.title || 'now'));
                play.onclick = () => playItem(playable.id, owner).catch(error => window.JellyfinEnhanced?.toast?.(error.message));
                info.append(play, element('div', badges(playable), 'mr-badges'));
            }
            if (row.canReplace || ['failed', 'cancelled'].includes(row.state)) {
                const again = element('button', 'Choose another release');
                again.onclick = () => {
                    if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
                    const body = {...row.context, ...(row.canReplace ? {replacementOf: row.id} : {})};
                    choose(body, body.mediaType === 'tv' ? [body.season] : []).catch(error => window.JellyfinEnhanced?.toast?.(error.message));
                }; info.append(again);
            }
            if (['pending', 'failed', 'uncertain'].includes(row.state)) {
                const cancel = element('button', 'Cancel selection');
                cancel.onclick = async () => {
                    if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
                    cancel.disabled = true;
                    try { await api('cancel', {id: row.id}); await pollActivity(); }
                    catch (error) { info.append(element('p', error.message)); cancel.disabled = false; }
                }; info.append(cancel);
            }
            item.append(info); list.append(item);
        }
        if (data.musicError) list.append(element('p',data.musicError));
        window.MediaPicker.renderMusicActivity?.(list, music, owner);
    }
    function inlineActivity() {
        if (!activityData || activityOwner !== window.ApiClient?.getCurrentUserId?.()) return;
        let container = [...document.querySelectorAll('.jellyfinenhanced.requests')].find(node =>
            window.JellyfinEnhanced?.helpers?.isActiveTabContainer?.(node) ?? (node.closest('.tabContent')?.classList.contains('is-active') && !node.closest('.hide,[hidden]')));
        container ||= location.hash.split('?')[0] === '#/downloads' ? document.querySelector('#je-downloads-container') : null;
        if (!container) return;
        let section = container.querySelector('.mr-inline-activity');
        if (!section) { section = element('section', undefined, 'mr-inline-activity'); container.prepend(section); }
        const signature = activityOwner+JSON.stringify([activityData.selections,activityData.music,activityData.musicError]);
        if (section.dataset.signature === signature) return;
        section.dataset.signature = signature; section.replaceChildren(element('h2', 'Your download progress'));
        const list = element('div'); section.append(list); renderActivity(list, activityData, activityOwner);
    }
    async function pollActivity() {
        const owner = window.ApiClient?.getCurrentUserId?.();
        if (owner !== activityOwner) {
            activityOwner = owner; activityData = null; activityGeneration++; activityBusy = false; toasted = new Set();
            readyMenu.replaceChildren(); readyToast.replaceChildren(); readyToast.hidden = true; controlsToggle.textContent = 'Media';
            document.querySelectorAll('.mr-activity-dialog').forEach(node => node.remove());
            controlsMenu.hidden = true; controlsToggle.setAttribute('aria-expanded', 'false');
            document.querySelectorAll('.mr-inline-activity').forEach(node => node.remove());
        }
        if (!owner || document.hidden || activityBusy) return;
        activityBusy = true; const generation = activityGeneration;
        try {
            const data = await api('activity');
            if (generation !== activityGeneration || owner !== window.ApiClient?.getCurrentUserId?.()) return;
            activityData = data; readyMenu.replaceChildren();
            for (const notice of data.notifications) readyMenu.append(readyCard(notice, owner));
            controlsToggle.textContent = data.notifications.length ? `Media (${data.notifications.length})` : 'Media';
            const fresh = data.notifications.find(n => !toasted.has(n.id));
            if (fresh) {
                toasted.add(fresh.id); readyToast.replaceChildren(readyCard(fresh, owner)); readyToast.hidden = false;
                clearTimeout(toastTimer); toastTimer = setTimeout(() => { readyToast.hidden = true; }, 12000);
            }
            inlineActivity();
            document.dispatchEvent(new CustomEvent('media:activity', {detail: {owner, data}}));
        } catch { /* Keep the last known view; its refresh button reports errors. */ }
        finally { if (generation === activityGeneration) activityBusy = false; }
    }
    async function history() {
        const owner = window.ApiClient?.getCurrentUserId?.(), view = dialog('Download status');
        view.panel.closest('.mr-overlay').classList.add('mr-activity-dialog');
        const list = element('div'), status = element('p', '', 'mr-status');
        const refresh = element('button', 'Refresh'); view.actions.append(refresh); view.panel.append(status, list);
        const render = data => { if (view.panel.isConnected && owner === window.ApiClient?.getCurrentUserId?.()) renderActivity(list, data, owner); };
        refresh.onclick = async () => {
            refresh.disabled = true;
            try { const data = await api('activity'); render(data); status.textContent = 'Only your requests are shown. Replacements require your confirmation.'; }
            catch (error) { status.textContent = error.message; }
            finally { refresh.disabled = false; }
        };
        const listener = event => {
            if (!view.panel.isConnected || owner !== window.ApiClient?.getCurrentUserId?.()) { document.removeEventListener('media:activity', listener); return; }
            if (event.detail.owner === owner) render(event.detail.data);
        };
        document.addEventListener('media:activity', listener); refresh.click();
    }
    document.addEventListener('je:user-changed', pollActivity);
    document.addEventListener('media:music-changed', pollActivity);
    document.addEventListener('visibilitychange', pollActivity);
    window.addEventListener('je:navigate', inlineActivity);
    document.addEventListener('viewshow', inlineActivity);
    every(pollActivity, 15000); every(inlineActivity, 2000);
    setTimeout(pollActivity, 1500);

    // Jellyfin's native Delete media action only deletes library files. Route
    // managed titles through the broker so their torrents cannot restore them.
    const deletionClients = new WeakSet();
    let deletionQueue = Promise.resolve();
    function installDeletionBridge() {
        const client = window.ApiClient;
        if (!client?.deleteItem || !client.getItem || deletionClients.has(client)) return;
        deletionClients.add(client);
        const original = client.deleteItem;
        client.deleteItem = function(itemId, ...args) {
            const owner = client.getCurrentUserId?.();
            const current = () => owner && client === window.ApiClient && owner === client.getCurrentUserId?.();
            const run = async () => {
                if (!current()) throw new Error('Account changed. Reopen deletion.');
                const item = await client.getItem(owner, itemId);
                if (!current()) throw new Error('Account changed. Reopen deletion.');
                // Collection/playlist deletion changes organization, not media files.
                if (['Playlist', 'BoxSet'].includes(item.Type)) return original.call(client, itemId, ...args);
                return new Promise((resolve, reject) => {
                    let complete = false, busy = false;
                    const view = dialog('Delete media from server', () => { if (!complete) reject(new Error('Deletion cancelled or unfinished.')); });
                    const status = element('p', 'Checking this title and its downloads…', 'mr-status');
                    status.setAttribute('role', 'status'); view.panel.append(status);
                    const close = view.actions.querySelector('button');
                    const valid = () => current() && view.panel.isConnected;
                    view.panel.addEventListener('keydown', event => {
                        if (busy && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); }
                    });
                    const prepare = async () => {
                        try {
                            if (!valid()) return;
                            const preview = await api('item-removal-preview', {itemId});
                            if (!valid()) return;
                            const scope = preview.mediaType === 'tv' ? 'the ENTIRE SERIES, including ALL seasons and episodes'
                                : preview.mediaType === 'music' ? 'the ENTIRE ALBUM, including ALL tracks' : 'this movie';
                            view.panel.append(element('strong', preview.title), element('p', `Permanently delete ${scope} for everyone? This removes its library files, subtitles, associated torrents and downloaded files, and request records. This cannot be undone.`));
                            status.textContent = preview.retry ? 'Continue the unfinished removal.' : `Associated downloads: ${preview.downloads ?? 0}.`;
                            const confirm = element('button', preview.retry ? 'Retry full removal' : 'Delete permanently'); view.actions.append(confirm);
                            confirm.onclick = async () => {
                                if (!valid() || busy) return;
                                busy = true; confirm.disabled = true; close.disabled = true; status.textContent = 'Removing files, torrents and requests…';
                                try {
                                    await api(preview.mediaType === 'music' ? 'music-remove' : 'remove', {id:preview.id});
                                    if (!current()) throw new Error('Account changed. Refresh the library to check the result.');
                                    complete = true; view.finish();
                                    document.dispatchEvent(new Event('media:music-changed'));
                                    document.dispatchEvent(new CustomEvent('jellyseerr-media-requested'));
                                    resolve();
                                } catch (error) {
                                    status.textContent = error.message+' Close and choose Delete media again to review or retry.';
                                } finally { busy = false; close.disabled = false; }
                            };
                        } catch (error) { if (valid()) status.textContent = error.message; }
                    };
                    prepare();
                });
            };
            const result = deletionQueue.then(run, run);
            deletionQueue = result.catch(() => {});
            return result;
        };
    }
    installDeletionBridge();
    every(installDeletionBridge, 2000);
    document.addEventListener('viewshow', installDeletionBridge);

    async function removalDialog() {
        const owner = window.ApiClient?.getCurrentUserId?.();
        const view = dialog('Remove from server');
        const current = () => view.panel.isConnected && owner === window.ApiClient?.getCurrentUserId?.();
        const status = element('p', 'Loading titles…', 'mr-status'); status.setAttribute('role', 'status');
        const filter = element('input'); filter.type = 'search'; filter.placeholder = 'Find a movie or series'; filter.setAttribute('aria-label', filter.placeholder);
        const list = element('div'); view.panel.append(status, filter, list);
        let rows = [];
        const render = () => {
            if (!current()) return;
            list.replaceChildren();
            for (const row of rows.filter(row => row.title.toLowerCase().includes(filter.value.toLowerCase()))) {
                const item = element('div', undefined, 'mr-row');
                item.append(element('div', `${row.title} — ${row.mediaType === 'tv' ? 'Entire series' : 'Movie'}`, 'mr-title'));
                const remove = element('button', row.retryId ? 'Retry removal' : 'Remove…');
                remove.onclick = async () => {
                    if (!current()) return;
                    remove.disabled = true; status.textContent = 'Checking downloads and library…';
                    try {
                        const preview = row.retryId ? { ...row, id: row.retryId } : await api('removal-preview', { mediaType: row.mediaType, mediaId: row.mediaId });
                        if (!current()) return;
                        const confirmation = dialog('Permanently remove '+preview.title);
                        confirmation.panel.append(element('p', `Delete ${preview.mediaType === 'tv' ? 'the entire series, including ALL seasons and episodes' : 'this movie'} for EVERYONE on this server? This removes its library files, subtitles, associated torrents and downloaded files, and requests. Favorites stay saved. This cannot be undone.${preview.downloads == null ? ' This resumes an incomplete removal.' : ' Associated downloads: '+preview.downloads+'.'}`));
                        const confirm = element('button', 'Delete permanently'); confirmation.actions.append(confirm);
                        const result = element('p', '', 'mr-status'); result.setAttribute('role', 'status'); confirmation.panel.append(result);
                        confirm.onclick = async () => {
                            if (!current() || !confirmation.panel.isConnected) return;
                            confirm.disabled = true; result.textContent = 'Removing files and requests…';
                            try {
                                const response = await api('remove', { id: preview.id });
                                if (!current()) return;
                                result.textContent = response.message;
                                rows = rows.filter(x => x.mediaType !== row.mediaType || x.mediaId !== row.mediaId); render();
                                status.textContent = response.message;
                                document.dispatchEvent(new CustomEvent('jellyseerr-media-requested'));
                            } catch (error) {
                                if (!current()) return;
                                result.textContent = error.message;
                                // Refresh the journal so interrupted/partial removals can be resumed explicitly.
                                try { rows = await api('removal-catalogue'); render(); } catch { /* Keep the original error visible. */ }
                            }
                        };
                    } catch (error) { if (current()) status.textContent = error.message; }
                    finally { remove.disabled = false; }
                };
                item.append(remove); list.append(item);
            }
        };
        filter.oninput = render;
        try { rows = await api('removal-catalogue'); if (current()) { status.textContent = 'Choose a title to review before deleting. Series removal includes every season.'; render(); } }
        catch (error) { if (current()) status.textContent = error.message; }
    }
    const removalButton = element('button', 'Remove from server', 'mr-launcher mr-remove-launcher');
    removalButton.style.bottom = '114px'; removalButton.hidden = true;
    removalButton.onclick = removalDialog; controlsMenu.append(removalButton);
    let removalOwner, removalAllowed = false;
    function onRequestsPage() {
        const route = location.hash.split('?')[0];
        if (route === '#/downloads' || location.pathname === '/downloads') return true;
        if (!['', '#/home', '#/home.html'].includes(route)) return false;
        return [...document.querySelectorAll('.jellyfinenhanced.requests')].some(node => {
            const active = window.JellyfinEnhanced?.helpers?.isActiveTabContainer;
            if (active) return active(node);
            return node.closest('.tabContent')?.classList.contains('is-active') &&
                !node.closest('.hide,[hidden],[aria-hidden="true"]') && node.getClientRects().length > 0;
        });
    }
    async function updateRemovalButton() {
        const owner = window.ApiClient?.getCurrentUserId?.();
        removalButton.hidden = true;
        if (!owner || !onRequestsPage()) return;
        try {
            if (owner !== removalOwner) {
                const response = await api('capabilities');
                if (owner !== window.ApiClient?.getCurrentUserId?.()) return;
                removalOwner = owner; removalAllowed = response.canRemove;
            }
            removalButton.hidden = !removalAllowed || !onRequestsPage();
        } catch { removalOwner = undefined; }
    }
    window.addEventListener('hashchange', updateRemovalButton);
    document.addEventListener('viewshow', updateRemovalButton);
    document.addEventListener('je:navigate', updateRemovalButton);
    every(updateRemovalButton, 2000); updateRemovalButton();

    function subtitleDialog(itemId) {
        const owner = window.ApiClient?.getCurrentUserId?.();
        const view = dialog('Find subtitles');
        const current = () => view.panel.isConnected && owner === window.ApiClient?.getCurrentUserId?.();
        const language = element('select'); language.setAttribute('aria-label', 'Subtitle language');
        for (const [code, name] of [['pb', 'Brazilian Portuguese'], ['en', 'English']]) {
            const option = element('option', name); option.value = code; language.append(option);
        }
        const search = element('button', 'Search subtitles');
        const status = element('p', '', 'mr-status'); status.setAttribute('role', 'status');
        const providerStatus = element('p', '', 'mr-status'); providerStatus.setAttribute('role', 'status');
        const results = element('div'); let rows = [], submitting = false;
        view.actions.append(language, search);
        view.panel.append(element('p', 'Compare the match score and release name. Downloads update the shared library and may replace an existing subtitle in that language. Each viewer chooses their playback track in the player’s subtitle menu.'), status, providerStatus, results);
        function render() {
            results.replaceChildren();
            const visible = rows.filter(row => row.language === language.value);
            for (const row of visible) {
                const line = element('div', undefined, 'mr-row'); const info = element('div');
                info.append(element('div', row.release || row.provider, 'mr-title'));
                info.append(element('div', `${row.score}% match · ${row.provider}${row.hearingImpaired ? ' · Hearing impaired' : ''}${row.forced ? ' · Forced only' : ''}`, 'mr-details'));
                if (row.missing.length) info.append(element('div', 'Does not match: '+row.missing.join(', '), 'mr-rejected'));
                const download = element('button', 'Download this subtitle'); download.disabled = submitting;
                download.onclick = async () => {
                    if (submitting) return;
                    submitting = true; search.disabled = true; language.disabled = true; render();
                    status.textContent = 'Submitting subtitle download…';
                    try {
                        if (!current()) throw new Error('Account changed. Reopen the subtitle search.');
                        const result = await api('subtitle-download', { id: row.id });
                        if (current()) { status.textContent = result.message; followSubtitle(row.id, message => { status.textContent = message; }, current); }
                    }
                    catch (error) { status.textContent = error.message+' Check the library before trying again.'; }
                };
                line.append(info, download); results.append(line);
            }
            if (!visible.length) results.append(element('p', 'No subtitles found in this language. Availability depends on the configured providers.'));
        }
        language.onchange = render;
        search.onclick = async () => {
            search.disabled = true; results.replaceChildren(); providerStatus.textContent = ''; status.textContent = 'Searching subtitle providers…';
            try {
                const response = await api('subtitle-search', { itemId });
                if (!current()) return;
                rows = response.subtitles; status.textContent = response.title;
                providerStatus.textContent = (response.warnings || []).join(' '); render();
            } catch (error) { status.textContent = error.message; }
            finally { if (!submitting) search.disabled = false; }
        };
        search.click();
    }

    // SPA navigation and next-episode playback do not always change the hash.
    const subtitleButton = element('button', 'Find subtitles', 'mr-launcher mr-subtitles');
    subtitleButton.hidden = true;
    subtitleButton.onclick = async () => {
        subtitleSession = null;
        const itemId = await updateSubtitleButton();
        if (itemId) subtitleDialog(itemId);
    };
    controlsMenu.append(subtitleButton);
    const libraryId = value => /^[a-f0-9]{32}$/i.test(String(value || '').replaceAll('-', '')) ? String(value).replaceAll('-', '').toLowerCase() : null;
    let subtitleGeneration = 0, subtitleOwner, subtitleClient, subtitleItemCache = new Map(), subtitleSession;
    async function updateSubtitleButton() {
        const generation = ++subtitleGeneration, client = window.ApiClient, owner = client?.getCurrentUserId?.();
        if (owner !== subtitleOwner || client !== subtitleClient) {
            subtitleItemCache.clear(); subtitleSession = null; subtitleButton.hidden = true;
            subtitleOwner = owner; subtitleClient = client;
        }
        const current = () => generation === subtitleGeneration && owner === window.ApiClient?.getCurrentUserId?.() && client === window.ApiClient;
        const fullscreen = document.fullscreenElement;
        const host = fullscreen && fullscreen.tagName !== 'VIDEO' ? fullscreen : document.body;
        mountControls();
        const route = location.hash.replace(/^#!?/, '') || location.pathname.replace(/^.*\/web\/?/, '/');
        const [page, query = ''] = route.split('?');
        const detailPage = /^\/?details(?:\.html)?\/?$/.test(page);
        const videoPage = /^\/?(?:video|videoosd|videoplayer)(?:\.html)?\/?$/.test(page);
        const video = [...document.querySelectorAll('video')].find(node => node.getClientRects().length && !node.closest('.hide,[hidden],[aria-hidden="true"]'));
        if (!owner || (!detailPage && !videoPage && !video)) {
            subtitleButton.hidden = true; delete subtitleButton.dataset.itemId; return;
        }
        let itemId = libraryId(new URLSearchParams(query || location.search).get('id'));
        try {
            if (video) {
                const source = video.currentSrc || video.src || '';
                const fromSource = libraryId(source.match(/\/Videos\/([a-f0-9-]{32,36})\//i)?.[1]);
                if (fromSource) itemId = fromSource;
                else if (source || !itemId) {
                    // Blob streams need this device's current session, not a stale detail URL.
                    const key = owner+':'+source;
                    if (!subtitleSession || subtitleSession.key !== key || Date.now()-subtitleSession.time > 5000) {
                        subtitleSession = { key, time: Date.now(), value: Promise.resolve(window.JellyfinEnhanced?.internals?.nowPlaying?.itemIdFromSession?.(video)) };
                    }
                    itemId = libraryId(await subtitleSession.value);
                }
            }
            if (!current()) return;
            if (subtitleButton.dataset.itemId !== itemId) subtitleButton.hidden = true;
            if (!itemId) { subtitleButton.hidden = true; delete subtitleButton.dataset.itemId; return; }
            let cached = subtitleItemCache.get(itemId);
            if (!cached || Date.now()-cached.time > 60000) {
                cached = { time: Date.now(), value: Promise.resolve(client.getItem(owner, itemId)) };
                subtitleItemCache.set(itemId, cached);
            }
            const item = await cached.value;
            if (!current()) return;
            subtitleButton.dataset.itemId = itemId;
            subtitleButton.hidden = !['Movie', 'Episode'].includes(item?.Type);
            if (!subtitleButton.hidden) return itemId;
        } catch {
            if (current()) { subtitleButton.hidden = true; subtitleItemCache.delete(itemId); }
        }
    }
    for (const event of ['hashchange', 'popstate', 'je:navigate']) window.addEventListener(event, updateSubtitleButton);
    for (const event of ['viewshow', 'visibilitychange', 'fullscreenchange', 'je:user-changed']) document.addEventListener(event, updateSubtitleButton);
    for (const event of ['loadedmetadata', 'play', 'emptied']) document.addEventListener(event, e => {
        if (e.target.tagName === 'VIDEO') { subtitleSession = null; updateSubtitleButton(); }
    }, true);
    every(updateSubtitleButton, 1000); updateSubtitleButton();

    // Intercept the API module's assignment synchronously: search components capture
    // requestMedia when they initialize, so polling after initialization is too late.
    window.MediaPicker = { api, element, dialog, choose, history, playItem, every };
    const je = window.JellyfinEnhanced;
    const removeRandomButton = () => document.querySelectorAll('#randomItemButtonContainer,#randomItemButton').forEach(node => node.remove());
    Object.defineProperty(je, 'addRandomButton', {configurable: true,
        get: () => removeRandomButton, set: () => removeRandomButton()});
    removeRandomButton();
    function install(requestAPI) {
        const search = requestAPI.search;
        if (search) requestAPI.search = async function(...args) {
            const empty = () => ({results: [], page: args[1] || 1, totalPages: 0, totalResults: 0});
            if (window.MediaPicker.isMusicSearch?.()) return empty();
            const result = await search.apply(this, args);
            return window.MediaPicker.isMusicSearch?.() ? empty() : result;
        };
        requestAPI.requestMedia = async (id, kind, settings = {}, is4k = false, data = null) => {
            const seasons = kind === 'tv' ? (await je.jellyseerrAPI.fetchTvShowDetails(id)).seasons.map(s => s.seasonNumber).filter(n => n > 0) : [];
            return choose({ ...settings, mediaId: Number(id), mediaType: kind, is4k }, seasons);
        };
        requestAPI.requestTvSeasons = (id, seasons, settings = {}, data = null, is4k = false) =>
            choose({ ...settings, mediaId: Number(id), mediaType: 'tv', is4k }, seasons);
        if (!document.querySelector('.mr-release-history')) {
            const launcher = element('button', 'Download status', 'mr-launcher mr-release-history'); launcher.onclick = history;
            controlsMenu.append(launcher);
        }
        window.mediaReleasePickerReady = true;
        return requestAPI;
    }
    let requestAPI = je.jellyseerrAPI;
    Object.defineProperty(je, 'jellyseerrAPI', { configurable: true,
        get: () => requestAPI, set: value => { requestAPI = install(value); } });
    if (requestAPI) requestAPI = install(requestAPI);
    // The search component captures this renderer during initialization.
    // Delegate before it installs its old double-tap filter handlers.
    const iconUIs = new WeakSet();
    function installSearchIcon(ui) {
        if (!ui || iconUIs.has(ui)) return ui;
        let render = ui.updateJellyseerrIcon;
        const wrapped = function(...args) {
            if (window.MediaPicker.updateSearchIcon?.()) return;
            return render.apply(this, args);
        };
        Object.defineProperty(ui, 'updateJellyseerrIcon', { configurable: true,
            get: () => typeof render === 'function' ? wrapped : render,
            set: value => { if (value !== wrapped) render = value; } });
        iconUIs.add(ui);
        return ui;
    }
    let searchUI = installSearchIcon(je.jellyseerrUI);
    Object.defineProperty(je, 'jellyseerrUI', { configurable: true,
        get: () => searchUI, set: value => { searchUI = installSearchIcon(value); } });
    let translate = je.t;
    const manualTranslate = (key, ...args) => {
        if (['jellyseerr_results_title', 'jellyseerr_discover_title'].includes(key)) return 'Movies & series to download';
        if (['jellyseerr_btn_request', 'jellyseerr_modal_request'].includes(key)) return 'Choose release';
        if (key === 'jellyseerr_modal_toast_request_success') return 'Selection saved. Check Download status for its status.';
        return translate.call(je, key, ...args);
    };
    Object.defineProperty(je, 't', { configurable: true,
        get: () => manualTranslate,
        set: value => { if (value !== manualTranslate) translate = value; } });
})();
