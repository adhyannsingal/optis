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
