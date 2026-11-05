/** Runtime contracts shared by the browser and its server gateway. No credentials. */
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const DIGEST = /^[0-9a-f]{64}$/;
export type JsonObject = Record<string, unknown>;
export type Decoder<T> = (value: unknown) => T;
export class ContractError extends Error {
  constructor(message = "The service returned an invalid response.") { super(message); }
}
export function object(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ContractError();
  return value as JsonObject;
}
function closed(value: unknown, keys: readonly string[]): JsonObject {
  const data = object(value); if (Object.keys(data).some(key => !keys.includes(key))) throw new ContractError("Check the entered fields."); return data;
}
export function text(value: unknown, max = 4000): string {
  if (typeof value !== "string" || !value.trim() || value.length > max) throw new ContractError();
  return value;
}
function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") throw new ContractError(); return value;
}
function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < min || value > max) throw new ContractError(); return value;
}
export function identifier(value: unknown): string {
  const result = text(value, 36); if (!UUID.test(result)) throw new ContractError("Enter a valid case identifier."); return result.toLowerCase();
}
export function digest(value: unknown): string {
  const result = text(value, 64); if (!DIGEST.test(result)) throw new ContractError("Enter a valid report or policy reference."); return result;
}
function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (!allowed.includes(value as T)) throw new ContractError(); return value as T;
}
function list<T>(value: unknown, decode: Decoder<T>, max = 100): T[] {
  if (!Array.isArray(value) || value.length > max) throw new ContractError(); return value.map(decode);
}
export function calendarDate(value: unknown): string {
  const result = text(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || result.startsWith("0000") || !Number.isFinite(Date.parse(result)) || new Date(result).toISOString().slice(0, 10) !== result) throw new ContractError("Enter a valid calendar date.");
  return result;
}
function verifiedDate(value: unknown): string {
  const result = text(value, 40); calendarDate(result.slice(0, 10));
  if (result.length !== 10 && (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(result) || !Number.isFinite(Date.parse(result)))) throw new ContractError(); return result;
}
export interface SourceReference { url: string; pdf_page: number; clause: string; quote: string }
export interface Citation { source: string; last_verified: string; references?: SourceReference[]; applicability_evidence?: SourceReference[]; condition_evidence?: SourceReference[] }
export interface Report { sentences: { text: string; citations: Citation[] }[] }
function reference(value: unknown): SourceReference {
  const data = object(value), url = new URL(text(data.url));
  if (url.protocol !== "https:" || url.username || url.password) throw new ContractError();
  return { url: url.href, pdf_page: integer(data.pdf_page, 1), clause: text(data.clause), quote: text(data.quote, 20_000) };
}
function citation(value: unknown): Citation {
  const data = object(value), result: Citation = { source: text(data.source), last_verified: verifiedDate(data.last_verified) };
  for (const key of ["references", "applicability_evidence", "condition_evidence"] as const) {
    if (data[key] !== undefined) result[key] = list(data[key], reference);
  }
  return result;
}
export const report: Decoder<Report> = value => {
  const sentences = list(object(value).sentences, item => {
    const data = object(item), citations = list(data.citations, citation);
    if (!citations.length) throw new ContractError(); return { text: text(data.text, 20_000), citations };
  }, 200);
  if (!sentences.length) throw new ContractError(); return { sentences };
};
export interface MessageResponse { session_id: string; reply: string; delivery_hold: boolean; missing_fields: string[]; escalation: boolean; notification_status: string; output: Report | null }
export const messageResponse: Decoder<MessageResponse> = value => {
  const data = object(value), held = boolean(data.delivery_hold);
  if (typeof data.reply !== "string" || data.reply.length > 50_000) throw new ContractError();
  return { session_id: identifier(data.session_id), reply: data.reply, delivery_hold: held,
    missing_fields: list(data.missing_fields, v => text(v, 100)), escalation: boolean(data.escalation),
    notification_status: text(data.notification_status, 100),
    output: !held && Array.isArray(object(data.output).sentences) ? report(data.output) : null };
};
export interface ReportStatus { turn_id: string; report_digest: string | null; status: "running" | "complete" | "failed"; delivery_hold: true }
export const reportStatusResponse: Decoder<ReportStatus> = value => {
  const data = object(value); if (data.delivery_hold !== true) throw new ContractError();
  return { turn_id: identifier(data.turn_id), report_digest: data.report_digest === null ? null : digest(data.report_digest), status: oneOf(data.status, ["running", "complete", "failed"]), delivery_hold: true };
};
export interface Review { report_digest: string; session_id: string; report: Report; revision: number; review_status: string; scenario: Scenario }
export const reviewResponse: Decoder<Review> = value => {
  const data = object(value); if (data.customer_delivery_authorized !== false) throw new ContractError();
  return { report_digest: digest(data.report_digest), session_id: identifier(data.session_id), report: report(data.report), revision: integer(data.revision),
    review_status: oneOf(data.review_status, ["pending", "approved", "revoked", "expired"]), scenario: scenario(data.scenario) };
};
export const capabilities = ["coverage_options", "adult_entry_ages", "base_ped_wait"] as const;
export interface Scenario { items: { publication_digest: string; capabilities: (typeof capabilities[number])[]; context: {
  transaction: "issue" | "renewal"; transaction_date: string; cover_basis: "individual" | "family_floater"; selected_options: string[];
  entry_age_years: number | null; residency: string | null; zone: string | null; portability: boolean | null; continuity: boolean | null;
} }[] }
export const scenario: Decoder<Scenario> = value => {
  const items = list(closed(value, ["items"]).items, value => {
    const item = closed(value, ["publication_digest", "capabilities", "context"]), context = closed(item.context, ["transaction", "transaction_date", "cover_basis", "selected_options", "entry_age_years", "residency", "zone", "portability", "continuity"]);
    const selected = list(context.selected_options, v => text(v), 20), checks = list(item.capabilities, v => oneOf(v, capabilities), 3);
    if (!checks.length || new Set(checks).size !== checks.length || new Set(selected).size !== selected.length) throw new ContractError();
    return { publication_digest: digest(item.publication_digest), capabilities: checks, context: {
      transaction: oneOf(context.transaction, ["issue", "renewal"]), transaction_date: calendarDate(context.transaction_date),
      cover_basis: oneOf(context.cover_basis, ["individual", "family_floater"]), selected_options: selected,
      entry_age_years: context.entry_age_years === null ? null : integer(context.entry_age_years, 0, 150),
      residency: context.residency === null ? null : text(context.residency, 100), zone: context.zone === null ? null : text(context.zone, 100),
      portability: context.portability === null ? null : boolean(context.portability), continuity: context.continuity === null ? null : boolean(context.continuity),
    } };
  }, 5);
  if (!items.length || new Set(items.map(item => item.publication_digest)).size !== items.length) throw new ContractError(); return { items };
};
export const scopes = ["process_comparison", "save_profile", "receive_updates"] as const;
export type ConsentScope = typeof scopes[number];
export const consentVersion = "2026-11-04";
export function consentRequest(value: unknown) {
  const data = object(value); if (Object.keys(data).some(key => !["scope", "action", "purpose_version"].includes(key))) throw new ContractError();
  if (data.purpose_version !== undefined && data.purpose_version !== consentVersion) throw new ContractError();
  return { scope: oneOf(data.scope, scopes), action: oneOf(data.action, ["grant", "revoke"]),
    ...(data.purpose_version === undefined ? {} : { purpose_version: consentVersion }) };
}
export function messageRequest(value: unknown) {
  const data = object(value); if (Object.keys(data).some(key => !["session_id", "user_message", "reviewed_comparison_request"].includes(key))) throw new ContractError();
  return { session_id: identifier(data.session_id), user_message: text(data.user_message, 4000).trim(),
    ...(data.reviewed_comparison_request === undefined ? {} : { reviewed_comparison_request: scenario(data.reviewed_comparison_request) }) };
}
export function decisionRequest(value: unknown) {
  const data = closed(value, ["request_key", "expected_revision", "action", "reason", "expires_at"]), action = oneOf(data.action, ["approve", "revoke"]), expiry = data.expires_at;
  if (typeof expiry === "string") verifiedDate(expiry);
  if ((action === "approve" && (typeof expiry !== "string" || !Number.isFinite(Date.parse(expiry)) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(expiry) || Date.parse(expiry) <= Date.now() || Date.parse(expiry) > Date.now() + 7 * 86400_000)) || (action === "revoke" && expiry !== null)) throw new ContractError("Choose a future approval expiry within seven days.");
  return { request_key: identifier(data.request_key), expected_revision: integer(data.expected_revision), action, reason: text(data.reason, 2000).trim(), expires_at: expiry as string | null };
}
