/** Reviewed text is a browser companion, never a claim about spoken audio. */
import { ContractError, calendarDate, digest, identifier, object, report, text, type Citation } from "../api-contracts";

export interface VoiceCaseBinding {
  binding_id: string; voice_session_id: string; case_id: string; turn_id: string;
  report_digest: string; requested_at: string; delivery_authorized: false;
}
export interface ReviewedCaptionPacket extends VoiceCaseBinding {
  sentences: { id: string; index: number; text: string; citations: (Citation & { id: string; url: string; expires_at: string })[] }[];
  expires_at: string; safe_for_display: true; caption_scope: "authorized_report_excerpt";
  realtime_transcript: false; external_speech_enabled: false;
}
function closed(value: unknown, keys: string[]) {
  const data = object(value);
  if (Object.keys(data).some(key => !keys.includes(key))) throw new ContractError();
  return data;
}
function stamp(value: unknown) {
  const result = text(value, 40);
  calendarDate(result.slice(0, 10));
  if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(result) || !Number.isFinite(Date.parse(result))) throw new ContractError();
  return result;
}
function sourceURL(value: unknown) {
  const raw = text(value, 4096);
  if (/[\s\u0000-\u001f\u007f\\]/.test(raw)) throw new ContractError();
  const url = new URL(raw);
  if (url.protocol !== "https:" || url.username || url.password || url.port === "0") throw new ContractError();
  return url.href;
}
export function bindCaseCommand(value: unknown) {
  const data = closed(value, ["case_id", "idempotency_key"]);
  return { case_id: identifier(data.case_id), idempotency_key: identifier(data.idempotency_key) };
}
/** Exactly two string members; inspect decoded names before JSON.parse loses duplicates. */
export function bindCaseJSONCommand(raw: string) {
  const quoted = '"(?:[^"\\\\]|\\\\.)*"';
  if (!new RegExp(`^\\s*\\{\\s*${quoted}\\s*:\\s*${quoted}\\s*,\\s*${quoted}\\s*:\\s*${quoted}\\s*\\}\\s*$`).test(raw)) throw new ContractError();
  const pairs = [...raw.matchAll(new RegExp(`(${quoted})\\s*:\\s*${quoted}`, "g"))];
  if (pairs.length !== 2 || new Set(pairs.map(pair => JSON.parse(pair[1]))).size !== 2) throw new ContractError();
  return bindCaseCommand(JSON.parse(raw));
}
const bindingKeys = ["binding_id", "voice_session_id", "case_id", "turn_id", "report_digest", "requested_at", "delivery_authorized"];
export function caseBinding(value: unknown): VoiceCaseBinding {
  const data = object(value);
  if (data.delivery_authorized !== false) throw new ContractError();
  return { binding_id: identifier(data.binding_id), voice_session_id: identifier(data.voice_session_id),
    case_id: identifier(data.case_id), turn_id: identifier(data.turn_id), report_digest: digest(data.report_digest),
    requested_at: stamp(data.requested_at), delivery_authorized: false };
}
export function captionPacket(value: unknown, binding: VoiceCaseBinding, now = Date.now()): ReviewedCaptionPacket {
  const data = closed(value, [...bindingKeys, "sentences", "expires_at", "safe_for_display", "caption_scope", "realtime_transcript", "external_speech_enabled"]);
  const selected = caseBinding(data);
  if (bindingKeys.some(key => selected[key as keyof VoiceCaseBinding] !== binding[key as keyof VoiceCaseBinding]) ||
      data.safe_for_display !== true || data.caption_scope !== "authorized_report_excerpt" ||
      data.realtime_transcript !== false || data.external_speech_enabled !== false) throw new ContractError();
  const expires_at = stamp(data.expires_at), deadline = Date.parse(expires_at);
  if (deadline <= now || deadline > now + 15_000 || !Array.isArray(data.sentences) || data.sentences.length > 32) throw new ContractError();
  const decoded = report({ sentences: data.sentences });
  const sentences = data.sentences.map((value, index) => {
    const row = closed(value, ["id", "index", "text", "citations"]);
    if (row.id !== `sentence-${index + 1}` || row.index !== index || text(row.text, 4096) !== decoded.sentences[index].text) throw new ContractError();
    if (!Array.isArray(row.citations)) throw new ContractError();
    const citations = row.citations.map((value, citationIndex) => {
      const citation = closed(value, ["id", "source", "last_verified", "url", "expires_at", "references", "applicability_evidence", "condition_evidence"]);
      text(citation.id, 300);
      const url = sourceURL(citation.url);
      if (Date.parse(stamp(citation.expires_at)) < deadline ||
          String(citation.last_verified).slice(0, 10) > new Date(now).toISOString().slice(0, 10)) throw new ContractError();
      for (const key of ["references", "applicability_evidence", "condition_evidence"]) {
        if (!Array.isArray(citation[key]) || citation[key].length > 20) throw new ContractError();
        citation[key].forEach(reference => sourceURL(object(reference).url));
      }
      if (!Array.isArray(citation.references) || !citation.references.length) throw new ContractError();
      return { ...decoded.sentences[index].citations[citationIndex], id: text(citation.id, 300), url, expires_at: stamp(citation.expires_at) };
    });
    return { id: String(row.id), index, text: decoded.sentences[index].text, citations };
  });
  return { ...selected, sentences, expires_at, safe_for_display: true, caption_scope: "authorized_report_excerpt", realtime_transcript: false, external_speech_enabled: false };
}
