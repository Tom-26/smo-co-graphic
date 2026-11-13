(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let draft = null, dirty = false, busy = false, initialized = false, toastTimer, awardPhoto = '', awardPhotoChanged = false;
  const board = Scoreboard.createBoard($('previewBoard'));
  const draftBoard = Scoreboard.createBoard($('draftPreviewBoard'));
  const preview = $('previewBoard');
  function fitPreview() {
    const css = getComputedStyle(preview);
    const width = preview.clientWidth-parseFloat(css.paddingLeft)-parseFloat(css.paddingRight);
    preview.firstElementChild.style.transform = 'scale('+Math.min(1,width/890)+')';
    fitDraftPreview();
  }
  new ResizeObserver(fitPreview).observe(preview);
  const client = Scoreboard.connect(render, connection);
  function fitDraftPreview() { const el=$('draftPreviewBoard'); if (el.firstElementChild && el.clientWidth) el.firstElementChild.style.transform='scale('+Math.min(1,el.clientWidth/890)+')'; }
  new ResizeObserver(fitDraftPreview).observe($('draftPreviewBoard'));
  const commandButtons = () => document.querySelectorAll('[data-score], [data-adjust], #startPause, #resetClock, #period, #toggleVisible, #saveSettings, #newMatch, #exportMatch, #timeForm button, [data-penalty-add], [data-penalty-remove], [data-award]');
  function toast(message, error=false) {
    clearTimeout(toastTimer); $('toast').textContent = message; $('toast').classList.toggle('error',error); $('toast').hidden = false;
    toastTimer = setTimeout(() => { $('toast').hidden = true; },error ? 9000 : 3500);
  }
  function buttons() { commandButtons().forEach(n => { n.disabled = !client.online || busy; }); }
  function connection(online) {
    $('connection').textContent = online ? 'Сервер подключён' : 'Нет связи с сервером';
    $('connection').classList.toggle('connected',online);
    $('saveStatus').textContent = online ? 'Состояние сохраняется автоматически' : 'Проверьте окно сервера';
    // connect() can call back only after construction, via EventSource.
    buttons();
  }
  async function send(action,value) {
    if (busy) return null;
    busy = true; buttons();
    try { return await client.command(action,value); }
    catch (error) { toast(error.message,true); return null; }
    finally { busy = false; buttons(); }
  }
  function render(s) {
    board.update(s,client.remaining());
    renderPenalties(s);
    for (const side of ['home','away']) {
      $(side+'Name').textContent = s[side].name; $(side+'Score').textContent = s[side].score;
      $(side+'Marker').style.backgroundColor = s[side].color;
    }
    $('period').value = s.period;
    const award=s.playerAward || {visible:false,name:'',number:'',votes:0};
    if (document.activeElement !== $('awardName')) $('awardName').value=award.name;
    if (document.activeElement !== $('awardNumber')) $('awardNumber').value=award.number;
    if (document.activeElement !== $('awardVotes')) $('awardVotes').value=award.votes;
    if (!awardPhotoChanged) { awardPhoto=award.photo || ''; $('awardPhotoPreview').src=awardPhoto; $('awardPhotoPreview').hidden=!awardPhoto; }
    $('awardStatus').textContent=award.name ? 'Победитель сохранён. Управляйте показом глазком источника в OBS.' : 'Введите победителя. Управляйте показом глазком источника в OBS.';
    $('startLabel').textContent = s.running ? 'Пауза' : 'Запустить';
    $('playIcon').textContent = s.running ? 'Ⅱ' : '▶';
    $('timerState').textContent = s.running ? 'ИДЁТ ОТСЧЁТ' : s.remainingMs === 0 ? 'ПЕРИОД ЗАВЕРШЁН' : 'ПАУЗА';
    $('timerState').classList.toggle('running',s.running);
    $('visibilityLabel').textContent = s.visible ? 'Табло в эфире' : 'Табло скрыто';
    $('toggleVisible').classList.toggle('is-hidden',!s.visible); $('hiddenNotice').hidden = s.visible;
    if (!initialized || !dirty) loadDraft(s);
    initialized = true;
    buttons();
  }
  const penaltySignatures = {};
  function renderPenalties(s) {
    for (const side of ['home','away']) {
      $(side+'PenaltyName').textContent = s[side].name;
      const rows = s.penalties?.[side] || [];
      const signature=JSON.stringify(rows.map(p=>[p.id,p.player]));
      if (penaltySignatures[side] === signature) continue;
      penaltySignatures[side] = signature;
      const list=$(side+'PenaltyList'); list.replaceChildren();
      if (!rows.length) { const empty=document.createElement('p'); empty.className='muted'; empty.textContent='Нет удалений'; list.append(empty); }
      for (const p of rows) {
        const row=document.createElement('div'); row.className='penalty-row'; row.dataset.penaltyRow=p.id;
        const player=document.createElement('span'); player.textContent=p.player ? 'Игрок № '+p.player : 'Без номера';
        const time=document.createElement('b'); time.dataset.penaltyTime=p.id; time.textContent=Scoreboard.clock(p.remainingMs);
        const remove=document.createElement('button'); remove.type='button'; remove.className='text-button danger'; remove.textContent='Снять'; remove.dataset.penaltyRemove=p.id; remove.dataset.side=side;
        remove.setAttribute('aria-label','Снять удаление — '+(p.player ? '№ '+p.player : 'без номера')+' — '+s[side].name);
        row.append(player,time,remove); list.append(row);
      }
    }
  }
  function tickPenalties() {
    const current=client.penalties();
    for (const side of ['home','away']) {
      const active=new Map(current[side].map(p=>[p.id,p.remainingMs]));
      $(side+'PenaltyList').querySelectorAll('[data-penalty-row]').forEach(row=> {
        const ms=active.get(row.dataset.penaltyRow) || 0; row.hidden=ms<=0;
        row.querySelector('[data-penalty-time]').textContent=Scoreboard.clock(ms);
      });
    }
  }
  for (const side of ['home','away']) {
    $(side+'PenaltyForm').addEventListener('submit',async e=> {
      e.preventDefault();
      const result=await send('penalty_add',{side,player:$(side+'PenaltyPlayer').value.trim(),durationSec:Number($(side+'PenaltyDuration').value)});
      if (result) { $(side+'PenaltyPlayer').value=''; toast('Удаление добавлено'); }
    });
    $(side+'PenaltyList').addEventListener('click',e=> {
      const button=e.target.closest('[data-penalty-remove]');
      if (button && !button.disabled) send('penalty_remove',{side,id:button.dataset.penaltyRemove});
    });
  }
  function thumb(side) {
    const box = $(side+'Thumb'); box.replaceChildren();
    if (draft[side].logo) { const img = document.createElement('img'); img.src = draft[side].logo; img.alt = ''; box.append(img); }
    else box.textContent = draft[side].name.slice(0,1);
  }
  function loadDraft(s) {
    draft = JSON.parse(JSON.stringify(s));
    for (const side of ['home','away']) { $(side+'Input').value = s[side].name; $(side+'Color').value = s[side].color; thumb(side); }
    $('brandInput').value = s.brand; $('captionInput').value = s.caption; $('durationInput').value = Scoreboard.clock(s.durationSec*1000);
    renderDraft();
  }
  function renderDraft() {
    if (!draft || !client.state) return;
    const state={...client.state};
    for (const side of ['home','away']) state[side]={...client.state[side],...draft[side],name:$(side+'Input').value.trim() || 'Название команды',color:$(side+'Color').value};
    state.brand=$('brandInput').value; state.caption=$('captionInput').value;
    draftBoard.update(state,client.remaining());
    fitDraftPreview();
  }
  $('editTeams').addEventListener('click',() => { $('settings').open=true; $('settings').scrollIntoView({behavior:'smooth',block:'start'}); $('homeInput').focus({preventScroll:true}); fitDraftPreview(); });
  $('swapTeams').addEventListener('click',() => {
    if (!draft) return;
    const a={name:$('homeInput').value,color:$('homeColor').value,logo:draft.home.logo};
    const b={name:$('awayInput').value,color:$('awayColor').value,logo:draft.away.logo};
    for (const [side,team] of [['home',b],['away',a]]) { $(side+'Input').value=team.name; $(side+'Color').value=team.color; draft[side].logo=team.logo; thumb(side); }
    dirty=true; $('settingsHint').textContent='Команды поменяны местами. Сохраните настройки.'; renderDraft();
  });
  $('discardSettings').addEventListener('click',() => { if (!client.state) return; dirty=false; loadDraft(client.state); $('settingsHint').textContent='Изменения отменены'; });
  function parseTime(text, allowZero=true) {
    if (!/^\d{1,2}:[0-5]\d$/.test(text.trim())) throw Error('Введите время в формате ММ:СС, например 20:00. Максимум 99:59.');
    const [m,s] = text.trim().split(':').map(Number), result = m*60+s;
    if (!allowZero && result === 0) throw Error('Длительность периода должна быть больше нуля.');
    return result;
  }
  async function confirmAction(title,text) {
    $('dialogTitle').textContent = title; $('dialogText').textContent = text;
    return new Promise(resolve => { const d = $('confirmDialog'); d.returnValue = ''; d.addEventListener('close',() => resolve(d.returnValue==='confirm'),{once:true}); d.showModal(); });
  }
  document.querySelectorAll('[data-score]').forEach(b => b.addEventListener('click',() => send('score',{side:b.dataset.score,delta:Number(b.dataset.delta)})));
  document.querySelectorAll('[data-adjust]').forEach(b => b.addEventListener('click',() => send('adjust',Number(b.dataset.adjust))));
  $('startPause').addEventListener('click',() => {
    if (!client.state) return;
    if (!client.state.running && client.remaining() <= 0) return toast('Время закончилось. Сбросьте таймер или установите время.',true);
    send(client.state.running ? 'pause' : 'start');
  });
  $('resetClock').addEventListener('click',async () => { if (await confirmAction('Сбросить время?', 'Таймер остановится и вернётся к длительности периода. Счёт и период сохранятся.')) send('reset_clock'); });
  $('toggleVisible').addEventListener('click',() => send('visible',!client.state.visible));
  $('period').addEventListener('change',async e => { const value=e.target.value; const result=await send('period',value); if (!result && client.state) e.target.value=client.state.period; });
  $('timeForm').addEventListener('submit',async e => { e.preventDefault(); try { if (await send('set_time',parseTime($('manualTime').value))) toast('Время установлено. Таймер на паузе.'); } catch (error) { toast(error.message,true); } });
  $('settingsForm').addEventListener('input',e => { if (e.target.type==='file') return; dirty=true; $('settingsHint').textContent='Есть несохранённые настройки'; renderDraft(); });
  $('settingsForm').addEventListener('submit',async e => {
    e.preventDefault();
    if (!draft) return;
    try {
      const duration=parseTime($('durationInput').value,false);
      const value={brand:$('brandInput').value,caption:$('captionInput').value,durationSec:duration};
      for (const side of ['home','away']) value[side]={...draft[side],name:$(side+'Input').value.trim(),color:$(side+'Color').value};
      if (!(await send('settings',value))) return;
      dirty=false; loadDraft(client.state); $('settingsHint').textContent='Настройки сохранены'; toast('Настройки матча сохранены');
    } catch (error) { toast(error.message,true); }
  });
  async function logo(file) {
    if (!file || file.size>5*1024*1024) throw Error('Логотип должен быть не больше 5 МБ.');
    if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw Error('Используйте PNG, JPEG или WebP.');
    const url=URL.createObjectURL(file);
    try {
      const img=new Image(); img.src=url; await img.decode();
      const size=Math.min(1,256/Math.max(img.width,img.height));
      const canvas=document.createElement('canvas'); canvas.width=Math.max(1,Math.round(img.width*size)); canvas.height=Math.max(1,Math.round(img.height*size));
      canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height); return canvas.toDataURL('image/png');
    } finally { URL.revokeObjectURL(url); }
  }
  for (const side of ['home','away']) $(side+'Logo').addEventListener('change',async e => {
    if (!draft || !e.target.files[0]) return;
    try { draft[side].logo=await logo(e.target.files[0]); dirty=true; thumb(side); renderDraft(); $('settingsHint').textContent='Логотип загружен. Сохраните настройки.'; }
    catch(error) { toast(error.message,true); } finally { e.target.value=''; }
  });
  document.querySelectorAll('[data-remove-logo]').forEach(b => b.addEventListener('click',() => { if (!draft) return; draft[b.dataset.removeLogo].logo=''; dirty=true; thumb(b.dataset.removeLogo); renderDraft(); $('settingsHint').textContent='Сохраните настройки, чтобы удалить логотип из эфира.'; }));
  const overlay=location.origin+'/scoreboard.html'; $('obsUrl').value=overlay; $('openOverlay').href=overlay;
  $('copyUrl').addEventListener('click',async () => { try { await navigator.clipboard.writeText(overlay); toast('Адрес скопирован'); } catch { $('obsUrl').select(); toast('Скопируйте выделенный адрес: Ctrl+C или ⌘C'); } });
  $('awardPhotoInput').addEventListener('change',async e=> {
    const file=e.target.files[0]; if (!file) return;
    try {
      if (file.size>5*1024*1024) throw Error('Фото должно быть не больше 5 МБ.');
      if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw Error('Используйте PNG, JPEG или WebP.');
      const url=URL.createObjectURL(file);
      try {
        const img=new Image(); img.src=url; await img.decode();
        const scale=Math.min(1,512/Math.max(img.width,img.height));
        const canvas=document.createElement('canvas'); canvas.width=Math.max(1,Math.round(img.width*scale)); canvas.height=Math.max(1,Math.round(img.height*scale));
        canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
        awardPhoto=canvas.toDataURL('image/jpeg',0.86); awardPhotoChanged=true;
        $('awardPhotoPreview').src=awardPhoto; $('awardPhotoPreview').hidden=false;
      } finally { URL.revokeObjectURL(url); }
    } catch(error) { toast(error.message,true); } finally { e.target.value=''; }
  });
  $('playerAwardForm').addEventListener('submit',async e=> {
    e.preventDefault();
    const name=$('awardName').value.trim(), number=$('awardNumber').value.trim(), votes=Number($('awardVotes').value);
    if (!name) return toast('Введите имя победителя',true);
    if (!Number.isInteger(votes) || votes<0 || votes>1000000) return toast('Укажите число голосов от 0 до 1 000 000',true);
    if (await send('player_award',{visible:true,name,number,votes,photo:awardPhoto,title:'ИГРОК МАТЧА'})) { awardPhotoChanged=false; toast('Победитель сохранён. Включите источник глазком в OBS.'); }
  });
  $('newMatch').addEventListener('click',async () => { if (await confirmAction('Начать новый матч?', 'Счёт станет 0:0, период — первым, таймер остановится и сбросится. Названия и логотипы сохранятся.')) { if (await send('new_match')) toast('Новый матч готов'); } });
  $('exportMatch').addEventListener('click',() => {
    if (!client.state) return;
    const state={...client.state,remainingMs:Math.ceil(client.remaining()),penalties:client.penalties(),running:false};
    const url=URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));
    const a=document.createElement('a'); a.href=url; a.download='smo-match.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
    toast('Матч экспортирован. При импорте таймер будет на паузе.');
  });
  $('importMatch').addEventListener('change',async e => {
    const file=e.target.files[0]; if (!file) return;
    try {
      if (file.size>3_000_000) throw Error('Файл слишком большой.');
      const value=JSON.parse(await file.text());
      if (await confirmAction('Загрузить матч?', 'Текущие данные будут заменены данными из файла. Таймер загрузится на паузе.')) {
        if (await send('import',value)) { dirty=false; loadDraft(client.state); toast('Матч загружен'); }
      }
    } catch(error) { toast('Не удалось загрузить матч: '+error.message,true); } finally { e.target.value=''; }
  });
  document.addEventListener('keydown',e => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey || $('confirmDialog').open || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
    const keys={KeyQ:['home',-1],KeyW:['home',1],KeyO:['away',-1],KeyP:['away',1]};
    const fallback={q:'KeyQ', 'й':'KeyQ', w:'KeyW', 'ц':'KeyW', o:'KeyO', 'щ':'KeyO', p:'KeyP', 'з':'KeyP', ' ':'Space'};
    const code=keys[e.code] || e.code==='Space' ? e.code : fallback[(e.key || '').toLowerCase()];
    if (code==='Space') { e.preventDefault(); $('startPause').click(); }
    else if (keys[code]) { e.preventDefault(); const [side,delta]=keys[code]; send('score',{side,delta}); }
  });
  window.addEventListener('beforeunload',e => { if (dirty) { e.preventDefault(); e.returnValue=''; } });
  function frame() { if (client.state) tickPenalties(); const ms=client.remaining(); if (client.state) { board.tick(ms); draftBoard.tick(ms); $('bigClock').textContent=Scoreboard.clock(ms); $('bigClock').classList.toggle('zero',ms<=0); } requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
})();
