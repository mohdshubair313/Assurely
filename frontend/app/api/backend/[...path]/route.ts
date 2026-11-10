import { NextResponse } from "next/server";
import { accessToken, sameOrigin } from "@/lib/server-session";
import { ContractError, object, identifier, messageRequest, consentRequest, decisionRequest, digest } from "@/lib/api-contracts";
import { humanReviewCommand, humanReviewJSONCommand } from "@/lib/api-contracts";
import { bindCaseCommand, bindCaseJSONCommand } from "@/lib/voice/case-contracts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 150;

const uuid = "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}";
const digestPattern = "[a-f0-9]{64}";
const routes: [string, RegExp][] = [
  ["GET", /^me(?:\/consents)?$/],
  ["GET", /^voice\/entitlement$/],
  ["GET", /^voice\/active$/],
  ["GET", /^voice\/development\/(?:availability|release-status)$/],
  ["POST", /^voice\/development\/(?:sessions|billing\/checkout)$/],
  ["GET", new RegExp(`^voice/development/cases/${uuid}/evidence$`)],
  ["POST", new RegExp(`^voice/development/cases/${uuid}/turn$`)],
  ["POST", /^voice\/development\/recaps$/],
  ["GET", new RegExp(`^voice/development/recaps/${uuid}$`)],
  ["DELETE", new RegExp(`^voice/development/recaps/${uuid}$`)],
  ["GET", new RegExp(`^voice/development/sessions/${uuid}(?:/authorization)?$`)],
  ["POST", new RegExp(`^voice/development/sessions/${uuid}/(?:connect|end)$`)],
  ["GET", new RegExp(`^voice/development/sessions/${uuid}/(?:case-binding|captions)$`)],
  ["POST", new RegExp(`^voice/development/sessions/${uuid}/case-binding$`)],
  ["POST", /^voice\/sessions$/],
  ["GET", new RegExp(`^voice/sessions/${uuid}$`)],
  ["POST", new RegExp(`^voice/sessions/${uuid}/(?:end|turn)$`)],
  ["POST", /^message$/],
  ["POST", /^consent$/],
  ["DELETE", /^profile-memory$/],
  ["GET", new RegExp(`^session/${uuid}$`)],
  ["GET", new RegExp(`^sessions/${uuid}/report-status$`)],
  ["GET", new RegExp(`^sessions/${uuid}/human-review$`)],
  ["POST", new RegExp(`^sessions/${uuid}/human-review$`)],
  ["POST", new RegExp(`^sessions/${uuid}/(?:report-release|recover-turn)$`)],
  ["POST", new RegExp(`^advisor-reviews/sessions/${uuid}/snapshot$`)],
  ["GET", new RegExp(`^advisor-reviews/${digestPattern}$`)],
  ["POST", new RegExp(`^advisor-reviews/${digestPattern}/decisions$`)],
];
const empty = (status: number) => new Response(null, { status, headers: { "Cache-Control": "no-store" } });

function command(path: string, value: unknown): unknown {
  const data = object(value);
  if (path === "message") return messageRequest(data);
  if (path === "consent") return consentRequest(data);
  if (/\/human-review$/.test(path)) return humanReviewCommand(data);
  if (/\/case-binding$/.test(path)) return bindCaseCommand(data);
  if (/^voice\/development\/cases\/.+\/turn$/.test(path)) {
    if (Object.keys(data).length !== 1 || typeof data.text !== "string" || !data.text.trim() || data.text.length > 4000) throw new ContractError();
    return { text: data.text };
  }
  if (path === "voice/development/recaps") {
    if (Object.keys(data).some(key => !["idempotency_key", "case_id"].includes(key))) throw new ContractError();
    return { idempotency_key: identifier(data.idempotency_key), case_id: identifier(data.case_id) };
  }
  if (["voice/development/sessions", "voice/development/billing/checkout"].includes(path)) {
    if (Object.keys(data).length !== 1) throw new ContractError();
    return { idempotency_key: identifier(data.idempotency_key) };
  }
  if (/^voice\/development\/sessions\//.test(path)) {
    if (Object.keys(data).length) throw new ContractError();
    return {};
  }
  if (path === "voice/sessions") {
    if (Object.keys(data).some(key => !["language", "idempotency_key"].includes(key)) ||
        !["en", "hi", "hinglish"].includes(String(data.language))) throw new ContractError();
    return { language: data.language, idempotency_key: identifier(data.idempotency_key) };
  }
  if (/\/turn$/.test(path)) {
    if (Object.keys(data).length !== 1 || !["copay", "estimate", "agent_claim", "human_review"].includes(String(data.prompt))) throw new ContractError();
    return { prompt: data.prompt };
  }
  if (/\/end$/.test(path)) {
    if (Object.keys(data).some(key => key !== "idempotency_key")) throw new ContractError();
    return data.idempotency_key === undefined ? {} : { idempotency_key: identifier(data.idempotency_key) };
  }
  if (/\/decisions$/.test(path)) return decisionRequest(data);
  if (/\/(report-release|recover-turn)$/.test(path)) {
    const allowed = path.endsWith("report-release") ? ["turn_id", "report_digest", "request_key"] : ["turn_id", "request_key"];
    if (Object.keys(data).some(key => !allowed.includes(key))) throw new ContractError();
    return { turn_id: identifier(data.turn_id), request_key: identifier(data.request_key),
      ...(path.endsWith("report-release") ? { report_digest: digest(data.report_digest) } : {}) };
  }
  if (Object.keys(data).length) throw new ContractError();
  return {};
}

async function limitedText(input: Request | Response, limit: number) {
  const reader = input.body?.getReader();
  if (!reader) return "";
  const parts: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) { await reader.cancel(); throw new RangeError("Body exceeds limit"); }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(parts).toString("utf8");
}

async function handle(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!routes.some(([method, pattern]) => method === request.method && pattern.test(path))) {
    return empty(404);
  }
  try {
    const writes = request.method !== "GET";
    if (writes && (!sameOrigin(request) ||
        request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json")) {
      return empty(403);
    }
    let body: string | undefined;
    try { body = writes ? await limitedText(request, 65_536) : undefined; }
    catch { return empty(413); }
    if (writes) {
      try { body = JSON.stringify(/\/human-review$/.test(path) ? humanReviewJSONCommand(body ?? "") : /\/case-binding$/.test(path) ? bindCaseJSONCommand(body ?? "") : command(path, JSON.parse(body ?? ""))); }
      catch { return NextResponse.json({ detail: "Check the entered details." }, { status: 422, headers: { "Cache-Control": "no-store" } }); }
    }
    const base = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password ||
        base.pathname !== "/" || base.search || base.hash) throw new Error("Backend unavailable");
    if (process.env.NODE_ENV === "production" && base.protocol !== "https:" &&
        !(base.hostname === "api" && process.env.BACKEND_PRIVATE_NETWORK === "1")) {
      throw new Error("Backend unavailable");
    }
    const token = await accessToken();
    const gatewayKey = process.env.BACKEND_GATEWAY_TOKEN ?? "";
    if (process.env.NODE_ENV === "production" && gatewayKey.length < 32) {
      throw new Error("Backend unavailable");
    }
    if (!token) return NextResponse.json(
      { detail: "Sign in to access this case." }, { status: 401, headers: { "Cache-Control": "no-store" } });
    let upstreamPath = path;
    if (path === "consent" || path === "profile-memory") {
      const identity = await fetch(new URL("/v1/me", base), {
        cache: "no-store", redirect: "error", signal: AbortSignal.any([request.signal, AbortSignal.timeout(10_000)]),
        headers: { Authorization: `Bearer ${token}`, ...(gatewayKey ? { "X-Assurely-Gateway-Key": gatewayKey } : {}) },
      });
      if (!identity.ok) { await identity.body?.cancel(); return empty([401, 403].includes(identity.status) ? identity.status : 503); }
      const owner = identifier(object(JSON.parse(await limitedText(identity, 16_384))).user_id);
      if (path === "consent") body = JSON.stringify({ ...JSON.parse(body!), user_id: owner });
      else { upstreamPath = `profile-memory/${owner}`; body = undefined; }
    }
    const upstream = await fetch(new URL(`/v1/${upstreamPath}`, base), {
      method: request.method, body, cache: "no-store", redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(120_000)]), headers: {
        "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(gatewayKey ? { "X-Assurely-Gateway-Key": gatewayKey } : {}),
      },
    });
    if (!upstream.ok) {
      await upstream.body?.cancel();
      const retry = Number(upstream.headers.get("retry-after"));
      return NextResponse.json({ detail: "The request could not be completed." }, { status: upstream.status, headers: {
        "Cache-Control": "no-store", ...(upstream.status === 429 && upstream.headers.has("retry-after") && Number.isFinite(retry) && retry >= 0 ? { "Retry-After": String(Math.min(Math.ceil(retry), 3600)) } : {}),
      } });
    }
    const data = await limitedText(upstream, 2_000_000);
    if (upstream.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") throw new Error("Invalid service response");
    try { object(JSON.parse(data)); } catch { throw new Error("Invalid service response"); }
    return new Response(data, { status: upstream.status, headers: {
      "Content-Type": "application/json", "Cache-Control": "no-store",
    } });
  } catch {
    return NextResponse.json({ detail: "The service is unavailable. Please refresh the case status before retrying." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

export { handle as GET, handle as POST, handle as DELETE };
