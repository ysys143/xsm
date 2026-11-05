import { scenes } from './content.mjs';

export function createPlayer({ reducedMotion = false, scene = 0 } = {}) {
  const valid = Number.isInteger(scene) && scenes[scene] ? scene : 0;
  return { scene: valid, elapsed: reducedMotion ? scenes[valid].duration : 0, paused: reducedMotion, reducedMotion, repeatScene: false };
}

export function advance(player, milliseconds) {
  if (player.paused || !Number.isFinite(milliseconds) || milliseconds <= 0) return player;
  let { scene, elapsed } = player;
  elapsed += milliseconds;
  while (elapsed >= scenes[scene].duration) {
    if (player.repeatScene || scene === scenes.length - 1) {
      return { ...player, scene, elapsed: scenes[scene].duration, paused: true };
    }
    elapsed -= scenes[scene].duration;
    scene += 1;
  }
  return { ...player, scene, elapsed };
}

export function selectScene(player, scene) {
  if (!Number.isInteger(scene) || !scenes[scene]) return player;
  if (scene === player.scene) return player;
  return { ...player, scene, elapsed: player.paused ? scenes[scene].duration : 0 };
}

export function togglePlayback(player) {
  const ended = player.elapsed >= scenes[player.scene].duration;
  return { ...player, paused: !player.paused, elapsed: player.paused && ended ? 0 : player.elapsed };
}

export function replay(player, scene = player.scene) {
  if (!Number.isInteger(scene) || !scenes[scene]) return player;
  return { ...player, scene, elapsed: 0, paused: false, repeatScene: true };
}

export function setReducedMotion(player, reducedMotion) {
  return reducedMotion
    ? { ...player, reducedMotion, paused: true, elapsed: scenes[player.scene].duration }
    : { ...player, reducedMotion };
}

export function sceneFrame(player) {
  const scene = scenes[player.scene];
  const time = player.reducedMotion ? scene.duration : player.elapsed;
  const messages = Object.fromEntries(Object.entries(scene.messages).map(([actor, entries]) => [actor,
    entries.filter(entry => entry.at <= time).map(entry => {
      const count = player.reducedMotion ? entry.text.length : Math.max(1, Math.floor((time - entry.at) / 19));
      return { ...entry, text: entry.text.slice(0, count), typing: count < entry.text.length };
    }),
  ]));
  const board = scene.boards.filter(entry => entry.at <= time).at(-1) ?? scene.boards[0];
  const flow = scene.flows.filter(entry => entry.at <= time).at(-1) ?? null;
  const status = scene.id === 'progress' && board.progress === undefined
    ? '완료 기준과 워커 보고 대조 중'
    : scene.status;
  return { scene, messages, board, flow, status };
}
