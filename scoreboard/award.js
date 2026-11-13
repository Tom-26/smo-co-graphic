(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const photo=$('awardPhotoGraphic'), fallback=$('awardPhotoFallback');
  Scoreboard.connect(state=>{
    const a=state.playerAward || {};
    $('awardTitle').textContent=a.title || 'ИГРОК МАТЧА';
    $('awardNameGraphic').textContent=a.name || 'ИМЯ ИГРОКА';
    $('awardNumberGraphic').textContent=a.number ? '№ '+a.number : '';
    $('awardVotesGraphic').textContent=a.votes ? a.votes+' ГОЛОСОВ' : 'ГОЛОСОВАНИЕ ЗРИТЕЛЕЙ';
    photo.hidden=!a.photo;
    fallback.hidden=!!a.photo;
    if (a.photo && photo.src!==a.photo) photo.src=a.photo;
    if (!a.photo) { photo.removeAttribute('src'); fallback.textContent=(a.name || '★').trim().slice(0,1).toUpperCase(); }
  },()=>{});
})();
