"use client";

import { useState } from "react";
import { Button } from "@/components/createui/button";
import { getConsents, updateConsent } from "@/lib/api-client";
import { useCaseTask } from "@/hooks/use-case-task";

export default function ReportSpeechConsent({ account, active, disabled, onStop }: {
  account: string; active: boolean; disabled: boolean; onStop: () => Promise<void>;
}) {
  const [current, setCurrent] = useState<{ available: boolean; granted: boolean } | null>(null);
  const { run, busy, notice, notify } = useCaseTask(account);
  return <section aria-label="Reviewed report speech permission" className="mt-6 rounded-xl border border-light p-5">
    <h2 className="text-heading-sm text-strongest">Reviewed report speech permission</h2>
    <p className="mt-2 text-body">Separate from microphone access: allow the report-reading bridge to share independently reviewed, currently released, bound reports with Vaani for speech. This account-level permission applies to future development sessions until you withdraw it. Use fictional staging cases only. This permission does not start a call.</p>
    <p className="mt-2 text-body">When the bridge is available, say “Read my reviewed report.” Other questions use the case workspace. Withdrawal blocks future report sends and requests call termination; previously sent audio cannot be recalled here.</p>
    <p className="mt-2 text-body" role="status">{current ? current.available ? current.granted ? "Report sharing allowed." : "Report sharing not allowed." : "Report sharing is unavailable in this backend." : "Report-sharing permission has not been loaded."}</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <Button variant="neutral-light" appearance="ghost" size="md" disabled={disabled || busy} onClick={() => void run(async ({ signal, commit }) => {
        setCurrent(null); const choices = await getConsents({ signal });
        const selected = choices.find(row => row.scope === "voice_report_speech");
        commit(() => setCurrent({ available: Boolean(selected), granted: selected?.granted === true }));
      })}>Load report-sharing choice</Button>
      <Button variant="primary" appearance="outline" size="md" disabled={disabled || busy || !current?.available || current.granted} onClick={() => void run(async ({ signal, commit }) => {
        setCurrent(null); await updateConsent("voice_report_speech", "grant", { signal });
        commit(() => { setCurrent({ available: true, granted: true }); notify("Separate report-speech permission recorded. A report still requires current independent approval."); });
      })}>Allow report speech</Button>
      <Button variant="danger" appearance="outline" size="md" disabled={disabled || busy || current?.available === false} onClick={() => void run(async ({ signal, commit }) => {
        setCurrent(null);
        try {
          await updateConsent("voice_report_speech", "revoke", { signal });
          commit(() => { setCurrent({ available: true, granted: false }); notify("Report-sharing withdrawal recorded. Check the session status for confirmed termination."); });
        } finally { if (active && !signal.aborted) await onStop(); }
      })}>{active ? "Withdraw and request call end" : "Withdraw report speech"}</Button>
    </div>
    {notice && <p className="mt-3 text-body" role={notice.failed ? "alert" : "status"}>{notice.text}</p>}
  </section>;
}
