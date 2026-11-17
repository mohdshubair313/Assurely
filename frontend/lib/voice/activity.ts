import { api } from "../api-client";
import { ContractError, calendarDate, digest, identifier, object, text } from "../api-contracts";
import { reviewedSentences } from "./case-contracts";

export interface ActivityEvent {
  response_id: number; intent: "report_read" | "unsupported";
  status: "response_sent" | "delivery_uncertain" | "interrupted" | "failed" | "pending";
  answer_kind: "report" | "operational" | null; created_at: string; completed_at: string | null;
}
export interface ActivityRecap {
  kind: "voice_session_activity_recap"; voice_session_id: string; session_state: string;
  generated_at: string; display_expires_at: string; transcript_stored: false; audio_delivery_verified: false;
  events: ActivityEvent[]; report_availability: "available" | "not_sent" | "unavailable";
  reviewed_report: null | { binding_id: string; case_id: string; turn_id: string; report_digest: string;
    authorized_at: string; display_expires_at: string; sentences: ReturnType<typeof reviewedSentences> };
}
function closed(value: unknown, keys: string[]) {
  const row = object(value);
  if (Object.keys(row).length !== keys.length || Object.keys(row).some(key => !keys.includes(key))) throw new ContractError();
  return row;
}
function stamp(value: unknown) {
  const result = text(value, 40);
  calendarDate(result.slice(0, 10));
  if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(result) || !Number.isFinite(Date.parse(result))) throw new ContractError();
  return result;
}
export function activityRecap(value: unknown, expectedVoice: string, now = Date.now()): ActivityRecap {
  const row = closed(value, ["kind", "voice_session_id", "session_state", "generated_at", "display_expires_at", "transcript_stored", "audio_delivery_verified", "events", "reviewed_report", "report_availability"]);
  if (row.kind !== "voice_session_activity_recap" || identifier(row.voice_session_id) !== identifier(expectedVoice) ||
    row.transcript_stored !== false || row.audio_delivery_verified !== false ||
    !["reserved", "active", "ended", "expired", "failed"].includes(String(row.session_state)) ||
    !["available", "not_sent", "unavailable"].includes(String(row.report_availability)) ||
    !Array.isArray(row.events) || row.events.length > 128) throw new ContractError();
  const generated_at = stamp(row.generated_at), display_expires_at = stamp(row.display_expires_at);
  const deadline = Date.parse(display_expires_at), generated = Date.parse(generated_at);
  if (deadline <= now || deadline > now + 15_000 || deadline > generated + 10_000 || generated > now + 2_000) throw new ContractError();
  let previous = 0;
  const events = row.events.map(value => {
    const event = closed(value, ["response_id", "intent", "status", "answer_kind", "created_at", "completed_at"]);
    if (!Number.isSafeInteger(event.response_id) || Number(event.response_id) <= previous || Number(event.response_id) > 2147483647 ||
      !["report_read", "unsupported"].includes(String(event.intent)) ||
      !["response_sent", "delivery_uncertain", "interrupted", "failed", "pending"].includes(String(event.status)) ||
      ![null, "report", "operational"].includes(event.answer_kind as null | string) ||
      (event.intent === "unsupported" && event.answer_kind === "report")) throw new ContractError();
    previous = Number(event.response_id);
    const created_at = stamp(event.created_at), completed_at = event.completed_at === null ? null : stamp(event.completed_at);
    if (Date.parse(created_at) > generated || (event.status === "response_sent") !== (completed_at !== null) ||
      (completed_at && (Date.parse(completed_at) < Date.parse(created_at) || Date.parse(completed_at) > generated)) ||
      (["response_sent", "delivery_uncertain"].includes(String(event.status)) && event.answer_kind === null)) throw new ContractError();
    return { ...event, created_at, completed_at } as unknown as ActivityEvent;
  });
  const factualSent = events.some(event => event.status === "response_sent" && event.answer_kind === "report");
  let reviewed_report: ActivityRecap["reviewed_report"] = null;
  if ((row.report_availability === "not_sent") === factualSent) throw new ContractError();
  if (row.report_availability === "available") {
    const packet = closed(row.reviewed_report, ["binding_id", "case_id", "turn_id", "report_digest", "authorized_at", "display_expires_at", "sentences"]);
    const authorized_at = stamp(packet.authorized_at);
    if (packet.display_expires_at !== display_expires_at || Date.parse(authorized_at) > generated) throw new ContractError();
    reviewed_report = { binding_id: identifier(packet.binding_id), case_id: identifier(packet.case_id), turn_id: identifier(packet.turn_id),
      report_digest: digest(packet.report_digest), authorized_at, display_expires_at,
      sentences: reviewedSentences(packet.sentences, display_expires_at, now) };
  } else if (row.reviewed_report !== null) throw new ContractError();
  return { kind: "voice_session_activity_recap", voice_session_id: expectedVoice, session_state: String(row.session_state), generated_at,
    display_expires_at, transcript_stored: false, audio_delivery_verified: false, events, reviewed_report,
    report_availability: row.report_availability as ActivityRecap["report_availability"] };
}
export function readActivityRecap(voice: string, signal?: AbortSignal) {
  const selected = identifier(voice);
  return api(`voice/development/sessions/${selected}/activity-recap`, value => activityRecap(value, selected), undefined, { signal });
}
