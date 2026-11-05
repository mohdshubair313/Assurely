"use client";
import Link from "next/link";
import { useRef, useState, useSyncExternalStore } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Input } from "@/components/createui/input";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import { postMessage, reportStatus, readSession, releaseReport, recoverTurn, type Report, type ReportStatus } from "@/lib/api-client";
import { scenario, UUID } from "@/lib/api-contracts";
import { useCaseTask } from "@/hooks/use-case-task";
import PrivacyControls from "@/components/product/PrivacyControls";
import styles from "./workspace.module.css";
import EvidenceSources from "@/components/product/EvidenceSources";
import SignOutControl from "@/components/auth/SignOutControl";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export default function Workspace() {
  const restored = useSyncExternalStore(subscribeHash, () => window.location.hash.slice(1), () => "");
  const session = restored;
  function setSession(value: string) {
    const url = new URL(window.location.href); url.hash = value;
    window.history.replaceState(null, "", url); window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
  const [question, setQuestion] = useState("");
  const [policy, setPolicy] = useState("");
  const [capability, setCapability] = useState("coverage_options");
  const [age, setAge] = useState("");
  const [date, setDate] = useState("");
  const [transaction, setTransaction] = useState("issue");
  const [basis, setBasis] = useState("individual");
  const [options, setOptions] = useState("");
  const [residency, setResidency] = useState("");
  const [zone, setZone] = useState("");
  const [portability, setPortability] = useState("");
  const [continuity, setContinuity] = useState("");
  type View = { session: string; reply: string; status: ReportStatus | null; report: Report | null; missing: string[]; notification: string };
  const [view, setView] = useState<View | null>(null);
  const current = view?.session === session ? view : null;
  const reply = current?.reply ?? "", status = current?.status ?? null, report = current?.report ?? null;
  function patchCase(value: Partial<View>) {
    setView(previous => ({ session, reply: "", status: null, report: null, missing: [], notification: "",
      ...(previous?.session === session ? previous : {}), ...value }));
  }
  const { run, busy, notice, notify: setMessage } = useCaseTask(session);
  const message = notice?.text ?? "", failed = notice?.failed ?? false;
  const requests = useRef(new Map<string, string>());
  const policyDetails = useRef<HTMLDetailsElement>(null);
  const valid = UUID;
  function key(binding: string) {
    if (!requests.current.has(binding)) requests.current.set(binding, crypto.randomUUID());
    return requests.current.get(binding)!;
  }
  return <section className={styles.page}>
    <header className={styles.header}><div><p className={styles.eyebrow}>YOUR COVER, UNDERSTOOD</p>
      <h1>Your health-cover case.</h1><p>Ask a question, follow the review, and read the evidence when your report is released.</p></div>
      <div className={styles.actions}><Link href="/sign-in">Account access</Link><SignOutControl /></div></header>
    <div className={styles.grid}><div className={styles.panel}><h2>Start with your question</h2>
      <p>Messages are sent to the advisory service. Share only the health-cover details needed for your case.</p>
      <form onSubmit={event => { event.preventDefault(); void run(async ({ signal, commit }) => {
        const references = policy.split(",").map(value => value.trim()).filter(Boolean);
        if (policy.trim() && (!references.length || !date)) throw new Error("Enter the policy references and applicable date supplied for your case.");
        const selected = references.length ? scenario({ items: references.map(publication_digest => ({ publication_digest,
          capabilities: [capability],
          context: { transaction, transaction_date: date, cover_basis: basis,
            selected_options: options.split("\n").map(v => v.trim()).filter(Boolean),
            entry_age_years: age ? Number(age) : null, residency: residency || null,
            zone: zone || null, portability: portability ? portability === "yes" : null,
            continuity: continuity ? continuity === "yes" : null },
        })) }) : undefined;
        patchCase({ report: null, status: null, reply: "" });
        const response = await postMessage(session, question.trim(), selected, { signal });
        commit(() => {
        patchCase({ reply: response.reply, missing: response.missing_fields, notification: response.notification_status, report: response.output }); setQuestion("");
        if (policyDetails.current) policyDetails.current.open = false;
        setMessage(response.delivery_hold ? "Your case is held for review. No report has been released." : "Your response is available.");
        });
      }); }}>
        <label htmlFor="question">Your question</label><Input id="question" size="md" required
          disabled={busy} maxLength={4000} value={question} onChange={event => setQuestion(event.target.value)} />
        <details ref={policyDetails}><summary>Review a specific policy</summary><p>Use the policy reference supplied by your advisor. Missing or unmatched details stay under review.</p>
          <label htmlFor="policy">Advisor-supplied policy references, separated by commas</label><Input id="policy" size="md" maxLength={350} disabled={busy} value={policy} onChange={e => setPolicy(e.target.value)} />
          <p>Check up to five policies against the same scenario. Each policy keeps its own evidence and conditions.</p>
          <label htmlFor="policy-field">What would you like to check?</label><select id="policy-field" disabled={busy} value={capability} onChange={e => setCapability(e.target.value)}><option value="coverage_options">Cover amount options</option><option value="adult_entry_ages">Adult entry-age terms</option><option value="base_ped_wait">Base pre-existing-condition waiting period</option></select>
          <label htmlFor="policy-age">Entry age in completed years</label><Input id="policy-age" type="number" size="md" min={0} max={150} disabled={busy} value={age} onChange={e => setAge(e.target.value)} />
          <label htmlFor="policy-date">Applicable issue or renewal date</label><Input id="policy-date" type="date" size="md" disabled={busy} value={date} onChange={e => setDate(e.target.value)} />
          <label htmlFor="transaction">Policy transaction</label><select id="transaction" disabled={busy} value={transaction} onChange={e => setTransaction(e.target.value)}><option value="issue">New issue</option><option value="renewal">Renewal</option></select>
          <label htmlFor="cover-basis">Cover arrangement</label><select id="cover-basis" disabled={busy} value={basis} onChange={e => setBasis(e.target.value)}><option value="individual">Individual</option><option value="family_floater">Family floater</option></select>
          <label htmlFor="policy-options">Selected options, one per line</label><textarea id="policy-options" rows={3} maxLength={2000} disabled={busy} value={options} onChange={e => setOptions(e.target.value)} />
          <label htmlFor="policy-zone">Zone stated in the policy schedule</label><Input id="policy-zone" size="md" maxLength={100} disabled={busy} value={zone} onChange={e => setZone(e.target.value)} />
          <label htmlFor="policy-residency">Residency classification stated in the policy</label><Input id="policy-residency" size="md" maxLength={100} disabled={busy} value={residency} onChange={e => setResidency(e.target.value)} />
          <label htmlFor="policy-portability">Is this a portability case?</label><select id="policy-portability" value={portability} disabled={busy} onChange={e => setPortability(e.target.value)}><option value="">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select>
          <label htmlFor="policy-continuity">Is continuity credit confirmed?</label><select id="policy-continuity" value={continuity} disabled={busy} onChange={e => setContinuity(e.target.value)}><option value="">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select>
        </details>
        <Button type="submit" variant="primary" appearance="solid" size="lg" loading={busy}
          disabled={busy || !valid.test(session) || !question.trim()}><ButtonLabel>Send question</ButtonLabel></Button>
      </form>{reply && <p className={styles.reply} aria-live="polite">{reply}</p>}
      {Boolean(current?.missing.length) && <p role="status">More profile details are needed. Answer the service&apos;s follow-up question to continue.</p>}
      {current?.notification === "queued" && <p>The review notification was acknowledged by the configured receiver. This is not report approval.</p>}
      {["failed", "unconfigured"].includes(current?.notification ?? "") && <p>The review notification could not be confirmed. Your report stays held; no advisor contact is promised.</p>}
    </div><aside className={styles.panel}><h2>Your case</h2>
      <label htmlFor="case-id">Case identifier</label><Input id="case-id" size="md" placeholder="Choose New case or enter your saved identifier" disabled={busy} value={session}
        maxLength={36} onChange={event => { setSession(event.target.value); setView(null); }} />
      <p>Keep this identifier to return to your case. Private case access requires the same signed-in account.</p>
      <div className={styles.actions}><Button variant="primary" appearance="outline" size="md" disabled={busy || !valid.test(session)}
        onClick={() => void run(async ({ signal, commit }) => { patchCase({ report: null }); const result = await reportStatus(session, { signal }); commit(() => patchCase({ status: result })); })}>
        <ButtonLabel>Refresh case status</ButtonLabel></Button>
        <Button variant="neutral-light" appearance="outline" size="md" disabled={busy || !valid.test(session)} onClick={() => void run(async ({ signal, commit }) => {
          patchCase({ report: null }); const result = await readSession(session, { signal }); commit(() => setMessage(`Case activity: ${result.status}. Report access is checked separately.`));
        })}><ButtonLabel>Check case activity</ButtonLabel></Button>
        <Button variant="neutral-light" appearance="ghost" size="md" disabled={busy} onClick={() => {
          const id = crypto.randomUUID(); setSession(id); setView(null); setPolicy(""); setAge(""); setDate(""); setOptions(""); setQuestion("");
          setResidency(""); setZone(""); setPortability(""); setContinuity("");
        }}><ButtonLabel>New case</ButtonLabel></Button></div>
      {status && <div className={styles.status}><p><strong>Turn status:</strong> {status.status}</p>
        <p>{report ? "Your report is open after fresh verification." : status.report_digest ? "Report prepared. Independent review is required before release." : "No report is available for release."}</p>
        {status.report_digest && <Button variant="primary" appearance="solid" size="md" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
          patchCase({ report: null });
          const result = await releaseReport(session, status.turn_id, status.report_digest!, key(`release:${session}:${status.turn_id}:${status.report_digest}`), { signal });
          commit(() => { patchCase({ report: result, reply: "" }); setMessage("Report released after fresh verification."); });
        })}><ButtonLabel>Check and open reviewed report</ButtonLabel></Button>}
        {status.status === "running" && <details><summary>Interrupted case?</summary><p>Close an interrupted turn to send a new question. A live turn cannot be closed here.</p>
          <Button variant="neutral-light" appearance="outline" size="md" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
            patchCase({ report: null });
            await recoverTurn(session, status.turn_id, key(`recover:${session}:${status.turn_id}`), { signal });
            const result = await reportStatus(session, { signal });
            commit(() => { patchCase({ status: result }); setMessage("Interrupted turn closed. You can send a new question."); });
          })}><ButtonLabel>Close interrupted turn</ButtonLabel></Button></details>}
      </div>}<div className={styles.actions}><Link href={`/comparison#${session}`}>Open report view</Link><Link href={`/handoff#${session}`}>Review status</Link><Link href="/advisor">Advisor workspace ↗</Link></div>
      <PrivacyControls />
    </aside></div>
    {message && <InlineAlert variant={failed ? "danger" : "info"} appearance="soft" layout="horizontal" role={failed ? "alert" : "status"}>
      <InlineAlertContent><InlineAlertDescription className="line-clamp-none">{message}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
    {report && <article className={styles.panel} aria-label="Released report"><h2>Your reviewed report</h2>
      {report.sentences?.map((sentence, index) => <div key={index} className={styles.claim}><p>{sentence.text}</p>
        {sentence.citations.map((citation, i) => <EvidenceSources key={i} citation={citation} />)}
      </div>)}
    </article>}
  </section>;
}
