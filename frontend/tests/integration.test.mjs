import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../src/routeAudio.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { playCurrentCue } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const cue = { audio: 'AAAA', audio_type: 'audio/mpeg', generation: 7 };
function player() {
  return { src: '', plays: 0, pause() {}, async play() { this.plays++; } };
}

test('landing image points to a shipped public asset', async () => {
  const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const path = /imageSrc: "\/([^"]+)"/.exec(app)?.[1];
  assert.equal(path, 'optis-glasses.png');
  await access(new URL(`../public/${path}`, import.meta.url));
});

test('current route audio plays', async () => {
  const audio = player();
  await playCurrentCue(async () => ({ cue }), () => true, () => 7, audio);
  assert.equal(audio.plays, 1);
});

test('invalidating an in-flight request prevents later playback', async () => {
  let resolve;
  let current = true;
  const audio = player();
  const pending = playCurrentCue(() => new Promise(r => { resolve = r; }), () => current, () => 7, audio);
  current = false;
  resolve({ cue });
  await pending;
  assert.equal(audio.plays, 0);
  assert.equal(audio.src, '');
});

test('server generation changes during a fetch discard the old cue', async () => {
  let resolve;
  let generation = 7;
  const audio = player();
  const pending = playCurrentCue(() => new Promise(r => { resolve = r; }), () => true, () => generation, audio);
  generation = 8;
  resolve({ cue });
  await pending;
  assert.equal(audio.plays, 0);
});

test('missing status and non-audio responses cannot play', async () => {
  const audio = player();
  await playCurrentCue(async () => ({ cue }), () => true, () => undefined, audio);
  await playCurrentCue(async () => ({ cue: { ...cue, audio_type: 'text/html' } }), () => true, () => 7, audio);
  assert.equal(audio.plays, 0);
});

const lifecycleSource = await readFile(new URL('../src/sessionLifecycle.ts', import.meta.url), 'utf8');
const lifecycleJS = ts.transpileModule(lifecycleSource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { SessionRequests, appendEvent, canCancelRecording, startRecorder, disposeRecording } = await import(`data:text/javascript;base64,${Buffer.from(lifecycleJS).toString('base64')}`);

test('server restart accepts generation zero and rejects older client responses', () => {
  const requests = new SessionRequests();
  let status;
  const accept = (ticket, generation) => { if (requests.accept(ticket)) status = generation; };
  accept(requests.begin(), 7);
  const old = requests.begin();
  accept(requests.begin(), 0);
  accept(old, 7);
  assert.equal(status, 0);
});

test('expired-session tickets cannot update a replacement session', () => {
  const requests = new SessionRequests();
  const pendingVoice = requests.begin();
  const pendingStatus = requests.begin();
  requests.reset();
  assert.equal(requests.current(pendingVoice), false);
  assert.equal(requests.accept(pendingStatus), false);
  assert.equal(requests.accept(requests.begin()), true);
});

test('conversation and recent actions include the newest reply after more than six requests', () => {
  let events = [];
  for (let i = 1; i <= 40; i++) events = appendEvent(events, i);
  assert.equal(events.length, 30);
  assert.deepEqual(events.slice(-6), [35, 36, 37, 38, 39, 40]);
  assert.equal([...events].reverse()[0], 40);
});

test('submitted voice processing does not offer local recording cancellation', () => {
  assert.equal(canCancelRecording('starting'), true);
  assert.equal(canCancelRecording('recording'), true);
  assert.equal(canCancelRecording('sending'), false);
  assert.equal(canCancelRecording('idle'), false);
});

for (const failure of ['constructor', 'start']) {
  test(`recorder ${failure} failure releases the granted microphone`, () => {
    let stops = 0;
    const media = { getTracks: () => [{ stop: () => stops++ }] };
    const recorder = { state: 'inactive', start() { throw Error('start failed'); } };
    assert.throws(() => startRecorder(media, () => {
      if (failure === 'constructor') throw Error('constructor failed');
      return recorder;
    }, () => {}));
    assert.equal(stops, 1);
    if (failure === 'start') assert.equal(recorder.onstop, null);
  });
}

test('session recording cleanup releases tracks and disables deferred submission', () => {
  let stops = 0;
  let submissions = 0;
  const recorder = {
    state: 'recording', onstop: () => submissions++, onerror: () => {},
    stop() { this.onstop?.(); this.state = 'inactive'; },
  };
  disposeRecording(recorder, { getTracks: () => [{ stop: () => stops++ }] });
  assert.equal(stops, 1);
  assert.equal(submissions, 0);
  assert.equal(recorder.onerror, null);
});
