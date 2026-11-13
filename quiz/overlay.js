(() => {
  'use strict'; const $=id=>document.getElementById(id); let revision=-1, clipPlayId='', rosterLive=null, rosterKey='', rosterIndex=-1;
  function setLogo(img,url){img.hidden=!url;if(url)img.src=url;else img.removeAttribute('src');}
  function updateRosterPlayer(){
    if(!rosterLive)return;
    const players=rosterLive.team.players, index=players.length ? Math.floor(Math.max(0,Date.now()-rosterLive.started)/4000)%players.length : -1;
    if(index===rosterIndex)return;
    rosterIndex=index;
    Array.from($('rosterPlayers').children).forEach((row,i)=>row.classList.toggle('is-active',i===index));
    const player=players[index], feature=$('rosterFeature');feature.hidden=!player;
    if(!player)return;
    $('rosterFeatureNumber').textContent='#'+player.number;
    $('rosterFeatureName').textContent=player.name;
    $('rosterFeaturePosition').textContent=player.position || 'Позиция не указана';
    const photo=$('rosterFeaturePhoto'),fallback=$('rosterFeatureFallback');
    photo.hidden=true;fallback.hidden=false;
    photo.onload=()=>{if(rosterLive && rosterLive.team.players[rosterIndex]===player){photo.hidden=false;fallback.hidden=true;}};
    photo.onerror=()=>{if(rosterLive && rosterLive.team.players[rosterIndex]===player){if(photo.dataset.originalFallback!=='1' && player.photo_url){photo.dataset.originalFallback='1';photo.src=player.photo_url;}else{photo.hidden=true;fallback.hidden=false;}}};
    photo.dataset.originalFallback='0';if(player.photo_url)photo.src='/api/player-cutout?url='+encodeURIComponent(player.photo_url);else photo.removeAttribute('src');
  }
  async function update(){try{
    const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)return;const s=await r.json();if(s.revision===revision)return;revision=s.revision;
    const mode=s.display || (s.visible?'quiz':'none'), q=s.questions[s.index];
    const showRoster=mode==='team1'||mode==='team2', showQuiz=mode==='quiz'&&!!q;
    if(!showRoster){rosterLive=null;rosterKey='';rosterIndex=-1;}
    $('graphic').hidden=!(showQuiz||mode==='vote'||mode==='winner'||mode==='fans'); $('rosterGraphic').hidden=!showRoster; $('playerGraphic').hidden=mode!=='player';
    $('tournamentGraphic').hidden=mode!=='tournament';
    if(mode==='tournament' && s.tournament){const t=s.tournament, table=$('tournamentTable');table.replaceChildren();const head=table.insertRow();head.insertCell().textContent='Команда';t.names.forEach(n=>appendTeamName(head.insertCell(),n,s.team_library));t.names.forEach((name,i)=>{const row=table.insertRow();appendTeamName(row.insertCell(),name,s.team_library);t.names.forEach((_,j)=>{const cell=row.insertCell();if(i===j){cell.className='diagonal';cell.textContent='—';return;}const winner=t.results[Math.min(i,j)+'-'+Math.max(i,j)];cell.textContent=winner>=0?t.names[winner]:'—';});});renderStandings($('standingsOverlay'),t.names,t.results,t.points_per_win ?? 2,s.team_library);$('standingsRule').textContent='ПОБЕДА: '+(t.points_per_win ?? 2)+' ОЧК. · ПОРАЖЕНИЕ: 0 · ПРИ РАВЕНСТВЕ ОЧКОВ МЕСТО ОБЩЕЕ';}
    const video=$('clipVideo'), clipBox=$('clipGraphic');
    if(mode==='clip' && s.clip){
      if(clipPlayId!==s.clip.play_id){clipPlayId=s.clip.play_id;clipBox.hidden=false;video.src='/media/'+s.clip.file;video.currentTime=0;video.play().catch(()=>{clipBox.hidden=true;});}
      return;
    }
    if(clipPlayId){video.pause();video.removeAttribute('src');video.load();clipPlayId='';} clipBox.hidden=true;
    if(mode==='player'){
      const selected=s.player, team=selected && (selected.library_id ? s.team_library?.find(t=>t.id===selected.library_id) : s.teams?.[selected.team]), player=team?.players?.[selected.index];
      if(!player){$('playerGraphic').hidden=true;return;}
      setLogo($('playerTeamLogo'),team.logo_url); $('playerGraphic').dataset.accent=team.accent; $('playerName').textContent=player.name; $('playerTeam').textContent=team.name;
      $('playerPosition').textContent=player.position; $('playerNumber').textContent='#'+player.number;
      const photo=$('playerPhoto'),fallback=$('playerFallback'); photo.hidden=true;fallback.hidden=false;
      photo.onload=()=>{photo.hidden=false;fallback.hidden=true;}; photo.onerror=()=>{photo.hidden=true;fallback.hidden=false;};
      if(player.photo_url){photo.src=player.photo_url;}else{photo.removeAttribute('src');}
      return;
    }
    if(showRoster){
      const team=s.teams?.[mode]; if(!team)return;
      const key=JSON.stringify([mode,s.roster_started_at,team]);
      if(key!==rosterKey){
        rosterKey=key;rosterIndex=-1;rosterLive={team,started:Number(s.roster_started_at)*1000 || Date.now()};$('rosterFeature').hidden=true;
        setLogo($('rosterTeamLogo'),team.logo_url); $('teamLabel').textContent=team.label; $('teamName').textContent=team.name;
        $('rosterGraphic').dataset.accent=team.accent; $('rosterCount').textContent=team.players.length+' ИГРОКОВ';
        const list=$('rosterPlayers'); list.classList.toggle('roster-large',team.players.length>18); list.classList.toggle('roster-medium',team.players.length>16 && team.players.length<=18); list.replaceChildren();
        team.players.forEach(player=>{const row=document.createElement('div');row.className='roster-player';const number=document.createElement('span');number.className='roster-number';number.textContent=String(player.number).padStart(2,'0');const name=document.createElement('span');name.className='roster-player-name';name.textContent=player.name;row.append(number,name);list.append(row);});
      }
      updateRosterPlayer();
      return;
    }
    if(mode==='fans'){
      const a=s.fans?.team1||0,b=s.fans?.team2||0,total=a+b,p=total?Math.round(a*100/total):0;
      $('graphicType').textContent='БОЛЕЛЬЩИКИ НА ТРИБУНАХ'; $('graphicFooter').textContent='SMO&CO · ХОККЕЙ В ПРЯМОМ ЭФИРЕ'; $('title').textContent='Среди зрителей';
      $('answers').replaceChildren();
      [[s.fans?.name1 || 'Команда 1',p,'red'],[s.fans?.name2 || 'Команда 2',total?100-p:0,'blue']].forEach(([name,percent,color])=>{const row=document.createElement('div');row.className='graphic-answer fan-result fan-'+color;const label=document.createElement('span');label.textContent=name;const number=document.createElement('strong');number.className='fan-percent';number.textContent=percent+'%';const team=Object.values(s.teams||{}).find(t=>t.name===name);if(team?.logo_url){const img=document.createElement('img');img.src=team.logo_url;img.alt='';img.className='broadcast-team-logo';row.append(img);}row.append(label,number);$('answers').append(row);});
      return;
    }
    if(!showQuiz&&mode!=='vote'&&mode!=='winner')return;
    $('answers').replaceChildren();
    if(mode==='quiz'){
      $('graphicType').textContent='ХОККЕЙНЫЙ КВИЗ';$('graphicFooter').textContent='ДУМАЙ · ВЫБИРАЙ · БОЛЕЙ';$('title').textContent=q.title;
      q.options.forEach((value,i)=>{const item=document.createElement('div');item.className='graphic-answer';if(i===s.selected)item.classList.add('selected');if(s.revealed&&i===q.correct)item.classList.add('correct');if(s.revealed&&i===s.selected&&i!==q.correct)item.classList.add('wrong');const n=document.createElement('span');n.className='graphic-letter';n.textContent=String.fromCharCode(65+i);const label=document.createElement('span');label.textContent=value;item.append(n,label);$('answers').append(item);});return;
    }
    const vote=s.vote, winner=vote.players[vote.winner];
    $('graphicType').textContent=mode==='vote'?'ГОЛОСОВАНИЕ ЗРИТЕЛЕЙ':'ЛУЧШИЙ ИГРОК МАТЧА';
    $('graphicFooter').textContent=mode==='vote'?'ГОЛОСУЙТЕ В ОПРОСЕ ИЛИ ЧАТЕ':'СПАСИБО ЗА ВАШИ ГОЛОСА';
    $('title').textContent=mode==='vote'?'Кто лучший игрок матча?':(winner?.name || '');
    const rows=mode==='vote'?vote.players:(winner?[winner]:[]),total=vote.players.reduce((n,p)=>n+p.votes,0);
    rows.forEach(p=>{const row=document.createElement('div');row.className='graphic-answer';const name=document.createElement('span');name.textContent=p.name;const count=document.createElement('strong');count.className='vote-count';count.textContent=mode==='vote'?(total?Math.round(p.votes*100/total)+'% · ':'')+p.votes:p.votes+' голосов';row.append(name,count);$('answers').append(row);});
  }catch{}}
  $('clipVideo').addEventListener('ended',()=>{$('clipGraphic').hidden=true;});
  update();setInterval(update,500);setInterval(updateRosterPlayer,250);
})();
