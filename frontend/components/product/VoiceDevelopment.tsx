"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import VoiceCaseCompanion from "./VoiceCaseCompanion";
import ReportSpeechConsent from "./ReportSpeechConsent";
import VoiceActivityRecap from "./VoiceActivityRecap";
import { Button, ButtonLabel } from "@/components/createui/button";
import { VoiceAudioControls } from "./VoiceAudioControls";
import { updateConsent } from "@/lib/api-client";
import { VoiceMediaController, type VoiceConnection } from "@/lib/voice/controller";
import { createLiveKitRoom } from "@/lib/voice/livekit-room";
import { availability, authorizeDevelopment, connectDevelopment, endDevelopment, readDevelopment, startDevelopment, type DevelopmentSession } from "@/lib/voice/api";
import { currentStep, probeMicrophone, workspaceStorageKeys, WorkspaceLifetime } from "@/lib/voice/workspace-lifetime";

export default function VoiceDevelopment() {
  const { userId, isLoaded } = useAuth();
  if (!isLoaded || !userId) return <p role="status" className="reference-container py-10 text-body">Sign in to open your voice workspace.</p>;
  return <VoiceWorkspace key={userId} account={userId} />;
}

function VoiceWorkspace({ account: userId }: { account: string }) {
  const keys = workspaceStorageKeys(userId);
  const storageKey = keys.session, attemptKey = keys.attempt;
  const [lifetime] = useState(() => new WorkspaceLifetime());
  const operation = useRef(false);
  const audioId = useId();
  const [enabled, setEnabled] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [microphone, setMicrophone] = useState(false);
  const [vendor, setVendor] = useState(false);
  const consentReady = accepted && microphone && vendor;
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState<DevelopmentSession | null>(null);
  const [connection, setConnection] = useState<VoiceConnection | null>(null);
  const [notice, setNotice] = useState("Checking synthetic audio availability.");
  const controller = useMemo(() => new VoiceMediaController({
    createRoom: () => { const element = document.getElementById(audioId); if (!element) throw new Error("Audio surface unavailable"); return createLiveKitRoom(element); },
    authorize: async id => { const status = await authorizeDevelopment(id, { signal: lifetime.signal }); return { sessionId: status.sessionId, roomName: status.roomName, allowed: status.allowed, expiresAt: status.expiresAt }; },
  }), [audioId, lifetime]);
  useEffect(() => {
    const scope = lifetime.activate();
    void availability({ signal: scope.signal }).then(value => { if (!scope.signal.aborted) { setEnabled(value); setNotice(value ? "Development audio is available to this account. Use fictional data only." : "Development audio is disabled. No call or payment will be created."); } }).catch(() => { if (!scope.signal.aborted) setNotice("Availability could not be verified. Audio remains disabled."); });
    void Promise.resolve().then(() => sessionStorage.getItem(storageKey)).then(async saved => {
      if (!saved || scope.signal.aborted) return;
      const value = await readDevelopment(saved, { signal: scope.signal });
      if (!scope.signal.aborted) setSession(value);
    }).catch(() => { if (!scope.signal.aborted) setNotice("A previous session could not be recovered. Existing usage remains under server reconciliation."); });
    return () => { scope.abort(); void controller.disconnect(); };
  }, [controller, storageKey, lifetime]);
  const sessionId = session?.sessionId;
  useEffect(() => {
    if (!sessionId) return;
    const scope = new AbortController();
    let pending = false;
    const timer = setInterval(() => { if (pending) return; pending = true; void readDevelopment(sessionId, { signal: scope.signal }).then(value => {
      if (scope.signal.aborted) return;
      setSession(value);
      if (["ended", "failed", "expired"].includes(value.state)) sessionStorage.removeItem(attemptKey);
      if (!value.allowed) { setConnection(null); void controller.disconnect(); }
    }).catch(() => { if (!scope.signal.aborted) { setSession(previous => previous ? { ...previous, allowed: false } : previous); setNotice("Session authorization could not be refreshed. Local audio disconnected; server reconciliation remains pending."); void controller.disconnect(); } }).finally(() => { pending = false; }); }, 5000);
    return () => { scope.abort(); clearInterval(timer); };
  }, [sessionId, controller, attemptKey]);
  async function start() {
    if (operation.current || !consentReady || !enabled) return;
    operation.current = true; setBusy(true);
    const signal = lifetime.signal;
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error();
      // Check actual permission before any provider operation; no recording or transmission here.
      await probeMicrophone(signal, () => navigator.mediaDevices.getUserMedia({ audio: true, video: false }));
      await currentStep(signal, () => updateConsent("voice_microphone", "grant", { signal }));
      await currentStep(signal, () => updateConsent("voice_vendor_processing", "grant", { signal }));
      const key = sessionStorage.getItem(attemptKey) ?? crypto.randomUUID();
      sessionStorage.setItem(attemptKey, key);
      const value = await currentStep(signal, () => startDevelopment(key, { signal }));
      sessionStorage.setItem(storageKey, value.sessionId); setSession(value);
      setNotice("Session intent recorded. Unknown operations retain their reservation; no replacement call is created.");
    } catch { if (!signal.aborted) setNotice("Start could not be confirmed. Check microphone access and refresh status; retries retain the same request key."); }
    finally { operation.current = false; if (!signal.aborted) setBusy(false); }
  }
  async function prepareConnection() {
    if (!session || operation.current || !consentReady) return;
    operation.current = true; setBusy(true); const signal = lifetime.signal;
    try { setConnection(await currentStep(signal, () => connectDevelopment(session.sessionId, { signal }))); }
    catch { if (!signal.aborted) setNotice("Connection could not be confirmed. Refresh this same session; no replacement call was requested."); }
    finally { operation.current = false; if (!signal.aborted) setBusy(false); }
  }
  async function finish(revoke = false) {
    if (operation.current) return;
    operation.current = true; setBusy(true); setConnection(null);
    const signal = lifetime.signal;
    try {
      await currentStep(signal, () => controller.disconnect());
      if (revoke) {
        setAccepted(false); setMicrophone(false); setVendor(false);
        await currentStep(signal, () => Promise.all([updateConsent("voice_microphone", "revoke", { signal }), updateConsent("voice_vendor_processing", "revoke", { signal })]));
      }
      if (session) setSession(await currentStep(signal, () => endDevelopment(session.sessionId, { signal })));
      setNotice("Termination requested. Only confirmed provider evidence settles reserved usage.");
    } catch { if (!signal.aborted) setNotice("Termination or consent update could not be confirmed. Local audio is disconnected; server recovery must confirm the provider state."); }
    finally { operation.current = false; if (!signal.aborted) setBusy(false); }
  }
  const open = session && ["reserved", "active"].includes(session.state);
  return <div className="reference-container py-10">
    <h1 className="text-heading-lg text-strongest">AI voice development</h1>
    <p className="mt-3 text-body">This is a disclosed AI service for fictional development conversations. It cannot verify policy facts, approve a report or replace a qualified human. No paid subscription is enabled.</p>
    <p className="mt-3 text-body"><Link href="/handoff">Request or check human review for an existing case</Link>. This separate workflow does not require an audio session.</p>
    <p role="status" aria-live="polite" className="mt-4 text-body">{notice}</p>
    <div className="mt-6 flex flex-wrap gap-3">
      <Button variant="neutral-light" appearance="outline" size="md" disabled={busy || Boolean(open)} aria-pressed={accepted} onClick={() => setAccepted(value => !value)}><ButtonLabel>{accepted ? "AI disclosure accepted" : "Accept AI disclosure"}</ButtonLabel></Button>
      <Button variant="neutral-light" appearance="outline" size="md" disabled={busy || Boolean(open)} aria-pressed={microphone} onClick={() => setMicrophone(value => !value)}><ButtonLabel>{microphone ? "Microphone consent selected" : "Allow microphone processing"}</ButtonLabel></Button>
      <Button variant="neutral-light" appearance="outline" size="md" disabled={busy || Boolean(open)} aria-pressed={vendor} onClick={() => setVendor(value => !value)}><ButtonLabel>{vendor ? "Vaani processing consent selected" : "Allow Vaani vendor processing"}</ButtonLabel></Button>
      <Button variant="primary" appearance="solid" size="lg" loading={busy} disabled={!enabled || !consentReady || Boolean(open)} onClick={() => void start()}><ButtonLabel>Prepare fictional development session</ButtonLabel></Button>
      <Button variant="neutral-light" appearance="soft" size="md" disabled={busy || !consentReady || !open || Boolean(session?.endRequested)} onClick={() => void prepareConnection()}><ButtonLabel>Prepare audio connection</ButtonLabel></Button>
      <Button variant="danger" appearance="outline" size="md" disabled={busy || !open} onClick={() => void finish()}><ButtonLabel>Request provider end</ButtonLabel></Button>
      <Button variant="danger" appearance="ghost" size="md" disabled={busy || !accepted} onClick={() => void finish(true)}><ButtonLabel>Withdraw audio consent</ButtonLabel></Button>
    </div>
    {session && <p className="mt-4 text-body" aria-live="polite">Session: {session.phase} · Reserved: {session.reservedSeconds} seconds · Confirmed usage: {session.consumedSeconds} seconds.</p>}
    {userId && <ReportSpeechConsent key={userId} account={userId} active={Boolean(open)} disabled={busy} onStop={() => finish()} />}
    <div id={audioId} />
    <div className="mt-6"><VoiceAudioControls controller={controller} connection={connection} consent={{ aiDisclosureAccepted: accepted, microphone, vendorProcessing: vendor }} /></div>
    <p className="mt-4 text-body">A dashboard connection error alone does not identify a wrong token. The server also requires an authorized call binding, current consent and development gates.</p>
    {session && userId && <VoiceCaseCompanion key={`${userId}:${session.sessionId}`} voice={session.sessionId} account={userId} enabled={Boolean(session.allowed && consentReady && !session.endRequested && !busy)} />}
    {session && <VoiceActivityRecap key={`${userId}:${session.sessionId}:activity`} account={userId} voice={session.sessionId} />}
  </div>;
}
