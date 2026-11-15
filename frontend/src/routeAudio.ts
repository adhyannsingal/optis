type Cue = { audio: string; audio_type: string; generation: number };

/** Recheck cancellation and server generation after the asynchronous fetch. */
export async function playCurrentCue(
  fetchCue: () => Promise<{ cue: Cue | null }>,
  isCurrent: () => boolean,
  currentGeneration: () => number | undefined,
  player: Pick<HTMLAudioElement, "pause" | "play" | "src"> | null,
) {
  const { cue } = await fetchCue();
  if (!isCurrent() || !player || !cue?.audio ||
      !cue.audio_type.startsWith("audio/") || cue.generation !== currentGeneration()) return;
  player.pause();
  player.src = `data:${cue.audio_type};base64,${cue.audio}`;
  await player.play();
}
