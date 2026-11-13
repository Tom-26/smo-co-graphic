(() => {
  'use strict';
  const board = Scoreboard.createBoard(document.getElementById('overlayBoard'));
  const warning = document.getElementById('overlayConnection');
  const promo = document.getElementById('overlayPromo');
  const title = document.getElementById('promoTitle');
  const copy = document.getElementById('promoCopy');
  let everConnected = false, carousel = [], index = -1, signature = '', latestState = null, stateReceivedAt = 0, pausedBefore = null, promoReady = false, revealTimer = null;
  const general = [
    ['ГОЛОСУЙ ЗА ЛУЧШЕГО ИГРОКА', 'Напиши имя своего фаворита в чате трансляции.'],
    ['СМОТРИ ХОККЕЙ СО SMO&CO', 'Оставайся с нами — впереди ещё больше игры и эмоций.'],
    ['МЕРЧ ЛЮБИМОЙ КОМАНДЫ НА ЗАКАЗ', 'Расскажи, какую вещь и дизайн ты хотел бы носить.'],
    ['ПОДДЕРЖИ КОМАНДУ В ЭФИРЕ', 'Пришли кружок поддержки в сообщество ВК или Telegram — возможно, он попадёт в трансляцию.']
  ];
  function renderPromo(state) {
    latestState = state;
    stateReceivedAt = performance.now();
    updatePromo();
  }
  function updatePromo() {
    const state = latestState;
    if (!state) return;
    const paused = !state.running || !state.visible;
    if (paused !== pausedBefore) {
      pausedBefore = paused;
      if (revealTimer) clearTimeout(revealTimer);
      revealTimer = null;
      promoReady = false;
      document.body.classList.toggle('promo-active', paused);
      document.body.classList.remove('promo-ready');
      promo.hidden = true;
      if (!paused) { index = -1; return; }
      const elapsedAtSnapshot = Math.max(0, (state.serverNowMs || Date.now()) - (state.promoStartedAtMs || state.serverNowMs || Date.now()));
      const delay = Math.max(0, 1500 - elapsedAtSnapshot);
      revealTimer = setTimeout(() => {
        const current = latestState;
        if (!current || (current.running && current.visible)) return;
        promoReady = true;
        document.body.classList.add('promo-ready');
        promo.hidden = false;
        show();
      }, delay);
    }
    if (!paused) return;
    const contextual = state.period === '1'
      ? ['КВИЗ В ПЕРВОМ ПЕРЕРЫВЕ', 'Оставайся с нами и участвуй в хоккейном квизе.']
      : state.period === '2'
        ? ['ИТОГИ ГОЛОСОВАНИЯ — ВО ВТОРОМ ПЕРЕРЫВЕ', 'Узнаем, кто станет лучшим игроком матча.']
        : null;
    const next = contextual ? [...general.slice(0, 1), contextual, ...general.slice(1)] : general;
    const nextSignature = JSON.stringify(next);
    if (signature !== nextSignature) { carousel = next; signature = nextSignature; index = -1; }
    const nowOnServer = (state.serverNowMs || Date.now()) + (performance.now() - stateReceivedAt);
    const elapsed = Math.max(0, nowOnServer - (state.promoStartedAtMs || state.serverNowMs || Date.now()));
    const nextIndex = ((state.promoStartIndex || 0) + Math.floor(elapsed / 6500)) % carousel.length;
    if (nextIndex !== index) { index = nextIndex; if (promoReady) show(); }
  }
  function show() {
    const [heading, message] = carousel[index];
    title.textContent = heading; copy.textContent = message;
    if (!promo.hidden) {
      promo.classList.remove('promo-enter');
      void promo.offsetWidth;
      promo.classList.add('promo-enter');
    }
  }
  const client = Scoreboard.connect(state => {
    everConnected = true;
    document.body.classList.toggle('overlay-hidden', !state.visible);
    board.update(state, client.remaining());
    renderPromo(state);
  }, online => { warning.hidden = online; warning.textContent = everConnected ? 'НЕТ СВЯЗИ С СЕРВЕРОМ' : 'ПОДКЛЮЧЕНИЕ К СЕРВЕРУ'; });
  setInterval(updatePromo, 250);
  function frame() { if (client.state) board.tick(client.remaining()); requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
})();
