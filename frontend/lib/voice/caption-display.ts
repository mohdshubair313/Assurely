import { captionPacket, type VoiceCaseBinding, type ReviewedCaptionPacket } from "./case-contracts";

export type CaptionDisplaySnapshot = Readonly<{
  state: "idle" | "checking" | "ready" | "blocked";
  packet: ReviewedCaptionPacket | null; message: string;
}>;
export interface CaptionDisplayDependencies {
  read: (binding: VoiceCaseBinding, signal: AbortSignal) => Promise<ReviewedCaptionPacket>;
  now?: () => number;
  schedule?: (tick: () => void) => () => void;
}
const initial: CaptionDisplaySnapshot = { state: "idle", packet: null, message: "Reviewed text is hidden." };
/** GET-only presentation controller; never dispatches audio or grants future access. */
export class CaptionDisplayController {
  private snapshot = initial;
  private listeners = new Set<() => void>();
  private active = false;
  private generation = 0;
  private pending: AbortController | null = null;
  private startedAt = 0;
  private cancelTick?: () => void;
  constructor(private binding: VoiceCaseBinding, private dependencies: CaptionDisplayDependencies) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private now() { return this.dependencies.now?.() ?? Date.now(); }
  private update(value: CaptionDisplaySnapshot) { this.snapshot = value; this.listeners.forEach(listener => listener()); }
  start() {
    if (this.active) return;
    this.active = true;
    const schedule = this.dependencies.schedule ?? (tick => { const id = setInterval(tick, 1000); return () => clearInterval(id); });
    this.cancelTick = schedule(() => {
      if (this.snapshot.packet && Date.parse(this.snapshot.packet.expires_at) <= this.now()) {
        this.update({ state: "blocked", packet: null, message: "Reviewed text authorization expired. Checking again." });
      }
      if (this.pending && this.now() - this.startedAt >= 8000) {
        this.generation++; this.pending.abort(); this.pending = null;
        this.update({ state: "blocked", packet: null, message: "Fresh authorization could not be confirmed." });
        this.startedAt = this.now();
        return;
      }
      if (!this.pending && this.now() - this.startedAt >= 4000) void this.refresh();
    });
    void this.refresh();
  }
  private async refresh() {
    if (!this.active || this.pending) return;
    const generation = ++this.generation, controller = new AbortController();
    this.pending = controller; this.startedAt = this.now();
    this.update({ state: "checking", packet: null, message: "Checking current case, consent, sources and human approval." });
    try {
      const result = await this.dependencies.read(this.binding, controller.signal);
      if (!this.active || generation !== this.generation || controller.signal.aborted) return;
      const packet = captionPacket(result, this.binding, this.now());
      this.update({ state: "ready", packet, message: "Reviewed report text; not a live voice transcript." });
    } catch {
      if (this.active && generation === this.generation) this.update({ state: "blocked", packet: null, message: "Reviewed text is unavailable or held. Check your case workspace." });
    } finally { if (generation === this.generation) this.pending = null; }
  }
  stop() {
    this.active = false; this.generation++; this.pending?.abort(); this.pending = null;
    this.cancelTick?.(); this.cancelTick = undefined; this.update(initial);
  }
}
