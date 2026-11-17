"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { getConsents, updateConsent } from "@/lib/api-client";
import { useCaseTask } from "@/hooks/use-case-task";
import { readActivityRecap } from "@/lib/voice/activity";
import { ActivityRecapController } from "@/lib/voice/activity-display";
import { attachCaptionLifecycle } from "@/lib/voice/caption-lifecycle";
import EvidenceSources from "./EvidenceSources";

const statuses = {
  response_sent: "Backend response sent; audio playback unverified",
  delivery_uncertain: "Send outcome uncertain",
  interrupted: "Unsent response interrupted", failed: "Response failed", pending: "Response pending",
};

export default function VoiceActivityRecap({ account, voice }: { account: string; voice: string }) {
  const [choice, setChoice] = useState<{ granted: boolean; description: string } | null>(null);
  const [show, setShow] = useState(false);
  const { run, busy, notice } = useCaseTask(`${account}:${voice}:activity`);
  const display = useMemo(() => new ActivityRecapController(voice, { read: readActivityRecap }), [voice]);
  const snapshot = useSyncExternalStore(display.subscribe, display.getSnapshot, display.getSnapshot);
  useEffect(() => {
    if (!show) { display.stop(); return; }
    return attachCaptionLifecycle(display, {
      documentEvents: document, windowEvents: window,
      visible: () => document.visibilityState === "visible", focused: () => document.hasFocus(), online: () => navigator.onLine,
    });
  }, [display, show]);
  function hide() { display.stop(); setShow(false); }
  return <section className="mt-6 rounded-xl border border-light p-5" aria-label="Voice session activity recap">
    <h2 className="text-heading-sm text-strongest">Session activity recap</h2>
    <p className="mt-2 text-body">Review server response activity and currently permitted report sources. Audio playback is unverified. Raw questions and a conversation transcript are not retained here.</p>
    <p className="mt-2 text-body">Recap access uses separate summary consent. Withdrawal deletes optional saved report excerpts; minimal response and usage audit records remain. Earlier exports cannot be recalled.</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <Button variant="neutral-light" appearance="ghost" size="md" disabled={busy} onClick={() => {
        hide(); setChoice(null); void run(async ({ signal, commit }) => {
          const rows = await getConsents({ signal }); const selected = rows.find(row => row.scope === "voice_summary");
          if (!selected) throw new Error("Summary permission is unavailable.");
          commit(() => setChoice({ granted: selected.granted, description: selected.description }));
        });
      }}><ButtonLabel>Load recap permission</ButtonLabel></Button>
      <Button variant="primary" appearance="outline" size="md" disabled={busy || !choice || choice.granted} onClick={() => {
        hide(); void run(async ({ signal, commit }) => {
          await updateConsent("voice_summary", "grant", { signal });
          commit(() => setChoice(previous => previous ? { ...previous, granted: true } : null));
        });
      }}><ButtonLabel>Allow recap access</ButtonLabel></Button>
      <Button variant="danger" appearance="outline" size="md" disabled={busy} onClick={() => {
        hide(); setChoice(null); void run(async ({ signal, commit }) => {
          await updateConsent("voice_summary", "revoke", { signal });
          commit(() => setChoice({ granted: false, description: "Summary permission withdrawn." }));
        });
      }}><ButtonLabel>Withdraw summary consent</ButtonLabel></Button>
      <Button variant="primary" appearance="solid" size="md" disabled={busy || !choice?.granted || show} onClick={() => setShow(true)}><ButtonLabel>Check session activity</ButtonLabel></Button>
      <Button variant="neutral-light" appearance="ghost" size="md" disabled={!show} onClick={hide}><ButtonLabel>Hide recap</ButtonLabel></Button>
    </div>
    {choice && <p className="mt-2 text-body">{choice.description}</p>}
    <p className="mt-3 text-body" role="status">{snapshot.message}</p>
    {notice && <p className="mt-2 text-body" role={notice.failed ? "alert" : "status"}>{notice.text}</p>}
    {snapshot.packet && <div className="mt-4 flex flex-col gap-4">
      {!snapshot.packet.events.length && <p className="text-body">No response activity was recorded for this session.</p>}
      <ol className="flex flex-col gap-3">{snapshot.packet.events.map(event => <li key={event.response_id} className="text-body">
        <span>{event.intent === "report_read" ? "Reviewed report request" : "Request outside supported voice commands"}: {statuses[event.status]}.</span>
      </li>)}</ol>
      {snapshot.packet.report_availability === "unavailable" && <p className="text-body">Report text is currently unavailable. Check the case workspace for its review status.</p>}
      {snapshot.packet.reviewed_report && <article aria-label="Currently authorized report references" className="flex flex-col gap-4">
        <h3 className="text-heading-sm text-strongest">Currently authorized report references</h3>
        {snapshot.packet.reviewed_report.sentences.map(sentence => <div key={sentence.id}><p className="text-body">{sentence.text}</p>{sentence.citations.map((citation, index) => <EvidenceSources key={`${citation.id}:${index}`} citation={citation} />)}</div>)}
      </article>}
    </div>}
  </section>;
}
