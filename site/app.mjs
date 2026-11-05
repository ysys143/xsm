import { scenes, topics, installPrompt } from './content.mjs';
import { createPlayer, advance, selectScene, togglePlayback, replay, setReducedMotion, sceneFrame } from './player.mjs';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escape = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const motion = matchMedia('(prefers-reduced-motion: reduce)');
const narrow = matchMedia('(max-width: 680px)');
let player = createPlayer({ reducedMotion: motion.matches });
let route = { view: 'demo', id: 'team' };
let renderedScene = -1;
let renderedBoard = null;
let animation = 0;
let lastTime = 0;
let stageVisible = true;
let toastTimer = 0;
const prompts = new Map([['install', installPrompt]]);
const demo = $('#demo');

$('#chapters').innerHTML = scenes.map(scene => `<a class="chapter-link" href="#demo/${scene.id}" data-scene="${scene.id}"><span>${scene.number}</span><span>${escape(scene.short)}</span></a>`).join('');
$('#guide-navigation').innerHTML = topics.map(topic => `<a href="#guide/${topic.id}" data-topic="${topic.id}">${escape(topic.label)}</a>`).join('');

function announce(text) { $('#announcement').textContent = text; }

function setFocus(focus, writeURL = false) {
  const valid = ['lead', 'workers', 'board'].includes(focus) ? focus : 'lead';
  demo.dataset.focus = valid;
  $$('.focus-tabs button').forEach(button => {
    const selected = button.dataset.focus === valid;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  const compact = narrow.matches || route.view === 'guide';
  for (const [name, selector] of [['lead', '#lead-window'], ['workers', '#worker-windows'], ['board', '#board-window']]) {
    const panel = $(selector);
    if (compact) {
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', `focus-${name}`);
      panel.tabIndex = 0;
    } else {
      panel.removeAttribute('role');
      panel.removeAttribute('aria-labelledby');
      panel.removeAttribute('tabindex');
    }
  }
  if (writeURL) {
    const params = new URLSearchParams(location.hash.split('?')[1]);
    if (valid === 'lead') params.delete('focus'); else params.set('focus', valid);
    history.replaceState(null, '', `#${route.view}/${route.id}${params.size ? `?${params}` : ''}`);
  }
}

function renderMessages(target, entries) {
  while (target.children.length > entries.length) target.lastElementChild.remove();
  entries.forEach((entry, index) => {
    let node = target.children[index];
    if (!node) {
      node = document.createElement('div');
      node.className = 'message';
      node.innerHTML = '<div class="message-from"></div><p class="message-text"></p>';
      target.append(node);
    }
    node.dataset.kind = entry.kind;
    const from = node.querySelector('.message-from');
    const text = node.querySelector('.message-text');
    if (from.textContent !== entry.from) from.textContent = entry.from;
    if (text.textContent !== entry.text) text.textContent = entry.text;
    text.classList.toggle('typing', entry.typing && !player.paused && !player.reducedMotion);
  });
}

function render() {
  const frame = sceneFrame(player);
  const scene = frame.scene;
  if (renderedScene !== player.scene) {
    renderedScene = player.scene;
    renderedBoard = null;
    for (const actor of ['lead', 'api', 'ui']) $(`#${actor}-messages`).replaceChildren();
    $('#qa-report').replaceChildren();
    $('#scene-title').textContent = `${scene.number} / ${scene.title}`;
    $('#scene-day').textContent = scene.day;
    $$('[data-actor-title]').forEach(node => { node.textContent = scene.actors[node.dataset.actorTitle].join(' · '); });
    $('#board-label').textContent = player.scene === 3 ? 'COORDINATION BOARD / 팀장 간 공유' : 'TEAM BOARD / NOTIFICATIONS';
    $('#team-relationship').textContent = player.scene === 3 ? 'API 팀 · UI 팀 · 팀장들이 함께 속한 조율 팀' : '팀장 1 · 수평적인 워커 3 · 각자의 네이티브 세션';
    $('#caption-number').textContent = `${scene.number} / 이 장면의 사용법`;
    $('#caption-title').textContent = scene.caption;
    $('#caption-description').textContent = scene.description;
    $('#scene-guide-link').href = `#guide/${scene.topic}`;
    $('#expand-show').href = `#demo/${scene.id}`;
    $$('#chapters a').forEach(link => {
      if (link.dataset.scene === scene.id) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current');
    });
    $('#transcript-content').innerHTML = Object.entries(scene.messages).flatMap(([actor, messages]) => messages.map(message => ({ ...message, actor }))).sort((a, b) => a.at - b.at).map(message => `<li><span>${escape(message.from)}</span><p>${escape(message.text)}</p></li>`).join('');
    if (route.view === 'demo' && location.hash.startsWith('#demo/')) {
      route.id = scene.id;
      const params = new URLSearchParams(location.hash.split('?')[1]);
      history.replaceState(null, '', `#demo/${scene.id}${params.size ? `?${params}` : ''}`);
    }
    announce(`장면 ${scene.number}. ${scene.title}`);
  }
  for (const actor of ['lead', 'api', 'ui']) renderMessages($(`#${actor}-messages`), frame.messages[actor]);
  renderMessages($('#qa-report'), frame.messages.qa);
  if ($('#scene-status').textContent !== frame.status) $('#scene-status').textContent = frame.status;
  if (renderedBoard !== frame.board) {
    renderedBoard = frame.board;
    $('#board-title').textContent = frame.board.title;
    const marks = { done: '+', active: '>', waiting: '-', blocked: '!' };
    $('#board-items').innerHTML = frame.board.items.map(item => `<li data-state="${item.state}"><span class="item-mark" aria-hidden="true">${marks[item.state]}</span><span>${escape(item.text)}</span></li>`).join('');
    $('#completion').hidden = frame.board.progress === undefined;
    if (frame.board.progress !== undefined) $('#completion .completion-track span').style.transform = `scaleX(${frame.board.progress})`;
  }
  $('#message-flow').textContent = frame.flow?.text ?? '';
  $$('.chapter-timeline i').forEach((bar, index) => {
    const progress = index < player.scene ? 1 : index === player.scene ? Math.min(player.elapsed / scene.duration, 1) : 0;
    bar.style.transform = `scaleX(${progress})`;
  });
  const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  $('#playback-time').textContent = `${time(player.elapsed / 1000)} / ${time(scene.duration / 1000)}`;
  $('#play-button .play-icon').textContent = player.paused ? '▷' : 'Ⅱ';
  $('#play-button .play-label').textContent = player.paused ? '재생' : '일시정지';
  $('#play-button').setAttribute('aria-label', player.paused ? '시연 재생' : '시연 일시정지');
  $('#motion-note').hidden = !player.reducedMotion;
  demo.dataset.scene = scene.id;
  demo.dataset.playing = String(!player.paused);
  demo.dataset.elapsed = String(Math.round(player.elapsed));
}

function schedule() {
  if (!animation && !player.paused && !document.hidden && stageVisible) animation = requestAnimationFrame(tick);
}
function tick(now) {
  animation = 0;
  if (!lastTime) lastTime = now;
  if (!document.hidden && stageVisible) player = advance(player, now - lastTime);
  lastTime = now;
  render(); schedule();
}
function resetClock() {
  lastTime = 0;
  if (animation) cancelAnimationFrame(animation);
  animation = 0;
  schedule();
}

function renderArticle(topic) {
  $('#guide-article').innerHTML = `<span class="section-label">사용 문서 / ${escape(topic.label)}</span><h1 tabindex="-1">${escape(topic.title)}</h1><p class="guide-intro">${escape(topic.intro)}</p>` + topic.sections.map((section, index) => {
    const copyId = `${topic.id}-${index}`;
    if (section.prompt) prompts.set(copyId, section.prompt);
    return `<section class="article-section" id="${copyId}" tabindex="-1"><h2>${escape(section.title)}</h2>${section.paragraphs.map(paragraph => `<p>${escape(paragraph)}</p>`).join('')}${section.prompt ? `<div class="prompt-block"><div class="prompt-toolbar"><span>내 에이전트에게 보내기</span><button class="copy-button" data-copy="${copyId}">${escape(section.copy)} ⧉</button></div><pre>${escape(section.prompt)}</pre></div>` : ''}${section.link ? `<a href="#guide/${section.link[0]}">${escape(section.link[1])} →</a>` : ''}</section>`;
  }).join('') + `<div class="guide-references"><h2>상세 안내</h2>${topic.references.map(([name, url]) => `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(name)} ↗</a>`).join('')}</div>`;
  const index = topics.indexOf(topic);
  const previous = topics[index - 1];
  const next = topics[index + 1];
  $('#guide-article').insertAdjacentHTML('beforeend', `<nav class="next-topic" aria-label="이전·다음 문서">${previous ? `<a href="#guide/${previous.id}">← ${escape(previous.label)}</a>` : '<span></span>'}${next ? `<a href="#guide/${next.id}">${escape(next.label)} →</a>` : '<a href="#demo/team">시연으로 돌아가기 →</a>'}</nav>`);
  $('#page-contents').innerHTML = '<span>이 페이지에서</span>' + topic.sections.map((section, index) => `<a href="#guide/${topic.id}?section=${topic.id}-${index}">${escape(section.title)}</a>`).join('');
  $$('#guide-navigation a').forEach(link => {
    if (link.dataset.topic === topic.id) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
}

function readRoute(initial = false) {
  const hash = location.hash.slice(1);
  if (!initial && ['main', 'show-stage'].includes(hash)) return;
  const [path, query] = hash.split('?');
  const [view, id] = path.split('/');
  const params = new URLSearchParams(query);
  const isGuide = view === 'guide' && topics.some(topic => topic.id === id);
  const isDemo = view === 'demo' && scenes.some(scene => scene.id === id);
  const next = isGuide || isDemo ? { view, id } : { view: 'demo', id: 'team' };
  if (!isGuide && !isDemo) history.replaceState(null, '', '#demo/team');
  const changed = initial || route.view !== next.view || route.id !== next.id;
  route = next;
  const topic = isGuide ? topics.find(topic => topic.id === id) : null;
  const sceneIndex = topic ? topic.scene : scenes.findIndex(scene => scene.id === next.id);
  player = { ...selectScene(player, sceneIndex), repeatScene: isGuide };
  const guide = route.view === 'guide';
  $('#show-view').hidden = guide;
  $('#guide-view').hidden = !guide;
  (guide ? $('#guide-slot') : $('#show-slot')).append(demo);
  if (guide && changed) renderArticle(topic);
  document.title = guide ? `${topic.title} — xsm` : 'xsm — All you need is a message channel.';
  $$('[data-nav]').forEach(link => {
    if (link.dataset.nav === route.view) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  setFocus(params.get('focus'));
  closeMenu(); render(); resetClock();
  if (params.has('section')) {
    requestAnimationFrame(() => {
      const target = document.getElementById(params.get('section'));
      if (target?.closest('#guide-article')) { target.scrollIntoView({ block: 'start' }); target.focus({ preventScroll: true }); }
    });
  } else if (!initial && changed) {
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (guide) $('#guide-article h1').focus({ preventScroll: true });
  }
}

function closeMenu() {
  $('#mobile-navigation').hidden = true;
  $('.mobile-menu').setAttribute('aria-expanded', 'false');
  $('.mobile-menu').setAttribute('aria-label', '메뉴 열기');
}
async function copyPrompt(button) {
  const text = prompts.get(button.dataset.copy);
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    const toast = $('#toast');
    toast.textContent = '문장을 복사했습니다. 에이전트에게 붙여넣으세요.';
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 3500);
  } catch {
    $('#copy-fallback').value = text;
    $('#copy-dialog').showModal();
    $('#copy-fallback').focus(); $('#copy-fallback').select();
  }
}

$('#play-button').addEventListener('click', () => {
  player = togglePlayback(player);
  announce(player.paused ? '시연을 일시정지했습니다.' : '시연을 재생합니다.');
  render(); resetClock();
});
$('#replay-button').addEventListener('click', () => { player = replay(player); render(); resetClock(); });
$('.focus-tabs').addEventListener('click', event => {
  const button = event.target.closest('button[data-focus]');
  if (button) setFocus(button.dataset.focus, true);
});
$('.focus-tabs').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const buttons = $$('.focus-tabs button');
  const index = buttons.indexOf(event.target);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
  setFocus(buttons[next].dataset.focus, true); buttons[next].focus();
});
$('.mobile-menu').addEventListener('click', () => {
  const open = $('#mobile-navigation').hidden;
  $('#mobile-navigation').hidden = !open;
  $('.mobile-menu').setAttribute('aria-expanded', String(open));
  $('.mobile-menu').setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('#mobile-navigation').hidden) { closeMenu(); $('.mobile-menu').focus(); }
});
document.addEventListener('click', event => {
  const button = event.target.closest('button[data-copy]');
  if (button) void copyPrompt(button);
});
window.addEventListener('hashchange', () => readRoute());
motion.addEventListener('change', event => { player = setReducedMotion(player, event.matches); render(); resetClock(); });
narrow.addEventListener('change', () => setFocus(demo.dataset.focus));
document.addEventListener('visibilitychange', resetClock);
const visibility = new IntersectionObserver(entries => { stageVisible = entries[0].isIntersecting; resetClock(); }, { threshold: 0.02 });
visibility.observe(demo);
const transcript = document.createElement('details');
transcript.id = 'transcript'; transcript.className = 'transcript';
transcript.innerHTML = '<summary>장면 전체 대화 읽기</summary><ol id="transcript-content"></ol>';
$('#demo .playback').append(transcript);
readRoute(true); schedule();
