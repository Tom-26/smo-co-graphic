/* Shared rendering and authoritative state connection. No external dependencies. */
(() => {
  'use strict';
  const period = p => ({'1':'1 ПЕРИОД','2':'2 ПЕРИОД','3':'3 ПЕРИОД',OT:'ОВЕРТАЙМ',SO:'БУЛЛИТЫ'}[p] || '');
  const clock = ms => { const s = Math.ceil(Math.max(0, ms) / 1000); return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); };
  function createBoard(parent) {
    const make = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls; if (text) n.textContent = text; return n; };
    const board = make('div','scorebug');
    const brand = make('div','bug-brand');
    const brandName = make('b','brand-name','SMO&CO');
    brand.append(brandName,make('span','live-label','LIVE'));
    const main = make('div','bug-main');
    function side(cls) {
      const el = make('div','bug-team '+cls), logo = make('img','team-logo'), initial = make('span','team-initial'), name = make('span','team-name');
      logo.alt = ''; el.append(logo, initial, name); return {el,logo,initial,name};
    }
    const home = side('home'), away = side('away'), scores = make('div','bug-score');
    const hs = make('span','','0'), sep = make('span','score-sep',':'), as = make('span','','0');
    scores.append(hs,sep,as);
    const timing = make('div','bug-timing'), p = make('span','bug-period','1 ПЕРИОД'), t = make('span','bug-clock','20:00');
    timing.append(p,t); main.append(home.el,scores,away.el,timing);
    const caption = make('div','bug-caption'), penaltyBar = make('div','bug-penalties');
    const penaltyGroups = {};
    for (const side of ['home','away']) {
      const group = make('div','bug-penalty-team '+side);
      penaltyGroups[side] = group; penaltyBar.append(group);
    }
    let lastState = null, penaltyNodes = [];
    function tickPenalties(ms) {
      if (!lastState) return;
      const elapsed = lastState.running ? Math.max(0,lastState.remainingMs-ms) : 0;
      let visible = 0;
      for (const item of penaltyNodes) {
        const remaining = Math.max(0,item.data.remainingMs-elapsed);
        item.row.hidden = remaining <= 0;
        item.time.textContent = clock(remaining);
        if (remaining > 0) visible++;
      }
      penaltyBar.hidden = visible === 0;
      for (const group of Object.values(penaltyGroups)) group.hidden = !Array.from(group.children).some(row=>!row.hidden);
    }
    board.append(brand,main,penaltyBar,caption); parent.append(board);
    return {
      update(state, ms) {
        lastState = state; penaltyNodes = [];
        for (const side of ['home','away']) {
          const group = penaltyGroups[side]; group.replaceChildren();
          group.style.setProperty('--team',state[side].color);
          for (const data of (state.penalties?.[side] || [])) {
            const row=make('div','bug-penalty');
            const label=make('span','bug-penalty-player', data.player ? '№ '+data.player : 'ШТРАФ');
            const time=make('b','bug-penalty-clock');
            row.append(label,time); group.append(row); penaltyNodes.push({row,time,data});
          }
        }
        tickPenalties(ms);
        brandName.textContent = state.brand; caption.textContent = state.caption;
        caption.hidden = !state.caption;
        for (const [nodes, data] of [[home,state.home],[away,state.away]]) {
          nodes.name.textContent = data.name;
          nodes.el.style.setProperty('--team',data.color);
          nodes.initial.textContent = data.name.trim().slice(0,1);
          nodes.logo.hidden = !data.logo; nodes.initial.hidden = !!data.logo;
          if (data.logo && nodes.logo.getAttribute('src') !== data.logo) nodes.logo.src = data.logo;
          if (!data.logo) nodes.logo.removeAttribute('src');
        }
        hs.textContent = state.home.score; as.textContent = state.away.score;
        p.textContent = period(state.period); t.textContent = clock(ms);
        board.classList.toggle('clock-running',state.running && ms > 0);
        board.classList.toggle('clock-zero',ms <= 0);
        board.classList.toggle('off-air',!state.visible);
      },
      tick(ms) { tickPenalties(ms); t.textContent = clock(ms); board.classList.toggle('clock-zero',ms <= 0); }
    };
  }
  function connect(onState, onConnection) {
    let state = null, anchor = 0, at = 0, seen = 0, token = '', online = false;
    function accept(next) {
      const restarted = state && next.instanceId !== state.instanceId;
      if (state && !restarted && next.revision < state.revision) return;
      if (restarted) token = '';
      // Correct the display only from server snapshots; performance.now avoids local clock jumps.
      state = next; anchor = next.remainingMs; at = performance.now(); seen = at;
      if (!online) { online = true; onConnection(true); }
      onState(next);
    }
    const events = new EventSource('/api/events');
    events.addEventListener('state', event => { try { accept(JSON.parse(event.data)); } catch (e) { console.error(e); } });
    events.onerror = () => { online = false; onConnection(false); };
    setInterval(() => { if (seen && performance.now()-seen > 2500 && online) { online = false; onConnection(false); } },500);
    async function getToken() {
      const r = await fetch('/api/session',{cache:'no-store',signal:AbortSignal.timeout(4000)});
      if (!r.ok) throw Error('Сервер недоступен');
      token = (await r.json()).token;
    }
    return {
      get state() { return state; },
      get online() { return online; },
      remaining() { return state ? Math.max(0,anchor-(state.running ? performance.now()-at : 0)) : 0; },
      penalties() {
        const elapsed = state?.running ? Math.max(0,state.remainingMs-this.remaining()) : 0;
        return Object.fromEntries(['home','away'].map(side => [side,(state?.penalties?.[side] || [])
          .map(p=>({...p,remainingMs:Math.max(0,Math.ceil(p.remainingMs-elapsed))})).filter(p=>p.remainingMs>0)]));
      },
      async command(action,value) {
        if (!online) throw Error('Нет связи с сервером. Дождитесь подключения.');
        if (!token) await getToken();
        const id = crypto.randomUUID();
        let r;
        const submit = () => fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Scoreboard-Token':token},
            body:JSON.stringify({id,action,value}),signal:AbortSignal.timeout(5000)});
        try {
          r = await submit();
          if (r.status === 403) { await r.text(); await getToken(); r = await submit(); }
        } catch {
          throw Error('Нет подтверждения команды. Проверьте табло перед повторным нажатием.');
        }
        const data = await r.json();
        if (!r.ok) { if (r.status === 403) token = ''; throw Error(data.error || 'Не удалось выполнить команду'); }
        accept(data); return data;
      }
    };
  }
  window.Scoreboard = {period,clock,createBoard,connect};
})();
