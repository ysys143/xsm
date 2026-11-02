import { NativeWorkerControl, WORKER_CONTROL_FD } from '../typescript/native-worker-control.mjs';
const control = NativeWorkerControl.fromEnvironment();
const mode = process.argv[2];
let result;
try {
  await control.bind('native-한글');
  if (!['normal', 'cancel'].includes(mode)) throw new Error('invalid response was accepted');
  await control.bind('native-한글');
  let changed = false;
  try { await control.bind('other-native'); } catch { changed = true; }
  result = { status: 'bound', nativeID: control.nativeID, changedRefused: changed,
    descriptorHintRemoved: process.env[WORKER_CONTROL_FD] === undefined };
  if (mode === 'cancel') {
    result.cancellation = [await control.cancellationRequested(), await control.cancellationRequested()];
    await control.reportStopped();
  }
} catch (error) {
  if (['normal', 'cancel'].includes(mode)) throw error;
  result = { status: 'refused', nativeID: control.nativeID ?? null, type: error.constructor.name };
} finally { control.close(); }
process.stdout.write(JSON.stringify(result) + '\n');
