import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPlayer, advance, selectScene, togglePlayback, replay, setReducedMotion, sceneFrame } from '../player.mjs';
import { scenes } from '../content.mjs';

test('a paused show stays at the same moment, including after navigation', () => {
  const playing = advance(createPlayer(), 4000);
  const paused = togglePlayback(playing);
  assert.deepEqual(advance(paused, 9000), paused);
  const selected = selectScene(paused, 2);
  assert.equal(selected.paused, true);
  assert.equal(selected.scene, 2);
  assert.equal(advance(selected, 9000).scene, 2);
});

test('the story advances through all four scenes and stops at its end', () => {
  let player = createPlayer();
  for (let i = 0; i < scenes.length; i++) {
    assert.equal(player.scene, i);
    player = advance(player, scenes[i].duration);
  }
  assert.equal(player.scene, 3);
  assert.equal(player.paused, true);
  assert.equal(player.elapsed, scenes[3].duration);
});

test('reduced motion starts with a readable still and never starts itself', () => {
  const player = createPlayer({ reducedMotion: true });
  assert.equal(player.paused, true);
  assert.equal(player.elapsed, scenes[0].duration);
  assert.deepEqual(advance(player, 60000), player);
  assert.equal(selectScene(player, 2).elapsed, scenes[2].duration);
  assert.equal(setReducedMotion(togglePlayback(createPlayer()), false).paused, true);
});

test('replay is an explicit request to restart and play only the chosen scene', () => {
  const stopped = selectScene(createPlayer({ reducedMotion: true }), 2);
  const player = replay(stopped, 2);
  assert.equal(player.scene, 2);
  assert.equal(player.elapsed, 0);
  assert.equal(player.paused, false);
  assert.equal(player.repeatScene, true);
  assert.equal(advance(player, scenes[2].duration).scene, 2);
});

test('frames show worker contributions and a board update as the story plays', () => {
  const before = sceneFrame(createPlayer());
  const after = sceneFrame(advance(createPlayer(), scenes[0].duration - 1));
  assert.equal(before.messages.api.length, 0);
  assert.ok(after.messages.api.some(message => message.text.includes('API')));
  assert.ok(after.messages.ui.some(message => message.text.includes('UI')));
  assert.ok(after.board.items.some(item => item.text.includes('Luna')));
});

test('the progress scene has evidence of the blocker and planned next work', () => {
  const player = selectScene(createPlayer({ reducedMotion: true }), 2);
  const frame = sceneFrame(player);
  assert.match(frame.board.title, /8\s*\/\s*12/);
  assert.ok(frame.messages.lead.some(message => message.text.includes('verified')));
  assert.ok(frame.messages.qa.some(message => message.text.includes('duplicate')));
  assert.ok(frame.board.items.some(item => item.state === 'blocked' || item.state === 'active'));
});

test('the progress count appears only after the coordinator checks the reports', () => {
  const player = selectScene(createPlayer(), 2);
  assert.doesNotMatch(sceneFrame(player).status, /8\s*\/\s*12/);
  assert.doesNotMatch(sceneFrame(advance(player, 9000)).status, /8\s*\/\s*12/);
  assert.match(sceneFrame(advance(player, scenes[2].duration - 1)).status, /8\s*\/\s*12/);
});

test('tool arguments arrive intact and the result appears after completion', () => {
  const started = sceneFrame(advance(createPlayer(), 2500));
  const call = started.messages.lead.find(message => message.kind === 'tool');
  assert.equal(JSON.parse(call.text).action, 'show');
  assert.equal(call.resultVisible, false);
  assert.equal(call.typing, false);
  const finished = sceneFrame(advance(createPlayer(), 3100)).messages.lead.find(message => message.kind === 'tool');
  assert.equal(finished.resultVisible, true);
  assert.equal(JSON.parse(finished.result).members.length, 4);
});

test('invalid scene selection cannot break the player or produce NaN time', () => {
  const player = createPlayer();
  assert.deepEqual(selectScene(player, 100), player);
  assert.deepEqual(selectScene(player, -1), player);
  assert.deepEqual(advance(player, NaN), player);
  assert.deepEqual(advance(player, -1000), player);
});
