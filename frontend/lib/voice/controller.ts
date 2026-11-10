/** Browser media only. This controller has no dispatch, settlement or provider-end authority. */
export type MediaState = "idle" | "connecting" | "connected" | "reconnecting" | "disconnected" | "blocked";
export type MediaSnapshot = Readonly<{ state: MediaState; microphone: boolean; playbackBlocked: boolean; quality: string; message: string }>;
export type VoiceConnection = Readonly<{ sessionId: string; roomName: string; url: string; token: string; expiresAt: number; synthetic: true }>;
export type VoiceConsent = Readonly<{ aiDisclosureAccepted: boolean; microphone: boolean; vendorProcessing: boolean }>;
export type AuthorizationReceipt = Readonly<{ sessionId: string; roomName: string; allowed: boolean; expiresAt: number }>;
export interface MediaRoom {
  connect(url: string, token: string): Promise<void>;
  disconnect(): Promise<void>;
  microphone(enabled: boolean): Promise<void>;
  startAudio(): Promise<void>;
  subscribe(listener: (event: "connected" | "reconnecting" | "disconnected" | "playback-blocked" | "quality", value?: string) => void): () => void;
}
export interface VoiceMediaDependencies {
  createRoom(): MediaRoom;
  /** Must recheck the same authenticated session and current consent on the server. No new dispatch. */
  authorize(sessionId: string): Promise<AuthorizationReceipt>;
  now?: () => number;
  schedule?: (callback: () => void) => () => void;
}
const initial: MediaSnapshot = { state: "idle", microphone: false, playbackBlocked: false, quality: "unknown", message: "Audio is not connected." };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const hosts = new Set(["rtc.vaanivoice.ai", "livekit.vaanivoice.ai"]);
export function validateConnection(value: VoiceConnection, now: number): void {
  const url = new URL(value.url);
  if (!uuid.test(value.sessionId) || !/^[A-Za-z0-9_-]{1,200}$/.test(value.roomName) || value.synthetic !== true ||
      url.protocol !== "wss:" || !hosts.has(url.hostname) || url.port || url.username || url.password || url.search || url.hash ||
      typeof value.token !== "string" || value.token.length < 20 || value.token.length > 8192 || /\s/.test(value.token) ||
      !Number.isFinite(value.expiresAt) || value.expiresAt <= now || value.expiresAt > now + 300_000) {
    throw new Error("Connection material is unavailable or expired.");
  }
}
function hasConsent(consent: VoiceConsent): boolean {
  return consent.aiDisclosureAccepted === true && consent.microphone === true && consent.vendorProcessing === true;
}
function bounded<T>(operation: Promise<T>, milliseconds = 8000): Promise<T> {
  let timeout: ReturnType<typeof setTimeout>;
  return Promise.race([operation, new Promise<never>((_, reject) => {
    timeout = setTimeout(() => reject(new Error("Operation timed out.")), milliseconds);
  })]).finally(() => clearTimeout(timeout));
}
export class VoiceMediaController {
  private snapshot: MediaSnapshot = initial;
  private listeners = new Set<() => void>();
  private room: MediaRoom | null = null;
  private connection: VoiceConnection | null = null;
  private consent = false;
  private generation = 0;
  private cancelEvents?: () => void;
  private cancelHeartbeat?: () => void;
  private checking = false;
  private microphoneBusy = false;
  constructor(private dependencies: VoiceMediaDependencies) {}
  getSnapshot = (): MediaSnapshot => this.snapshot;
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private update(patch: Partial<MediaSnapshot>) { this.snapshot = { ...this.snapshot, ...patch }; this.listeners.forEach(listener => listener()); }
  private now() { return this.dependencies.now?.() ?? Date.now(); }
  private async authorized(connection: VoiceConnection): Promise<boolean> {
    if (!this.consent || connection.expiresAt <= this.now()) return false;
    const receipt = await bounded(this.dependencies.authorize(connection.sessionId));
    return receipt.allowed === true && receipt.sessionId === connection.sessionId && receipt.roomName === connection.roomName && Number.isFinite(receipt.expiresAt) && receipt.expiresAt > this.now();
  }
  async connect(connection: VoiceConnection, consent: VoiceConsent): Promise<void> {
    if (this.room || ["connecting", "connected", "reconnecting"].includes(this.snapshot.state)) return;
    const generation = ++this.generation;
    try {
      validateConnection(connection, this.now());
      if (!hasConsent(consent)) throw new Error("Consent required.");
      this.consent = true;
      this.update({ ...initial, state: "connecting", message: "Checking this synthetic session before audio connection." });
      if (!await this.authorized(connection)) throw new Error("Authorization unavailable.");
      if (generation !== this.generation) return;
      const room = this.dependencies.createRoom();
      this.room = room; this.connection = connection;
      this.cancelEvents = room.subscribe((event, value) => {
        if (generation !== this.generation) return;
        if (event === "disconnected") void this.detach("disconnected", "Browser audio disconnected. Provider status and reserved usage require server confirmation.");
        if (event === "reconnecting") {
          this.update({ state: "reconnecting", microphone: false, message: "Reconnecting to the same session. Microphone remains muted." });
          void room.microphone(false).catch(() => { if (generation === this.generation) return this.detach("blocked", "Microphone state could not be confirmed."); });
        }
        if (event === "connected") void this.checkAuthorization();
        if (event === "playback-blocked") this.update({ playbackBlocked: true });
        if (event === "quality") this.update({ quality: ["excellent", "good", "poor", "lost"].includes(value ?? "") ? value! : "unknown" });
      });
      await bounded(room.connect(connection.url, connection.token).then(async () => {
        if (generation !== this.generation) await room.disconnect().catch(() => {});
      }));
      if (generation !== this.generation) { await room.disconnect().catch(() => {}); return; }
      if (!await this.authorized(connection)) throw new Error("Authorization expired.");
      if (generation !== this.generation) { await room.disconnect().catch(() => {}); return; }
      this.update({ state: "connected", microphone: false, message: "Synthetic AI audio connected. Enable your microphone when ready." });
      const schedule = this.dependencies.schedule ?? (callback => { const timer = setInterval(callback, 5000); return () => clearInterval(timer); });
      this.cancelHeartbeat = schedule(() => { void this.checkAuthorization(); });
    } catch { if (generation === this.generation) await this.detach("blocked", "Audio could not connect securely. Check consent and session authorization."); }
  }
  /** Called by a timer and SDK reconnect events; never dispatches a replacement call. */
  async checkAuthorization(): Promise<void> {
    if (this.checking || !this.connection || !this.room) return;
    this.checking = true;
    const generation = this.generation;
    try {
      if (!await this.authorized(this.connection)) throw new Error("Authorization unavailable.");
      if (generation === this.generation && this.snapshot.state === "reconnecting") this.update({ state: "connected", message: "Same session reconnected. Microphone is muted; enable it to resume." });
    } catch { if (generation === this.generation) await this.detach("blocked", "Session authorization could not be confirmed. Audio disconnected; provider status remains pending."); }
    finally { this.checking = false; }
  }
  async setMicrophone(enabled: boolean): Promise<void> {
    if (this.microphoneBusy || !this.room || !this.connection || this.snapshot.state !== "connected") return;
    this.microphoneBusy = true;
    const room = this.room; const generation = this.generation;
    try {
      if (enabled && !await this.authorized(this.connection)) throw new Error("Consent unavailable.");
      if (generation !== this.generation) return;
      await bounded(room.microphone(enabled).then(async () => {
        if (generation !== this.generation) await room.microphone(false).catch(() => {});
      }));
      if (generation !== this.generation) { await room.microphone(false).catch(() => {}); return; }
      this.update({ microphone: enabled, message: enabled ? "Microphone is transmitting to the disclosed AI voice service." : "Microphone is muted." });
    } catch { if (generation === this.generation) await this.detach("blocked", "Microphone permission or authorization failed. Browser audio disconnected."); }
    finally { this.microphoneBusy = false; }
  }
  async enablePlayback(): Promise<void> {
    const room = this.room; const generation = this.generation;
    if (!room) return;
    try { await bounded(room.startAudio()); if (generation === this.generation) this.update({ playbackBlocked: false }); }
    catch { if (generation === this.generation) this.update({ playbackBlocked: true, message: "Your browser requires permission to play audio." }); }
  }
  async revokeConsent(): Promise<void> {
    this.consent = false;
    await this.detach("blocked", "Local audio consent withdrawn. Server revocation and provider termination must be confirmed separately.");
  }
  async disconnect(): Promise<void> { await this.detach("disconnected", "Browser audio disconnected. This does not confirm provider termination or release reserved usage."); }
  private async detach(state: MediaState, message: string): Promise<void> {
    ++this.generation;
    this.cancelHeartbeat?.(); this.cancelHeartbeat = undefined;
    this.cancelEvents?.(); this.cancelEvents = undefined;
    const room = this.room; this.room = null; this.connection = null; this.consent = false;
    this.update({ state, microphone: false, playbackBlocked: false, message });
    if (room) {
      await bounded(room.microphone(false), 2000).catch(() => {});
      await bounded(room.disconnect(), 2000).catch(() => {});
    }
  }
}
