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

export function sceneFrame(player, story = scenes) {
  const scene = story[player.scene];
  const time = player.reducedMotion ? scene.duration : player.elapsed;
  const messages = Object.fromEntries(Object.entries(scene.messages).map(([actor, entries]) => [actor,
    entries.filter(entry => entry.at <= time).map(entry => {
      const count = player.reducedMotion ? entry.text.length : Math.max(1, Math.floor((time - entry.at) / 19));
      const typed = !['tool', 'inbox'].includes(entry.kind);
      return { ...entry, text: typed ? entry.text.slice(0, count) : entry.text, typing: typed && count < entry.text.length, resultVisible: entry.kind === 'tool' && time >= entry.resultAt };
    }),
  ]));
  const board = scene.boards.filter(entry => entry.at <= time).at(-1) ?? scene.boards[0];
  const flow = scene.flows.filter(entry => entry.at <= time).at(-1) ?? null;
  const status = scene.id === 'progress' && board.progress === undefined
    ? (scene.pendingStatus ?? 'Checking worker reports against acceptance criteria')
    : scene.status;
  return { scene, messages, board, flow, status };
}
