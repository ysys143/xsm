import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveLocale, translate, getContent, readLocalePreference, saveLocalePreference } from '../i18n.mjs';
import { createPlayer, selectScene, sceneFrame } from '../player.mjs';

test('Korean browser preferences choose Korean without using location', () => {
  assert.equal(resolveLocale({ languages: ['ko-KR', 'en-US'] }), 'ko');
  assert.equal(resolveLocale({ languages: ['en-US', 'ko-KR'] }), 'en');
  assert.equal(resolveLocale({ languages: ['fr-FR', 'ko'] }), 'ko');
  assert.equal(resolveLocale({ languages: ['fr-FR'] }), 'en');
});

test('an explicit URL wins, then a saved choice, then browser preference', () => {
  assert.equal(resolveLocale({ requested: 'en', saved: 'ko', languages: ['ko-KR'] }), 'en');
  assert.equal(resolveLocale({ requested: 'unknown', saved: 'en', languages: ['ko-KR'] }), 'en');
  assert.equal(resolveLocale({ requested: 'KO-kr', saved: 'en' }), 'ko');
  assert.equal(resolveLocale({ saved: 'ko', languages: ['en-US'] }), 'ko');
});

test('disabled browser storage never prevents language detection or switching', () => {
  const denied = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  assert.equal(readLocalePreference(denied), null);
  assert.equal(saveLocalePreference(denied, 'ko'), false);
});

test('both locales have the same chapters, timing, protocol identifiers and guide routes', () => {
  const en = getContent('en'), ko = getContent('ko');
  assert.deepEqual(ko.topics.map(topic => [topic.id, topic.scene]), en.topics.map(topic => [topic.id, topic.scene]));
  for (const [index, scene] of en.scenes.entries()) {
    const localized = ko.scenes[index];
    assert.equal(localized.id, scene.id);
    assert.equal(localized.duration, scene.duration);
    assert.deepEqual(localized.boards.map(board => board.at), scene.boards.map(board => board.at));
    for (const actor of Object.keys(scene.messages)) {
      assert.deepEqual(localized.messages[actor].map(message => [message.at, message.kind, message.resultAt]), scene.messages[actor].map(message => [message.at, message.kind, message.resultAt]));
      scene.messages[actor].forEach((message, position) => {
        if (message.kind !== 'tool') return;
        const original = JSON.parse(message.text), translated = JSON.parse(localized.messages[actor][position].text);
        for (const field of ['action', 'target', 'team', 'item', 'kind']) assert.equal(translated[field], original[field]);
      });
    }
  }
});

test('Korean includes the guides, copy prompts and native session narration', () => {
  const ko = getContent('ko');
  assert.equal(ko.topics.length, 8);
  assert.match(ko.installPrompt, /설치/);
  assert.match(ko.scenes[0].messages.lead[0].text, /알림/);
  assert.match(ko.topics.find(topic => topic.id === 'progress').intro, /팀장/);
  assert.equal(translate('ko', 'Docs'), '사용 문서');
  assert.equal(translate('en', 'Docs'), 'Docs');
});

test('a Korean frame keeps playback state and displays the same verified count', () => {
  const player = selectScene(createPlayer({ reducedMotion: true }), 2);
  const before = structuredClone(player);
  const frame = sceneFrame(player, getContent('ko').scenes);
  assert.match(frame.status, /8\s*\/\s*12/);
  assert.match(frame.messages.lead[0].text, /계획/);
  assert.deepEqual(player, before);
});
