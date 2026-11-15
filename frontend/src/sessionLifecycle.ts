/** Order responses within a client session; server generations may reset on restart. */
export class SessionRequests {
  epoch = 0;
  issued = 0;
  accepted = 0;
  begin() { return { epoch: this.epoch, sequence: ++this.issued }; }
  current(ticket: { epoch: number }) { return ticket.epoch === this.epoch; }
  accept(ticket: { epoch: number; sequence: number }) {
    if (!this.current(ticket) || ticket.sequence < this.accepted) return false;
    this.accepted = ticket.sequence;
    return true;
  }
  reset() { this.epoch++; this.accepted = 0; }
}

export function appendEvent<T>(events: T[], event: T) {
  return [...events, event].slice(-30);
}

export function canCancelRecording(state: string) {
  return state === "starting" || state === "recording";
}

export function disposeRecording(recorder: MediaRecorder | null | undefined, media: MediaStream | null) {
  try {
    if (recorder) {
      recorder.onstop = null;
      recorder.onerror = null;
      recorder.ondataavailable = null;
      if (recorder.state === "recording") recorder.stop();
    }
  } finally {
    media?.getTracks().forEach(track => track.stop());
  }
}

/** Own the granted stream even if constructor, configuration or start fails. */
export function startRecorder(
  media: MediaStream,
  create: () => MediaRecorder,
  configure: (recorder: MediaRecorder) => void,
) {
  let recorder: MediaRecorder | undefined;
  try {
    recorder = create();
    configure(recorder);
    recorder.start();
    return recorder;
  } catch (error) {
    disposeRecording(recorder, media);
    throw error;
  }
}
