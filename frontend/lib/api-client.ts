/**
 * API client stub — typed interfaces for backend integration.
 *
 * All methods currently return mock/placeholder data.
 * Interfaces match the backend API surface:
 *   POST /v1/message   → postMessage
 *   POST /v1/consent   → postConsent
 *   GET  /v1/session/id → getSession
 *
 * See docs/insurance-platform-tech-stack-hld-lld.md for full API spec.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ── Types ─────────────────────────────────────────────────── */

export interface ComparisonFact {
  category: string;
  plain_language: string;
  exact_term?: string;
  source?: {
    document: string;
    version?: string;
    section?: string;
    page?: number;
  };
  verification_status: "verified" | "unverified" | "conflicting" | "not_found";
  importance: "high" | "medium" | "low";
  last_verified: string;
}

export interface RecommendationReport {
  report_id: string;
  assumptions: string[];
  recommendations: string[];
  tradeoffs: string[];
  facts: ComparisonFact[];
  guardrail_status: "approved" | "escalation_required" | "delivery_hold";
  next_actions: Array<"save" | "edit" | "ask_expert" | "compare_more">;
}

export interface ConsentChoice {
  process_data: boolean;
  save_profile: boolean;
  receive_updates: boolean;
}

export interface SessionSummary {
  session_id: string;
  status: "intake" | "comparing" | "report_ready" | "escalated";
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  content: string;
  intent?: string;
  missing_fields?: string[];
  suggestions?: string[];
}

/* ── Client ────────────────────────────────────────────────── */

/** POST /v1/message — send a user message to the advisory graph. */
export async function postMessage(
  sessionId: string,
  content: string
): Promise<MessageResponse> {
  // Stub — will call `${API_BASE}/v1/message` when backend is ready
  void sessionId;
  void content;
  return {
    content: "This is a placeholder response. Backend not connected.",
    suggestions: [
      "Tell me about your family",
      "What matters most to you in a health plan?",
    ],
  };
}

/** POST /v1/consent — record user consent choices. */
export async function postConsent(
  userId: string,
  choices: ConsentChoice
): Promise<{ consent_id: string; recorded_at: string }> {
  void userId;
  void choices;
  return {
    consent_id: "consent-placeholder",
    recorded_at: new Date().toISOString(),
  };
}

/** GET /v1/session/:id — retrieve session state. */
export async function getSession(
  sessionId: string
): Promise<SessionSummary> {
  void sessionId;
  return {
    session_id: sessionId,
    status: "intake",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

export { API_BASE };
