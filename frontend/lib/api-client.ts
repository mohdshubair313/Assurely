/** Same-origin transport. No bearer credentials or health details in browser storage. */
import { ContractError, object, identifier, digest, report, messageRequest, messageResponse,
  reportStatusResponse, reviewResponse, consentRequest, decisionRequest, text, type Decoder,
  consentVersion, scopes, type ConsentScope, type Scenario } from "./api-contracts";
export type { Citation, Report, SourceReference, MessageResponse, ReportStatus, Review, ConsentScope, Scenario } from "./api-contracts";
export class ApiError extends Error {
  constructor(message: string, public status = 0, public retryAfter: number | null = null) { super(message); }
}
export interface RequestOptions { signal?: AbortSignal; method?: "GET" | "POST" | "DELETE" }
export async function api<T>(path: string, decode: Decoder<T>, body?: unknown, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController(), abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(abort, 125_000);
  try {
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const response = await fetch(`/api/backend/${path}`, {
      method: options.method ?? (body === undefined ? "GET" : "POST"), cache: "no-store", credentials: "same-origin",
      signal: controller.signal, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      await response.body?.cancel();
      const messages: Record<number, string> = {
        401: "Sign in again to continue with this case.", 403: "Your account cannot perform this action.",
        404: "This case or report could not be found.", 409: "The case or review changed, is still active, or remains held. Refresh its status before retrying.",
        413: "This request is too large. Reduce the details and try again.", 422: "Check the entered details and try again.",
        429: "Too many requests. Wait before trying again.",
      };
      const retry = Number(response.headers.get("retry-after"));
      throw new ApiError(messages[response.status] ?? "The service is unavailable. Refresh the case status before retrying.", response.status,
        response.headers.has("retry-after") && Number.isFinite(retry) && retry >= 0 ? retry : null);
    }
    if (response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") throw new ContractError();
    const data: unknown = await response.json();
    if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
    return decode(data);
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (error instanceof ApiError || error instanceof ContractError) throw error;
    throw new ApiError("The request could not be confirmed. Refresh the case status before retrying.");
  } finally { clearTimeout(timeout); options.signal?.removeEventListener("abort", abort); }
}
export async function postMessage(session: string, message: string, scenario?: Scenario, options?: RequestOptions) {
  const body = messageRequest({ session_id: session, user_message: message, ...(scenario ? { reviewed_comparison_request: scenario } : {}) });
  const result = await api("message", messageResponse, body, options);
  if (result.session_id !== body.session_id) throw new ContractError(); return result;
}
export function reportStatus(session: string, options?: RequestOptions) { return api(`sessions/${identifier(session)}/report-status`, reportStatusResponse, undefined, options); }
export function readSession(session: string, options?: RequestOptions) {
  const expected = identifier(session);
  return api(`session/${expected}`, value => {
    const data = object(value);
    if (identifier(data.session_id) !== expected || !["active", "completed"].includes(String(data.status)) || !Array.isArray(data.messages) || !Array.isArray(data.citations)) throw new ContractError();
    return { status: text(data.status, 20) };
  }, undefined, options);
}
export function readReview(reference: string, options?: RequestOptions) {
  const expected = digest(reference);
  return api(`advisor-reviews/${expected}`, value => { const result = reviewResponse(value); if (result.report_digest !== expected) throw new ContractError(); return result; }, undefined, options);
}
export function snapshotReview(session: string, options?: RequestOptions) {
  const id = identifier(session);
  return api(`advisor-reviews/sessions/${id}/snapshot`, value => {
    const data = object(value); if (identifier(data.session_id) !== id || data.customer_delivery_authorized !== false) throw new ContractError(); return { report_digest: digest(data.report_digest) };
  }, {}, options);
}
export function decideReview(reference: string, command: unknown, options?: RequestOptions) {
  const expected = digest(reference), body = decisionRequest(command);
  return api(`advisor-reviews/${expected}/decisions`, value => {
    const data = object(value);
    if (digest(data.report_digest) !== expected || data.action !== body.action || data.revision !== body.expected_revision + 1 || data.customer_delivery_authorized !== false) throw new ContractError();
    identifier(data.event_id); return { revision: data.revision };
  }, body, options);
}
export function releaseReport(session: string, turn: string, reference: string, key: string, options?: RequestOptions) {
  const expected = digest(reference), turnId = identifier(turn);
  return api(`sessions/${identifier(session)}/report-release`, value => {
    const data = object(value), receipt = object(data.release_receipt);
    if (data.delivery_hold !== false || receipt.scope !== "transaction_time_release_decision" || digest(receipt.report_digest) !== expected || identifier(receipt.turn_id) !== turnId) throw new ContractError();
    identifier(receipt.id); identifier(receipt.advisor_event_id); return report(data.output);
  }, { turn_id: turnId, report_digest: expected, request_key: identifier(key) }, options);
}
export function recoverTurn(session: string, turn: string, key: string, options?: RequestOptions) {
  const turnId = identifier(turn);
  return api(`sessions/${identifier(session)}/recover-turn`, value => {
    const data = object(value);
    if (identifier(data.turn_id) !== turnId || data.action !== "interrupted_turn_closed" || data.delivery_hold !== true || data.historical_receipt !== true) throw new ContractError();
    identifier(data.receipt_id); return { closed: true };
  }, { turn_id: turnId, request_key: identifier(key) }, options);
}
export function updateConsent(scope: ConsentScope, action: "grant" | "revoke", options?: RequestOptions) {
  const body = consentRequest({ scope, action, purpose_version: consentVersion });
  return api("consent", value => { const data = object(value);
    if (data.scope !== scope || data.status !== (action === "grant" ? "granted" : "revoked")) throw new ContractError();
    identifier(data.user_id); return { status: text(data.status), timestamp: text(data.timestamp, 40) };
  }, body, options);
}
export function deleteProfileMemory(options?: RequestOptions) {
  return api("profile-memory", value => { const data = object(value); identifier(data.user_id);
    if (typeof data.deleted !== "boolean") throw new ContractError(); return { deleted: data.deleted };
  }, {}, { ...options, method: "DELETE" });
}

export function getConsents(options?: RequestOptions) {
  return api("me/consents", value => {
    const data = object(value);
    if (data.purpose_version !== consentVersion || !Array.isArray(data.purposes) || data.purposes.length !== scopes.length) throw new ContractError();
    const purposes = data.purposes.map(value => {
      const row = object(value);
      if (!scopes.includes(row.scope as ConsentScope) || typeof row.granted !== "boolean") throw new ContractError();
      return { scope: row.scope as ConsentScope, granted: row.granted, description: text(row.description, 500) };
    });
    if (new Set(purposes.map(row => row.scope)).size !== scopes.length) throw new ContractError();
    return purposes;
  }, undefined, options);
}
