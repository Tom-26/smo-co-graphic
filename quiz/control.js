(() => {
  'use strict';
  const $=id=>document.getElementById(id); let state=null, token='', busy=false, editing=null, lastRevision=-1, voteLoaded=false, fansLoaded=false, playersLoaded=false, teamsLoaded=false, teamsSignature='', librarySignature='', tournamentLoaded=false;
  const toast=(text,error=false)=>{ $('message').textContent=text; $('message').classList.toggle('error',error); };
  function render(s){
    state=s; $('tournamentStatus').textContent=s.display==='tournament'?'Таблица в эфире':'Таблица скрыта'; if(!voteLoaded) loadVote(s.vote || {players:[],winner:-1}); $('voteStatus').textContent=({vote:'В эфире: голосование',winner:'В эфире: победитель',quiz:'В эфире: квиз',team1:'В эфире: состав команды 1',team2:'В эфире: состав команды 2',fans:'В эфире: болельщики',player:'В эфире: игрок',none:'Графика скрыта'})[s.display || (s.visible?'quiz':'none')]; const q=s.questions[s.index]; $('questionTitle').textContent=q?.title || 'Добавьте первый вопрос'; $('position').textContent=q ? `${s.index+1} / ${s.questions.length}`:'0 / 0';
    $('answers').replaceChildren();
    if(q) q.options.forEach((text,i)=>{ const button=document.createElement('button'); button.type='button'; button.className='answer';
      button.textContent=`${i+1}. ${text}`; if(i===s.selected) button.classList.add('selected'); if(s.revealed && i===q.correct) button.classList.add('correct'); if(s.revealed && i===s.selected && i!==q.correct) button.classList.add('wrong');
      button.setAttribute('aria-pressed',String(i===s.selected)); button.disabled=s.revealed || busy; button.addEventListener('click',()=>command('select',i)); $('answers').append(button);
    });
    $('previous').disabled=!q || s.index===0 || busy; $('next').disabled=!q || s.index>=s.questions.length-1 || busy;
    for(const id of ['reset','reveal','toggle','edit','delete']) $(id).disabled=!q || busy;
    $('reveal').disabled=!q || s.revealed || busy;
    $('airStatus').textContent=s.visible?'КВИЗ В ЭФИРЕ':'СКРЫТО В ЭФИРЕ'; $('airStatus').classList.toggle('on',s.visible); $('toggle').textContent=s.visible?'Скрыть из эфира':'Показать в эфире';
    if(s.teams){
      const sig=JSON.stringify(s.teams);
      for(let i=1;i<=2;i++) $('showTeam'+i).textContent='Команда '+i+' · '+s.teams['team'+i].name;
    }
    const libSig=JSON.stringify(s.team_library||[]);if(libSig!==librarySignature){const playerSelect=$('playerSelect'), oldPlayer=playerSelect.value;playerSelect.replaceChildren(new Option('Выберите игрока',''));(s.team_library||[]).forEach(team=>{const group=document.createElement('optgroup');group.label=team.name;team.players.forEach((p,i)=>group.append(new Option(`#${p.number} · ${p.name} · ${p.position}`,team.id+':'+i)));playerSelect.append(group);});playerSelect.value=oldPlayer;for(let i=1;i<=2;i++){const el=$('matchTeam'+i),old=el.value;el.replaceChildren(new Option('Выберите команду',''));(s.team_library||[]).forEach(t=>el.add(new Option(t.name,t.id)));const match=(s.team_library||[]).find(t=>t.name===s.teams['team'+i].name);el.value=(s.team_library||[]).some(t=>t.id===old)?old:(match?.id||'');}librarySignature=libSig;updatePlayerPreview();}
    $('playerStatus').textContent=s.display==='player'?'Карточка игрока в эфире':'Карточка скрыта';
    if(!fansLoaded){$('fansName1').value=s.fans?.name1 || 'Красная машина'; $('fansName2').value=s.fans?.name2 || 'Звезда ЮЗ'; $('fansTeam1').value=s.fans?.team1 ?? 0; $('fansTeam2').value=s.fans?.team2 ?? 0; fansLoaded=true; updateFansPreview();}
    $('fansStatus').textContent=s.display==='fans'?'Болельщики в эфире':'Графика скрыта';
    const rosterMode=s.display==='team1'||s.display==='team2' ? 'В эфире: '+s.teams[s.display].name : 'Состав скрыт';
    $('rosterStatus').textContent=rosterMode;
    $('showTeam1').classList.toggle('active',s.display==='team1'); $('showTeam2').classList.toggle('active',s.display==='team2');
  }
  async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'}); if(!r.ok) throw Error(); const s=await r.json(); $('connection').textContent='Пульт подключён'; $('connection').classList.add('on'); if(lastRevision!==s.revision){lastRevision=s.revision;render(s);} }catch{$('connection').textContent='Нет связи с сервером'; $('connection').classList.remove('on');}}
  async function command(action,value){if(busy)return;busy=true;try{if(!token){const r=await fetch('/api/session');token=(await r.json()).token;}const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Quiz-Token':token},body:JSON.stringify({action,value})});const d=await r.json();if(!r.ok){if(r.status===403)token='';throw Error(d.error);}lastRevision=d.revision;render(d);toast('Сохранено');return d;}catch(e){toast(e.message || 'Нет связи с сервером',true);}finally{busy=false;if(state)render(state);}}
  $('applyTeams').onclick=async()=>{const a=$('matchTeam1').value,b=$('matchTeam2').value;if(!a||!b||a===b){toast('Выберите две разные команды',true);return;}const teams={team1:state.team_library.find(t=>t.id===a),team2:state.team_library.find(t=>t.id===b)};if(await command('teams_save',teams)){fansLoaded=false;render(state);}};
  $('showTournament').onclick=()=>command('tournament_display',true);
  $('hideTournament').onclick=()=>command('tournament_display',false);
  $('previous').onclick=()=>command('navigate',state.index-1); $('next').onclick=()=>command('navigate',state.index+1); $('reset').onclick=()=>command('reset'); $('reveal').onclick=()=>command('reveal'); $('toggle').onclick=()=>command('visible',!state.visible);
  $('new').onclick=()=>{editing=null;$('questionForm').reset();$('editorTitle').textContent='Новый вопрос';$('title').focus();};
  $('edit').onclick=()=>{const q=state.questions[state.index]; if(!q)return;editing=state.index;$('editorTitle').textContent='Изменить вопрос';$('title').value=q.title;$('options').value=q.options.join('\n');$('correct').value=q.correct;$('title').focus();};
  $('delete').onclick=()=>{if(confirm('Удалить текущий вопрос?'))command('delete');};
  $('questionForm').onsubmit=async e=>{e.preventDefault(); const options=$('options').value.split('\n').map(x=>x.trim()).filter(Boolean);const result=await command('save',{index:editing,question:{title:$('title').value.trim(),options,correct:Number($('correct').value)}});if(result){editing=null;$('questionForm').reset();$('editorTitle').textContent='Новый вопрос';}};
  $('obsUrl').value=location.origin+'/overlay.html';$('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('obsUrl').value);toast('Адрес скопирован');}catch{$('obsUrl').select();toast('Скопируйте выделенный адрес');}};
  function voteRows(){
    return $('players').value.split('\n').map(x=>x.trim()).filter(Boolean).map(line=>{
      const parts=line.split('|'); if(parts.length>2) throw Error('Формат строки: имя | голоса');
      const name=parts[0].trim(), raw=(parts[1]||'').trim();
      if(!name || name.length>80 || (raw && !/^\d+$/.test(raw)) || Number(raw)>1000000) throw Error('Проверьте имя и число голосов.');
      return {name,votes:raw ? Number(raw) : 0};
    });
  }
  function updateWinners(chosen){
    const select=$('winner'), old=chosen ?? select.value; select.replaceChildren(new Option('Не выбран','-1'));
    let rows=[]; try{rows=voteRows();}catch{} rows.forEach((p,i)=>select.add(new Option(p.name,String(i))));
    select.value=Array.from(select.options).some(o=>o.value===String(old)) ? String(old) : '-1';
  }
  function loadVote(vote){$('players').value=vote.players.map(p=>p.name+' | '+p.votes).join('\n'); updateWinners(vote.winner);voteLoaded=true;}
  $('players').addEventListener('input',()=>updateWinners());
  async function saveVote(){
    let players;try{players=voteRows();if(players.length<2 || players.length>8)throw Error('Добавьте от 2 до 8 игроков.');}catch(e){toast(e.message,true);return null;}
    return command('vote_save',{players,winner:Number($('winner').value)});
  }
  $('voteForm').onsubmit=async e=>{e.preventDefault();await saveVote();};
  $('showVote').onclick=async()=>{if(await saveVote()) await command('vote_display','vote');};
  $('showWinner').onclick=async()=>{if(Number($('winner').value)<0){toast('Выберите победителя',true);return;}if(await saveVote()) await command('vote_display','winner');};
  $('hideVote').onclick=()=>command('vote_display','none');
  function updateFansPreview(){const a=Number($('fansTeam1').value)||0,b=Number($('fansTeam2').value)||0,total=a+b,p=total?Math.round(a*100/total):0; $('fansPreview').textContent=`${p}% против ${total?100-p:0}%`;}
  $('fansTeam1').addEventListener('input',updateFansPreview); $('fansTeam2').addEventListener('input',updateFansPreview);
  $('fansForm').onsubmit=async e=>{e.preventDefault();await command('fans_display',{team1:Number($('fansTeam1').value),team2:Number($('fansTeam2').value),name1:$('fansName1').value.trim(),name2:$('fansName2').value.trim()});};
  $('hideFans').onclick=()=>command('fans_display',false);
  let uploadedClip='';
  async function loadClips(){try{const r=await fetch('/api/clips',{cache:'no-store'});if(!r.ok)throw Error();const clips=await r.json(), selected=$('clipSelect').value;$('clipSelect').replaceChildren(new Option('Выберите видео',''));clips.forEach(c=>$('clipSelect').add(new Option(c.name,c.file)));$('clipSelect').value=selected;}catch{$('clipStatus').textContent='Не удалось загрузить список видео';}}
  $('clipSelect').onchange=()=>{uploadedClip=$('clipSelect').value;const video=$('clipPreview');video.pause();video.hidden=!uploadedClip;if(uploadedClip){video.src='/media/'+uploadedClip;$('clipStatus').textContent='Выбрано: '+$('clipSelect').selectedOptions[0].textContent;}else{video.removeAttribute('src');video.load();$('clipStatus').textContent='Выберите видео и проверьте его перед показом';}$('clipPlay').disabled=!uploadedClip;};
  loadClips();
  const clipDrop=$('clipDrop');
  async function uploadClip(file){
    if(!file)return;const ext=file.name.toLowerCase().split('.').pop();const mime=ext==='mp4'?'video/mp4':ext==='webm'?'video/webm':'';
    if(!mime || file.size>100*1024*1024 || !file.size){$('clipStatus').textContent='Выберите MP4 или WebM до 100 МБ';return;}
    $('clipSelect').value='';$('clipSelect').onchange();$('clipStatus').textContent='Загрузка: '+file.name+'…';
    try{if(!token){const r=await fetch('/api/session');token=(await r.json()).token;}const r=await fetch('/api/clip-upload',{method:'POST',headers:{'Content-Type':mime,'X-Quiz-Token':token,'X-Clip-Name':encodeURIComponent(file.name)},body:file});const data=await r.json();if(!r.ok)throw Error(data.error);await loadClips();$('clipStatus').textContent='Загружено: '+file.name+'. Выберите видео в списке и проверьте его.';}catch(e){$('clipStatus').textContent=e.message||'Ошибка загрузки';}
  }
  $('clipFile').addEventListener('change',e=>uploadClip(e.target.files[0]));
  for(const event of ['dragenter','dragover'])clipDrop.addEventListener(event,e=>{e.preventDefault();clipDrop.classList.add('dragging');});
  for(const event of ['dragleave','drop'])clipDrop.addEventListener(event,e=>{e.preventDefault();clipDrop.classList.remove('dragging');});
  clipDrop.addEventListener('drop',e=>uploadClip(e.dataTransfer.files[0]));
  $('clipPlay').onclick=()=>{if(uploadedClip)command('clip_display',uploadedClip);}; $('clipStop').onclick=()=>command('clip_display',false);
  function setTeamPreviewLogo(img,url){img.hidden=!url;if(url)img.src=url;else img.removeAttribute('src');}
  function updatePlayerPreview(){
    const value=$('playerSelect').value, [id,index]=value.split(':'), team=state?.team_library?.find(t=>t.id===id), player=team?.players?.[Number(index)];
    const wrap=$('playerPreviewWrap'), photo=$('previewPhoto'), fallback=$('previewFallback');
    wrap.hidden=!value || !player; $('showPlayer').disabled=!value || !player;
    if(!player){photo.removeAttribute('src');return;}
    setTeamPreviewLogo($('previewTeamLogo'),team.logo_url);$('playerPreview').dataset.accent=team.accent || ''; $('previewTeam').textContent=team.name; $('previewName').textContent=player.name; $('previewPosition').textContent=player.position; $('previewNumber').textContent='#'+player.number;
    photo.hidden=true; fallback.hidden=false; photo.onload=()=>{photo.hidden=false;fallback.hidden=true;}; photo.onerror=()=>{photo.hidden=true;fallback.hidden=false;};
    if(player.photo_url) photo.src=player.photo_url; else photo.removeAttribute('src');
  }
  $('playerSelect').addEventListener('change',updatePlayerPreview);
  $('showPlayer').onclick=()=>{const val=$('playerSelect').value;if(!val){toast('Выберите игрока',true);return;}const [library_id,index]=val.split(':');command('player_display',{library_id,index:Number(index)});};
  $('hidePlayer').onclick=()=>command('player_display',false);
  $('showTeam1').onclick=()=>command('roster_display','team1'); $('showTeam2').onclick=()=>command('roster_display','team2'); $('hideRoster').onclick=()=>command('roster_display','none');
  refresh();setInterval(refresh,700);
})();
