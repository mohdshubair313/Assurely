"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { VoiceMediaController, type VoiceConnection, type VoiceConsent } from "@/lib/voice/controller";

/** Staging preparation only: intentionally not mounted on VoiceDemo or any customer route.
 * Parent must obtain authenticated server-owned connection material and record actual audio consent.
 * Disconnect/revoke here stops local media only; parent still owns durable revocation/provider-stop workflow.
 */
export function VoiceAudioControls({ controller, connection, consent }: {
  controller: VoiceMediaController;
  connection: VoiceConnection | null;
  consent: VoiceConsent;
}) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const consented = consent.aiDisclosureAccepted && consent.microphone && consent.vendorProcessing;
  useEffect(() => { if (!consented) void controller.revokeConsent(); }, [controller, consented]);
  useEffect(() => () => { void controller.disconnect(); }, [controller]);
  const connecting = state.state === "connecting" || state.state === "reconnecting";
  const connected = state.state === "connected";
  return <section className="rounded-xl border border-line bg-surface p-6 text-body" aria-label="Synthetic development audio controls">
    <h2 className="text-lg font-semibold text-strongest">AI voice guide · synthetic development audio</h2>
    <p className="mt-2">This is an AI voice service, not a human advisor. Audio requires your explicit microphone and Vaani processing consent. Use fictional data only. It cannot approve reports or claims.</p>
    <p className="mt-2" role="status" aria-live="polite">{state.message}</p>
    <p className="mt-2 text-sm">Connection: {state.state} · Network: {state.quality} · Microphone: {state.microphone ? "enabled" : "muted"}</p>
    <div className="mt-4 flex flex-wrap gap-3">
      <Button variant="primary" appearance="solid" size="lg" loading={connecting}
        disabled={!connection || !consented || connected || connecting}
        onClick={() => { if (connection) void controller.connect(connection, consent); }}>
        <ButtonLabel>Connect authorized synthetic session</ButtonLabel>
      </Button>
      <Button variant="neutral-light" appearance="outline" size="lg" disabled={!connected}
        aria-pressed={state.microphone} onClick={() => void controller.setMicrophone(!state.microphone)}>
        <ButtonLabel>{state.microphone ? "Mute microphone" : "Enable microphone"}</ButtonLabel>
      </Button>
      {state.playbackBlocked && <Button variant="neutral-light" appearance="soft" size="lg" onClick={() => void controller.enablePlayback()}>
        <ButtonLabel>Allow audio playback</ButtonLabel>
      </Button>}
      <Button variant="danger" appearance="outline" size="lg" disabled={!connected && !connecting} onClick={() => void controller.disconnect()}>
        <ButtonLabel>Disconnect browser audio</ButtonLabel>
      </Button>
    </div>
    {!consented && <p className="mt-3 text-sm">Audio is blocked until disclosure, microphone and vendor-processing consent have been recorded.</p>}
    {!connection && <p className="mt-3 text-sm">No authorized audio connection is available. The existing mock demo remains text-only.</p>}
    <p className="mt-3 text-sm">Disconnecting browser audio does not confirm that a provider call ended. Reserved usage remains under server reconciliation.</p>
  </section>;
}
