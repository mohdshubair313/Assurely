/** Authenticated same-origin control only; provider master/session secrets never arrive here. */
import { api } from "../api-client";
import { ContractError, identifier, object } from "../api-contracts";
import { validateConnection, type VoiceConnection } from "./controller";

export type DevelopmentSession = { sessionId: string; roomName: string; phase: string; state: string; allowed: boolean; expiresAt: number; endRequested: boolean; reservedSeconds: number; consumedSeconds: number };
export function sessionStatus(value: unknown): DevelopmentSession {
  const data = object(value);
  const expiry = Date.parse(String(data.expires_at));
  const phases = ["pending_create", "creating", "created", "binding", "ready", "connecting", "connected", "start_unknown", "terminating", "termination_unknown", "awaiting_usage", "ended"];
  if (data.synthetic !== true || typeof data.allowed !== "boolean" || !phases.includes(String(data.phase)) ||
      !["reserved", "active", "failed", "expired", "ended"].includes(String(data.state)) ||
      !Number.isFinite(expiry) || typeof data.end_requested !== "boolean" ||
      !Number.isSafeInteger(data.reserved_seconds) || Number(data.reserved_seconds) < 0 ||
      !Number.isSafeInteger(data.consumed_seconds) || Number(data.consumed_seconds) < 0 || Number(data.consumed_seconds) > Number(data.reserved_seconds) ||
      !(data.room_name === null || (typeof data.room_name === "string" && /^[A-Za-z0-9_-]{1,160}$/.test(data.room_name)))) throw new ContractError();
  return { sessionId: identifier(data.session_id), roomName: data.room_name ?? "", phase: String(data.phase), state: String(data.state),
    allowed: data.allowed, expiresAt: expiry, endRequested: data.end_requested, reservedSeconds: Number(data.reserved_seconds), consumedSeconds: Number(data.consumed_seconds) };
}
function scoped(expected: string) {
  return (value: unknown) => { const result = sessionStatus(value); if (result.sessionId !== expected) throw new ContractError(); return result; };
}
export function availability() { return api("voice/development/availability", value => {
  const data = object(value); if (typeof data.enabled !== "boolean" || data.synthetic !== true || data.billing_enabled !== false) throw new ContractError(); return data.enabled;
}); }
export function startDevelopment(key: string) { return api("voice/development/sessions", sessionStatus, { idempotency_key: identifier(key) }); }
export function readDevelopment(session: string) { return api(`voice/development/sessions/${identifier(session)}`, scoped(session)); }
export function authorizeDevelopment(session: string) { return api(`voice/development/sessions/${identifier(session)}/authorization`, scoped(session)); }
export function endDevelopment(session: string) { return api(`voice/development/sessions/${identifier(session)}/end`, scoped(session), {}); }
export function connectDevelopment(session: string) { return api(`voice/development/sessions/${identifier(session)}/connect`, value => {
  const status = scoped(session)(value), data = object(value);
  if (!status.allowed || status.endRequested || typeof data.url !== "string" || typeof data.token !== "string") throw new ContractError();
  const result: VoiceConnection = { sessionId: status.sessionId, roomName: status.roomName, expiresAt: status.expiresAt,
    url: data.url, token: data.token, synthetic: true };
  validateConnection(result, Date.now()); return result;
}, {}); }
