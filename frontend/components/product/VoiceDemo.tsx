"use client";

import { useEffect, useState } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { SegmentedControl, SegmentedControlItem } from "@/components/createui/segmented-control";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import { ApiError, endVoiceSession, getActiveVoiceSession, getVoiceSession, getVoiceEntitlement, sendVoiceDemoPrompt, startVoiceSession, updateConsent, type VoiceEntitlement } from "@/lib/api-client";
import styles from "./voice-demo.module.css";

type Language = "en" | "hi" | "hinglish";
type ActiveSession = { session_id: string; state: string; reserved_seconds: number; consumed_seconds: number; elapsed_seconds: number; ai_disclosure: string };
type Answer = { answer: string; source: string };

export default function VoiceDemo() {
  const [entitlement, setEntitlement] = useState<VoiceEntitlement | null>(null);
  const [language, setLanguage] = useState<Language>("en");
  const [session, setSession] = useState<ActiveSession | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState<{ key: string; language: Language } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([getVoiceEntitlement({ signal: controller.signal }), getActiveVoiceSession({ signal: controller.signal })])
      .then(([available, current]) => {
        setEntitlement(available);
        if (current?.provider === "mock" && ["active", "reserved"].includes(current.state)) {
          setSession(current); setElapsed(current.elapsed_seconds);
        }
      }).catch(() => setNotice("Voice availability could not be confirmed. Refresh this page to try again."));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!session || session.state !== "active") return;
    const timer = window.setInterval(() => setElapsed(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [session]);

  const sessionId = session?.session_id;
  const sessionState = session?.state;
  useEffect(() => {
    if (!sessionId || !sessionState || !["active", "reserved"].includes(sessionState)) return;
    const controller = new AbortController();
    let fetching = false;
    const timer = window.setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const current = await getVoiceSession(sessionId, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setSession(current); setElapsed(current.elapsed_seconds);
        if (!["active", "reserved"].includes(current.state)) {
          setAttempt(null); setAnswer(null);
          setNotice(`The server confirmed the demo is ${current.state}.`);
          setEntitlement(await getVoiceEntitlement({ signal: controller.signal }));
        }
      } catch { if (!controller.signal.aborted) setNotice("The demo state could not be confirmed. Refresh to recover it."); }
      finally { fetching = false; }
    }, 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [sessionId, sessionState]);

  async function start() {
    setBusy(true); setNotice(""); setAnswer(null); setElapsed(0);
    try {
      const request = attempt ?? { key: crypto.randomUUID(), language };
      setAttempt(request);
      await updateConsent("voice_demo", "grant");
      const result = await startVoiceSession(request.language, request.key);
      setSession({ session_id: result.session_id, state: result.state, reserved_seconds: result.reserved_seconds,
        consumed_seconds: result.consumed_seconds, elapsed_seconds: result.elapsed_seconds,
        ai_disclosure: result.ai_disclosure });
      if (result.state !== "reserved") setAttempt(null);
      setEntitlement(await getVoiceEntitlement());
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : "The prototype could not start. Your minutes were not confirmed.");
    } finally { setBusy(false); }
  }

  async function ask(prompt: "copay" | "estimate" | "agent_claim" | "human_review") {
    if (!session || session.state !== "active") return;
    setBusy(true); setNotice("");
    try { setAnswer(await sendVoiceDemoPrompt(session.session_id, prompt)); }
    catch (error) { setNotice(error instanceof ApiError ? error.message : "The example answer could not be confirmed."); }
    finally { setBusy(false); }
  }

  async function end() {
    if (!session || !["active", "reserved"].includes(session.state)) return;
    setBusy(true); setNotice("");
    try {
      const result = await endVoiceSession(session.session_id);
      setSession(current => current ? { ...current, state: result.state, consumed_seconds: result.consumed_seconds } : current);
      setAttempt(null);
      setEntitlement(await getVoiceEntitlement());
    } catch (error) { setNotice(error instanceof ApiError ? error.message : "The server could not confirm that the prototype ended."); }
    finally { setBusy(false); }
  }

  const active = session?.state === "active";
  const pending = session?.state === "reserved";
  async function withdraw() {
    setBusy(true); setNotice("");
    try {
      await updateConsent("voice_demo", "revoke");
      if (session) setSession(await getVoiceSession(session.session_id));
      setAttempt(null); setAnswer(null); setEntitlement(await getVoiceEntitlement());
      setNotice("Demo consent withdrawn. Open synthetic sessions were closed.");
    } catch (error) { setNotice(error instanceof ApiError ? error.message : "Withdrawal could not be confirmed. Retry."); }
    finally { setBusy(false); }
  }
  return <section className={styles.page}>
    <header className={styles.header}>
      <p className={styles.eyebrow}>PRIVATE PRODUCT PROTOTYPE</p>
      <h1>Talk through a policy example.</h1>
      <p>This is a mock interface for a future Assurely AI voice guide. It does not open your microphone, connect audio, call Vaani, or use your case.</p>
    </header>

    <InlineAlert variant="info" appearance="soft" layout="vertical" className={styles.disclosure}>
      <InlineAlertContent><InlineAlertDescription className="line-clamp-none">
        I am an AI insurance guide. This prototype uses a fictional policy fixture for explanation only. It is not professional approval or a claim decision.
      </InlineAlertDescription></InlineAlertContent>
    </InlineAlert>

    <div className={styles.grid}>
      <article className={styles.panel}>
        <div className={styles.panelHead}><div><span className={styles.pulse} aria-hidden="true" /><span>Voice session</span></div>
          <span className={styles.badge}>{active ? "SIMULATION ACTIVE" : "NO AUDIO"}</span></div>
        <h2>{active ? "Your synthetic demo is ready." : "Choose a demo language."}</h2>
        <p className={styles.body}>English and Hindi are selectable labels only in this mock. Actual speech and Hinglish quality have not been tested.</p>
        <div className={styles.language} aria-label="Prototype response language">
          <SegmentedControl value={language} onValueChange={value => setLanguage(value as Language)} variant="primary" appearance="grouped" size="md" shape="rounded">
            <SegmentedControlItem value="en" disabled={busy || active || pending || Boolean(attempt)}>English</SegmentedControlItem>
            <SegmentedControlItem value="hi" disabled={busy || active || pending || Boolean(attempt)}>Hindi</SegmentedControlItem>
            <SegmentedControlItem value="hinglish" disabled={busy || active || pending || Boolean(attempt)}>Hinglish</SegmentedControlItem>
          </SegmentedControl>
        </div>
        <div className={styles.status} role="status" aria-live="polite">
          <span className={active ? styles.statusDotActive : styles.statusDot} aria-hidden="true" />
          {active ? `Prototype timer ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}` : "Microphone not requested · audio not connected"}
        </div>
        <p className={styles.body}>Starting accepts storage of this synthetic demo&apos;s session and simulated usage records. No microphone, vendor audio processing or saved conversation is authorized.</p>
        {pending && <p role="status">The server is recovering the same demo start. No new session is being created.</p>}
        {!active && !pending ? <Button type="button" variant="primary" appearance="solid" size="lg" loading={busy}
          disabled={busy || !entitlement?.enabled} onClick={() => void start()}><ButtonLabel>{attempt ? "Agree and retry the same demo" : "Agree and start synthetic demo"}</ButtonLabel></Button>
          : <Button type="button" variant="danger" appearance="solid" size="md" loading={busy}
            disabled={busy} onClick={() => void end()}><ButtonLabel>End demo</ButtonLabel></Button>}
        <Button type="button" variant="neutral-light" appearance="soft" size="md" disabled={busy} onClick={() => void withdraw()}><ButtonLabel>Withdraw demo consent</ButtonLabel></Button>
        <p className={styles.usage}>{entitlement?.enabled ? `${entitlement.minutes_remaining} included test minutes available · ${entitlement.active_sessions} active session` : "No test entitlement is enabled for this account."}</p>
      </article>

      <article className={styles.panel}>
        <div className={styles.panelHead}><div><span className={styles.fixtureIcon} aria-hidden="true">§</span><span>Demo fixture</span></div>
          <span className={styles.synthetic}>SYNTHETIC · UNVERIFIED</span></div>
        <h2>One fictional coverage term.</h2>
        <p className={styles.body}>The example says a 10% co-payment applies. No insurer, real document, premium or customer&apos;s policy is represented.</p>
        <div className={styles.promptList}>
          <Button variant="neutral-light" appearance="soft" size="md" disabled={!active || busy} onClick={() => void ask("copay")}><ButtonLabel>Explain co-payment</ButtonLabel></Button>
          <Button variant="neutral-light" appearance="soft" size="md" disabled={!active || busy} onClick={() => void ask("estimate")}><ButtonLabel>Show fictional math</ButtonLabel></Button>
          <Button variant="neutral-light" appearance="soft" size="md" disabled={!active || busy} onClick={() => void ask("agent_claim")}><ButtonLabel>Check a sales statement</ButtonLabel></Button>
          <Button variant="neutral-light" appearance="soft" size="md" disabled={!active || busy} onClick={() => void ask("human_review")}><ButtonLabel>Ask for human review</ButtonLabel></Button>
        </div>
        {answer && <div className={styles.answer} aria-live="polite"><p>{answer.answer}</p><small>Source: {answer.source} · synthetic fixture · not verified</small></div>}
        {session && <p className={styles.usage}>Session state: {session.state} · simulated use: {session.consumed_seconds}s · reserved: {session.reserved_seconds}s</p>}
      </article>
    </div>

    {notice && <InlineAlert variant="warning" appearance="soft" role="alert"><InlineAlertContent><InlineAlertDescription>{notice}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
    <p className={styles.footer}>No call audio, transcript, summary, payment or human-review request is created by this prototype. Held customer reports remain inaccessible here.</p>
  </section>;
}
