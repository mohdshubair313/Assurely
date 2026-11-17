import { text } from "../api-contracts";

/** Account-scoped opaque recovery only. Never infer an owner for legacy global keys. */
export function workspaceStorageKeys(account: string) {
  const selected = encodeURIComponent(text(account, 200));
  return { session: `assurely-synthetic-voice-session:${selected}`, attempt: `assurely-synthetic-voice-attempt:${selected}` };
}

export function requireCurrent(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
}

/** Stable owner workspace; effect reactivation also fences React development replays. */
export class WorkspaceLifetime {
  private controller = new AbortController();
  get signal() { return this.controller.signal; }
  activate() {
    this.controller.abort();
    this.controller = new AbortController();
    return this.controller;
  }
}

/** A permission dialog can resolve after unmount. Always close that local probe. */
export async function probeMicrophone(signal: AbortSignal, getMedia: () => Promise<MediaStream>) {
  requireCurrent(signal);
  const stream = await getMedia();
  try { requireCurrent(signal); }
  finally { stream.getTracks().forEach(track => track.stop()); }
}

/** Check after every awaited side effect so a replaced account cannot advance a chain. */
export async function currentStep<T>(signal: AbortSignal, action: () => Promise<T>): Promise<T> {
  requireCurrent(signal);
  const result = await action();
  requireCurrent(signal);
  return result;
}
