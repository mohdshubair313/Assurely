"use client";

import { useState } from "react";
import { Button } from "@/components/createui/button";
import { getHumanReview, requestHumanReview, type HumanReviewRequest } from "@/lib/api-client";
import { reviewAttempt, confirmReviewAttempt } from "@/lib/human-review-attempt";
import type { CaseTask } from "@/hooks/use-case-task";
import styles from "@/app/(product)/workspace/workspace.module.css";

const labels: Record<HumanReviewRequest["status"], string> = {
  pending: "Saved; waiting for assignment",
  assigned: "Assigned for human review",
  in_review: "Human review in progress",
  decision_recorded: "A human decision was recorded; fresh release checks still apply",
};

export default function HumanReviewPanel({ session, account, busy, run, beforeRequest }: {
  session: string; account: string; busy: boolean;
  run: (action: (task: CaseTask) => Promise<void>) => Promise<void>;
  beforeRequest: () => void;
}) {
  const [view, setView] = useState<{ request: HumanReviewRequest | null } | null>(null);
  return <section className={styles.panel} aria-label="Human review request">
    <h2>Ask for human review</h2>
    <p>This saves a request for your case. It does not connect a human or confirm a notification. Voice minutes, payment and microphone access are not required.</p>
    <p>A new request requires a fresh human decision before a prepared report can be released. The AI cannot provide that approval.</p>
    <div className="flex flex-wrap gap-3">
      <Button variant="primary" appearance="outline" size="md" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
        // Clear any previously displayed report even if this write's result is uncertain.
        beforeRequest();
        setView(null);
        const key = reviewAttempt(account, session, sessionStorage);
        const request = await requestHumanReview(session, key, { signal });
        commit(() => {
          setView({ request });
          try { confirmReviewAttempt(account, session, sessionStorage); } catch { /* Retaining a confirmed key is safe. */ }
        });
      })}>{view?.request ? "Request a fresh human review" : "Save human review request"}</Button>
      <Button variant="neutral-light" appearance="ghost" size="md" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
        beforeRequest(); setView(null);
        const request = await getHumanReview(session, { signal });
        commit(() => setView({ request }));
      })}>Refresh review request</Button>
    </div>
    {view && <div className="mt-4 text-body" role="status" aria-live="polite">
      {view.request ? <>
        <p>{labels[view.request.status]}</p>
        <p>Saved at <time dateTime={view.request.requested_at}>{view.request.requested_at}</time>.</p>
        <p>Human connection: not established. Notification: not dispatched. This status does not release a report.</p>
      </> : <p>No customer review request is recorded for this case.</p>}
    </div>}
  </section>;
}
