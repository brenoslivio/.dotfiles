/* Music uses Lidarr's catalogue and explicit album-release selections. */
(() => {
    'use strict';
    if (window.mediaMusicLoaded) return;
    window.mediaMusicLoaded = true;
    const {api, element: el, dialog, playItem, every} = window.MediaPicker;
    const owner = () => window.ApiClient?.getCurrentUserId?.();
    const button = (label, action) => { const b = el('button', label); b.type = 'button'; b.onclick = action; return b; };
    const qualityNames = {'flac':'FLAC', 'mp3-320':'MP3 320 kbps', 'mp3-v0':'MP3 V0', 'any':'Any supported quality'};
    const style = el('style'); style.textContent = '.mm-search{display:flex;gap:8px;flex-wrap:wrap}.mm-search input{flex:1;min-width:120px;padding:10px;font:inherit}.mm-cover{width:110px;float:left;margin:0 16px 12px 0;border-radius:8px}.mm-content{clear:both}.mm-releases summary{padding:12px;cursor:pointer}.mm-tracklist{max-height:200px;overflow:auto}.mm-search select{max-width:100%}'; document.head.append(style);
    style.textContent += '.mm-search-scope{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0;padding-inline-start:3.3%;color:inherit}.mm-search-scope select{background:#293449;color:white;border:1px solid #62718a;border-radius:7px;padding:10px;min-height:44px;font:inherit;cursor:pointer}.mm-search-scope[hidden]{display:none}';
    style.textContent += `
      #jellyseerr-search-icon.mm-mode-icon{display:grid;place-items:center;position:absolute;right:10px;top:68%;transform:translateY(-50%);width:44px;height:44px;padding:7px;background:transparent;border:0;cursor:pointer;opacity:1;filter:none}
      #searchPage .inputContainer:has(.mm-mode-icon){position:relative}
      #jellyseerr-search-icon.mm-mode-icon img{width:30px;height:30px;object-fit:contain}
      #searchPage .inputContainer:has(.mm-mode-icon) #searchTextInput{padding-right:62px;box-sizing:border-box}
      .mm-artist-art{border-radius:50%;font-size:3rem;color:#b8d9e9}
      #jellyseerr-search-icon.mm-mode-icon:focus-visible,.mm-search-scope select:focus-visible,.mm-album-card:focus-visible{outline:3px solid #8bdcff;outline-offset:3px}
      .mm-results[hidden]{display:none}.mm-results{padding:0 3.3%;margin:20px 0}
      .mm-album-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:20px}
      .mm-album-card{display:flex;flex-direction:column;gap:7px;text-align:left;border:0;border-radius:8px;background:transparent;color:inherit;padding:0;min-width:0;font:inherit;cursor:pointer}
      .mm-album-card>strong,.mm-album-card>span{max-width:100%;overflow-wrap:anywhere}
      .mm-artwork{display:grid;place-items:center;position:relative;aspect-ratio:1;width:100%;background:#293449;border-radius:8px;overflow:hidden}
      .mm-artwork img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
      .mm-cover-fallback{padding:14px;text-align:center;color:#c5ccda}
      #searchPage.mm-music-mode .verticalSection,#searchPage.mm-music-mode .noItemsMessage,
      #searchPage.mm-music-mode .jellyseerr-no-results-message,#searchPage.mm-music-mode .alphaPicker{display:none!important}
      #searchPage.mm-video-mode .verticalSection:has([data-type="MusicAlbum" i],[data-type="MusicArtist" i],[data-type="Audio" i]){display:none!important}
      @media(max-width:480px){.mm-album-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.mm-search-scope{gap:8px}}
    `;
    function view(title) {
        const v = dialog(title); v.owner = owner(); v.panel.dataset.musicDialog = 'true';
        v.status = el('p', '', 'mr-status'); v.status.setAttribute('role', 'status'); v.panel.append(v.status);
        v.current = () => v.panel.isConnected && v.owner === owner();
        v.call = async (path, data) => {
            if (!v.current()) throw new Error('Account changed. Reopen music.');
            const result = await api(path, data);
            if (!v.current()) throw new Error('Account changed. Reopen music.');
            return result;
        };
        v.fail = error => { if (v.current()) v.status.textContent = error.message; };
        return v;
    }
    function cover(id, parent) {
        if (!/^[a-f0-9-]{36}$/i.test(id)) return;
        const img = el('img'); img.className = 'mm-cover'; img.alt = 'Album cover'; img.loading = 'lazy';
        img.referrerPolicy = 'no-referrer'; img.src = 'https://coverartarchive.org/release-group/'+id+'/front-250';
        img.onerror = () => img.remove(); parent.append(img);
    }
    async function album(id, title, findReleases = false) {
        const v = view(title); v.status.textContent = 'Loading album and track metadata…';
        try {
            const result = await v.call('music-album', {id});
            cover(id, v.panel);
            v.panel.append(el('p', [result.artist, result.year, result.description].filter(Boolean).join(' · ')));
            const tracks = el('details'), trackList = el('ol', undefined, 'mm-tracklist'); tracks.append(el('summary', `${result.tracks.length} catalogue tracks`));
            for (const track of result.tracks) trackList.append(el('li', [track.disc ? `Disc ${track.disc}` : '', track.number, track.title].filter(Boolean).join(' · ')));
            tracks.append(trackList); v.panel.append(tracks);
            if (result.editions.length) {
                const editions = el('details'); editions.append(el('summary', 'Catalogue editions'));
                for (const edition of result.editions.slice(0, 30)) editions.append(el('p', [edition.format, (edition.country || []).join('/'), edition.description, `${edition.tracks || '?'} tracks`].filter(Boolean).join(' · ')));
                v.panel.append(editions);
            }
            const form = el('div', undefined, 'mm-search mm-content'), quality = el('select'); quality.setAttribute('aria-label','Music quality');
            for (const [value,label] of Object.entries(qualityNames)) { const o=el('option',label); o.value=value; quality.append(o); }
            const results = el('div', undefined, 'mm-releases');
            const search = button('Find releases', async () => {
                search.disabled = true; quality.disabled = true; results.replaceChildren(); v.status.textContent = 'Searching music indexers…';
                try {
                    const data = await v.call('music-releases', {id, quality:quality.value});
                    const rejected = el('details'), rejectedList = el('div');
                    let usable = 0, excluded = 0;
                    for (const release of [...data.releases].sort((a,b)=>(b.seeders ?? -1)-(a.seeders ?? -1))) {
                        const row = el('div', undefined, 'mr-row'), info = el('div');
                        info.append(el('strong', release.title), el('div', `${release.quality} · ${(release.size/1024**2).toFixed(0)} MiB · ${release.seeders ?? '?'} seeders · ${release.indexer || 'Unknown indexer'}`));
                        for (const warning of release.warnings || []) info.append(el('p',warning));
                        row.append(info);
                        if (release.rejections.length) { info.append(el('p', release.rejections.join(' '))); rejectedList.append(row); excluded++; }
                        else { row.append(button('Download this release', () => { if (v.current()) confirmDownload(release, title); })); results.append(row); usable++; }
                    }
                    if (excluded) { rejected.append(el('summary', `Show ${excluded} rejected releases`), rejectedList); results.append(rejected); }
                    v.status.textContent = usable ? 'Choose a release. Music downloads shows detected audio details after import.' : excluded ? 'Downloads were found, but none match this quality or pass the import checks. Try another quality or open the rejected releases below.' : 'This album is in the catalogue, but the music indexers returned no downloads. Try another album or check indexer availability in Lidarr.';
                } catch (error) { v.fail(error); } finally { search.disabled = false; quality.disabled = false; }
            });
            form.append(quality, search); v.panel.append(form, results);
            v.status.textContent = result.importedTracks ? `${result.importedTracks} tracks already imported. Remove the album before replacing it.` : 'Nothing downloads until you choose and confirm a release.';
            search.disabled = !!result.importedTracks;
            if (findReleases && !search.disabled) search.click();
        } catch (error) { v.fail(error); }
    }
    function confirmDownload(release, title) {
        const v = view('Download '+title+'?'); v.panel.append(el('p', release.title), el('p', release.quality));
        for (const warning of release.warnings || []) v.panel.append(el('p',warning));
        const confirm = button('Confirm download', async () => {
            confirm.disabled = true; v.status.textContent = 'Verifying and submitting your chosen release…';
            try { const result = await v.call('music-select', {id:release.id}); v.status.textContent = result.message; document.dispatchEvent(new Event('media:music-changed')); }
            catch (error) { v.fail(error); } // An uncertain POST must never be retried automatically.
        }); v.actions.append(confirm);
    }
    async function removeAlbum(id, refresh, replacementTitle) {
        const replacing = replacementTitle !== undefined;
        const v = view(replacing ? 'Choose another release?' : 'Remove album from server?'); v.status.textContent = 'Checking this album’s files and downloads…';
        try {
            const result = await v.call('music-removal-preview', {id});
            if (replacing && result.files) throw new Error('Tracks have already been imported. Refresh Requests before replacing this album.');
            v.panel.append(el('strong', result.title), el('p', `${result.files} imported files and ${result.downloads} matched downloads will be removed for everyone.`));
            v.status.textContent = result.retry ? 'Retry the remaining steps of this removal.' : replacing ? 'Remove this unfinished download and its partial files, then choose a different release. Nothing new downloads automatically.' : 'This permanently deletes the selected album.';
            const confirm = button(result.retry ? 'Retry removal' : replacing ? 'Remove download and find releases' : 'Delete album permanently', async () => {
                confirm.disabled = true;
                try {
                    const done = await v.call('music-remove', {id:result.id}); v.status.textContent = done.message; refresh();
                    document.dispatchEvent(new Event('media:music-changed'));
                    if (replacing && v.current()) album(id, replacementTitle, true);
                }
                catch (error) { v.fail(error); confirm.disabled = false; }
            }); v.actions.append(confirm);
        } catch (error) { v.fail(error); }
    }
    function musicRow(row, canRemove, user, refresh, showAudio = false) {
        const card = el('div', undefined, 'mr-row'), info = el('div'), actions = el('div');
        const current = () => owner() === user && card.isConnected;
        info.append(el('strong', `${row.artist} — ${row.title}`), el('p', `${row.quality} · ${row.message}`));
        if (row.percent != null && row.percent < 100 && !row.itemId) {
            const progress = el('progress'); progress.max = 100; progress.value = row.percent;
            progress.setAttribute('aria-label', 'Music download progress'); info.append(progress);
        }
        if (row.importedTracks) info.append(el('p', `${row.importedTracks} tracks imported`));
        if (showAudio && row.audio?.length) info.append(el('p', 'Imported audio: '+row.audio.join('; ')));
        if (row.itemId) actions.append(button('Listen', () => {
            if (current()) playItem(row.itemId, user).catch(error => { if (current()) info.append(el('p', error.message)); });
        }));
        if (canRemove && row.canChooseAlternative) actions.append(button('Choose another release', () => {
            if (current()) removeAlbum(row.albumId, refresh, row.title);
        }));
        if (canRemove) actions.append(button('Remove album', () => { if (current()) removeAlbum(row.albumId, refresh); }));
        card.append(info, actions); return card;
    }
    function downloads() {
        const v = view('Music downloads'), list = el('div'), admin = el('div'); let busy = false;
        v.panel.append(list, admin);
        const refresh = async () => {
            if (busy || !v.current()) return;
            busy = true;
            try {
                const data = await v.call('music-status'); list.replaceChildren();
                v.status.textContent = data.selections.length ? 'Your music selections. Refreshes every 15 seconds.' : 'No music downloads selected yet.';
                for (const row of data.selections) list.append(musicRow(row, data.canRemove, v.owner, refresh, true));
                // Preserve the administrator's selected option between automatic refreshes.
                const selected = admin.querySelector('select')?.value; admin.replaceChildren();
                if (data.canRemove && data.albums.length) {
                    const select = el('select'); select.setAttribute('aria-label','Album to remove');
                    for (const row of data.albums.sort((a,b)=>(a.artist+a.title).localeCompare(b.artist+b.title))) { const o=el('option', `${row.artist} — ${row.title}`); o.value=row.id; select.append(o); }
                    if ([...select.options].some(o=>o.value===selected)) select.value=selected;
                    admin.append(el('h3','Manage music library'), select, button('Remove selected album',()=>{ if (v.current()) removeAlbum(select.value,refresh); }));
                }
            } catch (error) { v.fail(error); } finally { busy=false; }
        };
        v.actions.append(button('Refresh',refresh)); refresh();
        const stop=every(()=>{ if (!v.current()) stop(); else return refresh(); },15000);
    }
    window.MediaPicker.renderMusicActivity=(list,data,user)=>{
        if (!data?.selections?.length || owner()!==user) return;
        list.append(el('h3','Music requests'));
        const refresh = () => document.dispatchEvent(new Event('media:music-changed'));
        for (const row of data.selections) list.append(musicRow(row, data.canRemove, user, refresh));
    };
    const searchButton=button('Search music',()=>{
        mode='music'; invalidateSearch();
        const input=document.querySelector('#searchPage:not(.hide) #searchTextInput');
        if (!input) location.hash='/search';
        searchScope(); input?.focus();
    }), downloadsButton=button('Music downloads',downloads);
    for (const b of [searchButton,downloadsButton]) { b.classList.add('mr-launcher'); b.hidden=true; document.querySelector('#media-controls-menu')?.append(b); }
    let lastOwner, retryAt=0, pending=false, musicAllowed=false;
    let mode='video', kind='album', mounted=null, timer=null, version=0, lastQuery=null;
    window.MediaPicker.isMusicSearch=()=>mode==='music' && musicAllowed && owner()===lastOwner
        && !!document.querySelector('#searchPage:not(.hide) #searchTextInput');
    function invalidateSearch() { clearTimeout(timer); version++; lastQuery=null; }
    function renderAlbums(grid, items, current) {
        grid.replaceChildren();
        for (const item of items.filter(item=>item.kind==='album')) {
            const card=button('',()=>{ if (current()) album(item.id,item.title); }); card.className='mm-album-card';
            card.setAttribute('aria-label',`Open album ${item.title}${item.artist ? ' by '+item.artist : ''}`);
            const artwork=el('span',undefined,'mm-artwork'), fallback=el('span','No cover available','mm-cover-fallback');
            artwork.append(fallback);
            if (/^[a-f0-9-]{36}$/i.test(item.id)) {
                const img=el('img'); img.alt=item.title+' cover'; img.loading='lazy'; img.referrerPolicy='no-referrer';
                img.src='https://coverartarchive.org/release-group/'+item.id+'/front-250';
                img.onload=()=>{ fallback.hidden=true; }; img.onerror=()=>img.remove(); artwork.append(img);
            }
            card.append(artwork,el('strong',item.title),el('span',[item.artist,item.year].filter(Boolean).join(' · ')));
            grid.append(card);
        }
    }
    async function artist(id, title) {
        const v=view(title+' — albums'), grid=el('div',undefined,'mm-album-grid'); v.panel.append(grid);
        const refresh=button('Refresh albums',async()=>{
            refresh.disabled=true; v.status.textContent='Loading albums…';
            try {
                const result=await v.call('music-artist',{id}); renderAlbums(grid,result.items,v.current);
                v.status.textContent=result.message || 'Select an album cover to choose its quality and release.';
            } catch(error) { v.fail(error); } finally { refresh.disabled=false; }
        });
        v.actions.append(refresh); refresh.click();
    }
    function renderArtists(grid, items, current) {
        grid.replaceChildren();
        for (const item of items) {
            const card=button('',()=>{ if (current()) artist(item.id,item.title); }); card.className='mm-album-card';
            card.setAttribute('aria-label','Browse albums by '+item.title);
            const initials=item.title.split(/\s+/).slice(0,2).map(word=>word[0] || '').join('');
            const art=el('span',initials,'mm-artwork mm-artist-art'); art.setAttribute('aria-hidden','true');
            card.append(art,el('strong',item.title),el('span',item.description || 'Browse albums')); grid.append(card);
        }
    }
    function setMode(value) {
        if (!musicAllowed || owner()!==lastOwner || mode===value) return;
        mode=value; invalidateSearch(); searchScope();
        if (mode==='video' && mounted) {
            mounted.input.dispatchEvent(new Event('input',{bubbles:true}));
            document.dispatchEvent(new CustomEvent('jellyseerr-manual-refresh'));
        }
    }
    function updateSearchIcon() {
        const page=document.querySelector('#searchPage:not(.hide)'), input=page?.querySelector('#searchTextInput');
        if (!input || !musicAllowed || !owner() || owner()!==lastOwner) return false;
        const anchor=input.closest('.inputContainer') || input.parentElement;
        let icon=page.querySelector('#jellyseerr-search-icon');
        if (!icon?.classList.contains('mm-mode-icon')) {
            // Replacing the old image discards its touch, double-tap and keyboard handlers.
            const replacement=button('',()=>setMode(mode==='music' ? 'video' : 'music'));
            replacement.id='jellyseerr-search-icon'; replacement.className='jellyseerr-icon mm-mode-icon';
            replacement.append(el('img')); replacement.addEventListener('dblclick',event=>{event.preventDefault();event.stopPropagation();});
            if (icon) icon.replaceWith(replacement); else anchor.append(replacement);
            icon=replacement;
        }
        const music=mode==='music', name=music ? 'Lidarr' : 'Seerr';
        const label=music ? 'Music search. Switch to movies and series' : 'Movies and series search. Switch to music';
        if (icon.title!==label) { icon.title=label; icon.setAttribute('aria-label',label); }
        if (icon.getAttribute('aria-pressed')!==String(music)) icon.setAttribute('aria-pressed',String(music));
        const img=icon.querySelector('img'), src=window.ApiClient.getUrl('JellyfinEnhanced/cdn/selfhst/svg/'+name.toLowerCase()+'.svg');
        if (img.getAttribute('src')!==src) { img.src=src; img.alt=name; }
        return true;
    }
    window.MediaPicker.updateSearchIcon=updateSearchIcon;
    function scheduleSearch(immediate=false) {
        if (!mounted || mode!=='music' || !musicAllowed) return;
        const {page,input,status,grid}=mounted, query=input.value.trim(), user=owner(), searchKind=kind;
        const key=searchKind+':'+query;
        if (lastQuery===key) return;
        invalidateSearch(); lastQuery=key;
        const request=version;
        const current=()=>request===version && owner()===user && musicAllowed && mode==='music' && kind===searchKind
            && mounted?.input===input && page.isConnected && !page.classList.contains('hide') && input.value.trim()===query;
        grid.replaceChildren();
        const label=searchKind==='artist' ? 'artists' : 'albums';
        if (query.length<2) { status.textContent='Search for music '+label+' using the search bar above.'; return; }
        if (query.length>100) { status.textContent='Use a search of 100 characters or fewer.'; return; }
        status.textContent='Searching '+label+'…';
        timer=setTimeout(async()=>{
            if (!current()) return;
            try {
                const result=await api('music-search',{query,kind:searchKind});
                if (!current()) return;
                const items=result.items.filter(item=>item.kind===searchKind);
                (searchKind==='artist' ? renderArtists : renderAlbums)(grid,items,current);
                const count=items.length, noun=count===1 ? searchKind : label;
                status.textContent=[count ? `${count} ${noun}. `+(searchKind==='artist' ? 'Select an artist to browse their albums.' : 'Select a cover to choose a download.') : 'No '+label+' found. Try another name.',...(result.warnings || [])].join(' ');
            } catch(error) { if (current()) status.textContent=error.message; }
        },immediate ? 0 : 350);
    }
    function searchScope() {
        const page=document.querySelector('#searchPage:not(.hide)'), input=page?.querySelector('#searchTextInput');
        if (mounted && (mounted.input!==input || !mounted.scope.isConnected || !mounted.results.isConnected || !musicAllowed || !owner())) {
            invalidateSearch(); mounted.page.classList.remove('mm-music-mode','mm-video-mode');
            mounted.input.placeholder=mounted.placeholder;
            mounted.page.querySelector('#jellyseerr-search-icon.mm-mode-icon')?.remove();
            mounted.scope.remove(); mounted.results.remove(); mounted=null;
        }
        if (!input || !owner() || !musicAllowed) return;
        if (!mounted) {
            const scope=el('div',undefined,'mm-search-scope'); scope.id='media-music-search-scope';
            const label=el('label','Search for '), select=el('select'); select.setAttribute('aria-label','Music search type');
            for (const [value,text] of [['album','Albums'],['artist','Artists']]) { const option=el('option',text); option.value=value; select.append(option); }
            select.value=kind; select.onchange=()=>{kind=select.value;invalidateSearch();searchScope();}; label.append(select); scope.append(label);
            const results=el('section',undefined,'mm-results');
            const status=el('p'); status.setAttribute('role','status');
            const grid=el('div',undefined,'mm-album-grid'); results.append(status,grid);
            const fields=page.querySelector('.searchFields');
            if (fields) fields.after(scope); else input.after(scope);
            scope.after(results);
            mounted={page,input,scope,results,status,grid,select,placeholder:input.placeholder};
        }
        const active=mode==='music';
        page.classList.toggle('mm-music-mode',active); page.classList.toggle('mm-video-mode',!active);
        mounted.results.hidden=mounted.scope.hidden=!active;
        mounted.results.setAttribute('aria-label',kind==='artist' ? 'Music artists' : 'Music albums');
        input.placeholder=active ? (kind==='artist' ? 'Search music artists' : 'Search music albums') : 'Search movies & series';
        updateSearchIcon();
        if (active) scheduleSearch();
    }
    // Keep Jellyfin's controlled input and URL state in sync. Its local library
    // results stay hidden; the picker suppresses Seerr catalogue calls in music mode.
    document.addEventListener('input',event=>{
        if (event.target===mounted?.input && mode==='music' && musicAllowed) {
            if (!event.isComposing) scheduleSearch();
        }
    },true);
    document.addEventListener('keydown',event=>{
        if (event.target===mounted?.input && mode==='music' && event.key==='Enter') {
            event.preventDefault(); event.stopImmediatePropagation(); invalidateSearch(); scheduleSearch(true);
        }
    },true);
    async function update() {
        const user=owner();
        if (user!==lastOwner) {
            lastOwner=user; retryAt=0; pending=false; musicAllowed=false; mode='video'; kind='album'; invalidateSearch();
            document.querySelectorAll('[data-music-dialog]').forEach(n=>n.closest('.mr-overlay')?.remove());
            searchButton.hidden=downloadsButton.hidden=true;
        }
        searchScope();
        if (!user || pending || Date.now()<retryAt) return;
        pending=true; retryAt=Date.now()+30000;
        try { const result=await api('capabilities'); if (owner()===user) { musicAllowed=!!result.music; searchButton.hidden=downloadsButton.hidden=!musicAllowed; retryAt=Infinity; searchScope(); } }
        catch { /* Keep unavailable music controls hidden, retry after service recovery. */ }
        finally { if (owner()===user) pending=false; }
    }
    document.addEventListener('je:user-changed',update);
    document.addEventListener('viewshow',update); window.addEventListener('hashchange',update);
    every(update,1000); update();
})();
