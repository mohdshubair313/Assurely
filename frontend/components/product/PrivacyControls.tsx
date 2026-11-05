"use client";
import { useState } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import { deleteProfileMemory, updateConsent, getConsents, type ConsentScope } from "@/lib/api-client";
import { useCaseTask } from "@/hooks/use-case-task";
const choices: { scope: ConsentScope; label: string }[] = [
  { scope: "process_comparison", label: "Process health-cover comparisons" },
  { scope: "save_profile", label: "Remember your profile for returning visits" },
  { scope: "receive_updates", label: "Receive updates" },
];
export default function PrivacyControls() {
  const { run, busy, notice, notify } = useCaseTask("privacy");
  const [confirm, setConfirm] = useState(false);
  const [current, setCurrent] = useState<Awaited<ReturnType<typeof getConsents>> | null>(null);
  return <details><summary>Privacy and consent</summary>
    <p>Consent purposes, version 2026-11-04. Process the health and family details you submit for a health-cover comparison. Saving your profile permits future signed-in reuse until withdrawal. Updates use your account only when a delivery channel is configured. Audio, transcripts and voice vendors are not included. Withdrawal stops future use; existing case reports and audit records are retained.</p>
    <Button type="button" size="sm" variant="neutral-light" appearance="outline" disabled={busy}
      onClick={() => void run(async ({ signal, commit }) => { const result = await getConsents({ signal }); commit(() => setCurrent(result)); })}><ButtonLabel>Load current choices</ButtonLabel></Button>
    {choices.map(({ scope, label }) => <div key={scope}><p>{label} — {current ? (current.find(row => row.scope === scope)?.granted ? "Allowed" : "Not allowed") : "Not loaded"}</p><div className="flex flex-wrap gap-component-sm">
      {(["grant", "revoke"] as const).map(action => <Button key={action} type="button" size="sm" variant="neutral-light" appearance="outline" disabled={busy}
        onClick={() => void run(async ({ signal, commit }) => { const result = await updateConsent(scope, action, { signal });
          commit(() => { setCurrent(null); notify(`${label}: ${result.status}. Receipt recorded at ${result.timestamp}.`); }); })}><ButtonLabel>{action === "grant" ? "Allow" : "Withdraw"}</ButtonLabel></Button>)}
    </div></div>)}
    {!confirm ? <Button type="button" size="sm" variant="danger" appearance="outline" disabled={busy} onClick={() => setConfirm(true)}><ButtonLabel>Delete saved profile</ButtonLabel></Button> : <div>
      <p>Delete the saved profile for your account? To also stop future saving, withdraw profile-memory consent above.</p>
      <Button type="button" size="sm" variant="danger" appearance="solid" disabled={busy} onClick={() => void run(async ({ signal, commit }) => {
        const result = await deleteProfileMemory({ signal }); commit(() => { setConfirm(false); notify(result.deleted ? "Saved profile deleted." : "No saved profile was present."); });
      })}><ButtonLabel>Confirm profile deletion</ButtonLabel></Button>
      <Button type="button" size="sm" variant="neutral-light" appearance="ghost" disabled={busy} onClick={() => setConfirm(false)}><ButtonLabel>Cancel</ButtonLabel></Button>
    </div>}
    {notice && <InlineAlert variant={notice.failed ? "danger" : "info"} appearance="soft" role={notice.failed ? "alert" : "status"}><InlineAlertContent><InlineAlertDescription className="line-clamp-none">{notice.text}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
  </details>;
}
