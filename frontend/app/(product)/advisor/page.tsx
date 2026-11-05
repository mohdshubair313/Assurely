"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Input } from "@/components/createui/input";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import { readReview, snapshotReview, decideReview, type Review } from "@/lib/api-client";
import { UUID, DIGEST, decisionRequest } from "@/lib/api-contracts";
import { useCaseTask } from "@/hooks/use-case-task";
import styles from "../workspace/workspace.module.css";
import EvidenceSources from "@/components/product/EvidenceSources";

export default function Advisor() {
  const [session, setSession] = useState("");
  const [digest, setDigest] = useState("");
  const [review, setReview] = useState<Review | null>(null);
  const [reason, setReason] = useState("");
  const [expiry, setExpiry] = useState("");
  const { run, busy, notice, notify } = useCaseTask(`${session}/${digest}`);
  const error = notice?.text ?? "";
  const requests = useRef(new Map<string, string>());
  async function decide(action: "approve" | "revoke", signal: AbortSignal, commit: (update: () => void) => void) {
    if (!review) return;
    if (action === "approve" && !Number.isFinite(Date.parse(expiry))) throw new Error("Choose a valid future approval expiry.");
    const expires = action === "approve" ? new Date(expiry).toISOString() : null;
    const binding = JSON.stringify([review.report_digest, review.revision, action, reason, expires]);
    if (!requests.current.has(binding)) requests.current.set(binding, crypto.randomUUID());
    const reference = review.report_digest;
    const command = decisionRequest({
      action, reason, expires_at: expires, expected_revision: review.revision,
      request_key: requests.current.get(binding),
    });
    setReview(null);
    await decideReview(reference, command, { signal });
    const result = await readReview(reference, { signal });
    commit(() => { setReview(result); notify("Decision recorded. Customer release still requires fresh verification."); });
  }
  return <section className={styles.page}><header className={styles.header}><div>
    <p className={styles.eyebrow}>INDEPENDENT REVIEW</p><h1>Advisor workspace.</h1>
    <p>Review the exact report and scenario before recording a decision. Access requires an authorized advisor account.</p>
    </div><Link href="/sign-in">Sign in</Link></header>
    <div className={styles.grid}><div className={styles.panel}><h2>Find the report</h2>
      <label htmlFor="advisor-case">Case identifier</label><Input id="advisor-case" size="md" disabled={busy} value={session} onChange={e => { setSession(e.target.value); setReview(null); }} />
      <Button variant="primary" appearance="outline" size="md" disabled={busy || !UUID.test(session)} onClick={() => void run(async ({ signal, commit }) => {
        setReview(null);
        const snapshot = await snapshotReview(session, { signal });
        const result = await readReview(snapshot.report_digest, { signal });
        commit(() => { setDigest(result.report_digest); setReview(result); });
      })}><ButtonLabel>Load current case report</ButtonLabel></Button>
      <label htmlFor="advisor-digest">Or exact report reference</label><Input id="advisor-digest" size="md" disabled={busy} value={digest} onChange={e => { setDigest(e.target.value); setReview(null); }} />
      <Button variant="neutral-light" appearance="outline" size="md" disabled={busy || !DIGEST.test(digest)} onClick={() => void run(async ({ signal, commit }) => { setReview(null); const result = await readReview(digest, { signal }); commit(() => setReview(result)); })}><ButtonLabel>Read report</ButtonLabel></Button>
    </div><div className={styles.panel}><h2>Record your decision</h2>
      <p>{review ? `Review status: ${review.review_status} · Revision ${review.revision}` : "Load a report before making a decision."}</p>
      <label htmlFor="review-reason">Review reason</label><Input id="review-reason" size="md" maxLength={2000} disabled={busy} value={reason} onChange={e => setReason(e.target.value)} />
      <label htmlFor="review-expiry">Approval expires at</label><Input id="review-expiry" type="datetime-local" size="md" disabled={busy} value={expiry} onChange={e => setExpiry(e.target.value)} />
      <p>Approval applies only to this report. The owner must request release, and evidence is checked again.</p>
      <p>Choose a future expiry within seven days. Policy-source expiry may shorten this window further.</p>
      <div className={styles.actions}><Button variant="primary" appearance="solid" size="md" disabled={busy || !review || !reason.trim() || !expiry} onClick={() => void run(({ signal, commit }) => decide("approve", signal, commit))}><ButtonLabel>Approve reviewed report</ButtonLabel></Button>
        <Button variant="danger" appearance="outline" size="md" disabled={busy || !review || !reason.trim()} onClick={() => void run(({ signal, commit }) => decide("revoke", signal, commit))}><ButtonLabel>Revoke approval</ButtonLabel></Button></div>
    </div></div>
    {error && <InlineAlert variant={notice?.failed ? "danger" : "info"} appearance="soft" layout="horizontal" role={notice?.failed ? "alert" : "status"}><InlineAlertContent><InlineAlertDescription className="line-clamp-none">{error}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
    {review && <article className={styles.panel}><h2>Exact report under review</h2>
      {review.report.sentences?.map((sentence, index) => <div key={index} className={styles.claim}><p>{sentence.text}</p>{sentence.citations.map((c, i) => <EvidenceSources key={i} citation={c} />)}</div>)}
      <details><summary>Bound policy scenario</summary><pre className={styles.reply}>{JSON.stringify(review.scenario, null, 2)}</pre></details>
    </article>}
  </section>;
}
