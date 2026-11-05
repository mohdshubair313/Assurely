"use client";
import Link from "next/link";
import { useRef, useState, useSyncExternalStore } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Input } from "@/components/createui/input";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import { reportStatus, releaseReport, type Report, type ReportStatus } from "@/lib/api-client";
import { UUID } from "@/lib/api-contracts";
import { useCaseTask } from "@/hooks/use-case-task";
import EvidenceSources from "./EvidenceSources";
import styles from "@/app/(product)/workspace/workspace.module.css";
const subscribe = (callback: () => void) => { window.addEventListener("hashchange", callback); return () => window.removeEventListener("hashchange", callback); };
export default function CaseReportView({ mode }: { mode: "comparison" | "handoff" }) {
  const session = useSyncExternalStore(subscribe, () => window.location.hash.slice(1), () => "");
  const [view, setView] = useState<{ session: string; status: ReportStatus; report: Report | null } | null>(null);
  const current = view?.session === session ? view : null;
  const { run, busy, notice, notify } = useCaseTask(session);
  const keys = useRef(new Map<string, string>());
  function select(value: string) {
    const url = new URL(window.location.href); url.hash = value; window.history.replaceState(null, "", url);
    window.dispatchEvent(new HashChangeEvent("hashchange")); setView(null);
  }
  return <section className={styles.page}><header className={styles.header}><div>
    <p className={styles.eyebrow}>{mode === "comparison" ? "YOUR NEEDS, SIDE BY SIDE" : "CASE REVIEW STATUS"}</p>
    <h1>{mode === "comparison" ? "Keep the evidence close." : "Follow your case."}</h1>
    <p>{mode === "comparison" ? "Open only the reviewed report for your case. Each statement keeps its sources and verification dates." : "Check the current turn and report preparation. A prepared report does not confirm advisor contact or delivery."}</p>
  </div><Link href="/workspace">Your workspace</Link></header>
    <div className={styles.panel}><h2>Find your case</h2><form onSubmit={event => { event.preventDefault(); void run(async ({ signal, commit }) => {
      setView(null); const status = await reportStatus(session, { signal }); commit(() => setView({ session, status, report: null }));
    }); }}><label htmlFor="report-case">Case identifier</label><Input id="report-case" size="md" maxLength={36} required disabled={busy} value={session} onChange={event => select(event.target.value)} />
      <p>Use the same signed-in account that owns the case. <Link href="/sign-in">Account access</Link></p><Button type="submit" variant="primary" appearance="outline" size="md" disabled={busy || !UUID.test(session)} loading={busy}><ButtonLabel>Check current status</ButtonLabel></Button>
    </form></div>
    {current && <div className={styles.panel}><h2>Current case status</h2><p>Turn: {current.status.status}</p>
      <p>{current.report ? "This report was opened after fresh verification." : current.status.report_digest ? "A report has been prepared. Fresh verification and independent approval are required to open it." : "No report is available for this turn."}</p>
      {current.status.report_digest && <Button variant="primary" appearance="solid" size="md" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
        const status = current.status, reference = status.report_digest!, binding = `${session}:${status.turn_id}:${reference}`;
        setView({ ...current, report: null });
        if (!keys.current.has(binding)) keys.current.set(binding, crypto.randomUUID());
        const report = await releaseReport(session, status.turn_id, reference, keys.current.get(binding)!, { signal });
        commit(() => { setView({ session, status, report }); notify("Report released after fresh verification."); });
      })}><ButtonLabel>Check and open reviewed report</ButtonLabel></Button>}
      <p><Link href={`/workspace#${session}`}>Continue or recover this case</Link></p>
    </div>}
    {notice && <InlineAlert variant={notice.failed ? "danger" : "info"} appearance="soft" role={notice.failed ? "alert" : "status"}><InlineAlertContent><InlineAlertDescription className="line-clamp-none">{notice.text}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
    {current?.report && <article className={styles.panel} aria-label="Released report"><h2>Your reviewed report</h2>{current.report.sentences.map((sentence, index) => <div key={index} className={styles.claim}><p>{sentence.text}</p>{sentence.citations.map((citation, i) => <EvidenceSources key={i} citation={citation} />)}</div>)}</article>}
  </section>;
}
