import { activityRecap, type ActivityRecap } from "./activity";

type Snapshot = Readonly<{ state: "idle" | "checking" | "ready" | "blocked"; packet: ActivityRecap | null; message: string }>;
interface Dependencies {
  read: (voice: string, signal: AbortSignal) => Promise<ActivityRecap>;
  now?: () => number; schedule?: (tick: () => void) => () => void;
}
const initial: Snapshot = { state: "idle", packet: null, message: "Activity recap is hidden." };
export class ActivityRecapController {
  private snapshot = initial;
  private listeners = new Set<() => void>();
  private active = false;
  private generation = 0;
  private pending: AbortController | null = null;
  private startedAt = 0;
  private cancelTick?: () => void;
  constructor(private voice: string, private dependencies: Dependencies) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private now() { return this.dependencies.now?.() ?? Date.now(); }
  private update(value: Snapshot) { this.snapshot = value; this.listeners.forEach(listener => listener()); }
  start() {
    if (this.active) return;
    this.active = true;
    const schedule = this.dependencies.schedule ?? (tick => { const id = setInterval(tick, 1000); return () => clearInterval(id); });
    this.cancelTick = schedule(() => {
      if (this.snapshot.packet && Date.parse(this.snapshot.packet.display_expires_at) <= this.now()) this.update({ state: "blocked", packet: null, message: "Activity authorization expired." });
      if (this.pending && this.now() - this.startedAt >= 8000) {
        this.generation++; this.pending.abort(); this.pending = null; this.startedAt = this.now();
        this.update({ state: "blocked", packet: null, message: "Fresh authorization could not be confirmed." }); return;
      }
      if (!this.pending && this.now() - this.startedAt >= 4000) void this.refresh();
    });
    void this.refresh();
  }
  private async refresh() {
    if (!this.active || this.pending) return;
    const generation = ++this.generation, controller = new AbortController();
    this.pending = controller; this.startedAt = this.now();
    this.update({ state: "checking", packet: null, message: "Checking current recap consent and report release." });
    try {
      const result = await this.dependencies.read(this.voice, controller.signal);
      if (!this.active || generation !== this.generation || controller.signal.aborted) return;
      this.update({ state: "ready", packet: activityRecap(result, this.voice, this.now()), message: "Server activity receipts; audio playback is unverified." });
    } catch {
      if (this.active && generation === this.generation) this.update({ state: "blocked", packet: null, message: "Activity recap is unavailable. Check consent or the case workspace." });
    } finally { if (generation === this.generation) this.pending = null; }
  }
  stop() {
    this.active = false; this.generation++; this.pending?.abort(); this.pending = null;
    this.cancelTick?.(); this.cancelTick = undefined; this.update(initial);
  }
}
