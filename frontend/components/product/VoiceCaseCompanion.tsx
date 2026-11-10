"use client";

import { useEffect, useId, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { Button } from "@/components/createui/button";
import { Input } from "@/components/createui/input";
import { UUID } from "@/lib/api-contracts";
import { useCaseTask } from "@/hooks/use-case-task";
import { bindVoiceCase, readCaseBinding, readReviewedCaptions } from "@/lib/voice/case-api";
import { caseBindingAttempt } from "@/lib/voice/binding-attempt";
import { CaptionDisplayController } from "@/lib/voice/caption-display";
import { attachCaptionLifecycle } from "@/lib/voice/caption-lifecycle";
import type { VoiceCaseBinding } from "@/lib/voice/case-contracts";
import EvidenceSources from "./EvidenceSources";

function ReviewedText({ binding }: { binding: VoiceCaseBinding }) {
  const display = useMemo(() => new CaptionDisplayController(binding, { read: readReviewedCaptions }), [binding]);
  const snapshot = useSyncExternalStore(display.subscribe, display.getSnapshot, display.getSnapshot);
  useEffect(() => attachCaptionLifecycle(display, {
    documentEvents: document, windowEvents: window,
    visible: () => document.visibilityState === "visible",
    focused: () => document.hasFocus(), online: () => navigator.onLine,
  }), [display]);
  return <div className="mt-4">
    <p role="status" aria-live="polite" className="text-body">{snapshot.message}</p>
    {snapshot.packet && <article aria-label="Freshly authorized reviewed report text" className="mt-4 space-y-4">
      {snapshot.packet.sentences.map(sentence => <div key={sentence.id} className="rounded-xl border border-light p-4">
        <p className="text-body">{sentence.text}</p>
        {sentence.citations.map(citation => <EvidenceSources key={citation.id} citation={citation} />)}
      </div>)}
    </article>}
  </div>;
}

export default function VoiceCaseCompanion({ voice, account, enabled }: { voice: string; account: string; enabled: boolean }) {
  const inputId = useId();
  const [caseId, setCaseId] = useState("");
  const [binding, setBinding] = useState<VoiceCaseBinding | null>(null);
  const [show, setShow] = useState(false);
  const { run, busy, notice } = useCaseTask(`${account}:${voice}:${enabled}`);
  return <section className="mt-8 rounded-xl border border-light p-5" aria-label="Reviewed case companion">
    <h2 className="text-heading-sm text-strongest">Reviewed case companion</h2>
    <p className="mt-2 text-body">Read the complete reviewed sentences and their source documents. This panel is not a live transcript. A separately enabled report-reading bridge can share this report with Vaani only with your report-speech permission and fresh server checks.</p>
    <p className="mt-2 text-body">One report version is fixed to this voice session. A changed report or human decision requires a new voice session. <Link href="/workspace">Continue your case in the workspace</Link>.</p>
    <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); if (!enabled || busy || binding) return; setShow(false); void run(async ({ signal, commit }) => {
      const command = caseBindingAttempt(account, voice, caseId, sessionStorage);
      const selected = await bindVoiceCase(voice, command.case_id, command.idempotency_key, signal);
      commit(() => { setBinding(selected); setShow(true); });
    }); }}>
      <label htmlFor={inputId} className="text-body">Existing case identifier — fictional staging cases only</label>
      <Input id={inputId} size="md" maxLength={36} required value={caseId} disabled={!enabled || busy || Boolean(binding)} onChange={event => { setShow(false); setCaseId(event.target.value); }} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" appearance="outline" size="md" disabled={!enabled || busy || !UUID.test(caseId) || Boolean(binding)} loading={busy}>Bind reviewed case</Button>
        <Button type="button" variant="neutral-light" appearance="ghost" size="md" disabled={!enabled || busy} onClick={() => { setShow(false); void run(async ({ signal, commit }) => {
          const selected = await readCaseBinding(voice, signal);
          commit(() => { setCaseId(selected.case_id); setBinding(selected); setShow(true); });
        }); }}>Recover and recheck bound case</Button>
        <Button type="button" variant="neutral-light" appearance="ghost" size="md" disabled={!show} onClick={() => setShow(false)}>Hide reviewed text</Button>
      </div>
    </form>
    {!enabled && <p className="mt-3 text-body">Reviewed text is hidden until this session and current consent are authorized.</p>}
    {notice && <p role={notice.failed ? "alert" : "status"} className="mt-3 text-body">{notice.text}</p>}
    {enabled && show && binding && <ReviewedText key={binding.binding_id} binding={binding} />}
  </section>;
}
