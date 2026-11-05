"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Input } from "@/components/createui/input";
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from "@/components/createui/inline-alert";
import ProgressPath from "@/components/ui/ProgressPath";
import { postMessage, updateConsent } from "@/lib/api-client";
import { intakeQuestion, priorities, budgets, covers, type Intake } from "@/lib/intake";
import { useCaseTask } from "@/hooks/use-case-task";
import styles from "./intake.module.css";
const steps = ["Your household", "Your priorities", "Your budget", "Existing cover"];
const titles = ["Who would you like to protect?", "What matters most to you?", "What annual premium range feels comfortable?", "Are you already covered?"];
export default function IntakePage() {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<Intake>({ adults: "", children: "", age: "", city: "", priorities: [], budget: "", cover: "" });
  const [consent, setConsent] = useState(false);
  const [result, setResult] = useState<{ session: string; reply: string } | null>(null);
  const [caseId, setCaseId] = useState("");
  const { run, busy, notice } = useCaseTask("intake");
  const update = (key: keyof Intake, value: string | string[]) => setAnswers(previous => ({ ...previous, [key]: value }));
  return <section className={styles.page} aria-labelledby="page-title"><div className={styles.ambient} aria-hidden="true" /><div className={styles.shell}>
    <header className={styles.pageHeader}><div className={styles.headerMark}><span className={styles.markIcon} aria-hidden="true">A</span><span>HEALTH COVER <small>A GUIDED STARTING POINT</small></span></div><Link href="/" className={styles.exitLink}>Back to the overview ↗</Link></header>
    <div className={styles.layout}><aside className={styles.story}><span className={styles.storyLabel}>A CLEARER START</span><h2 id="page-title">Your needs,<br /><em>before the fine print.</em></h2><p className={styles.storyCopy}>Organize your preferences, then send them to your health-cover case. Your answers stay in this page until you choose to submit.</p>
      <div className={styles.storyPath}>{steps.map((label, index) => <div className={`${styles.pathItem} ${step === index + 1 ? styles.pathActive : ""}`} key={label}><span className={styles.pathNumber}>0{index + 1}</span><span>{label}</span></div>)}</div>
      <p className={styles.storyCopy}>Sign in before submitting. No answers or account tokens are saved in browser storage.</p><Link href="/sign-in">Account access ↗</Link>
    </aside><div className={styles.formColumn}><div className={styles.formMeta}><span>YOUR COVER, YOUR WAY</span><span>STEP 0{step} / 04</span></div><div className={styles.progressWrap}><ProgressPath currentStep={step} totalSteps={4} labels={steps} /></div>
      {result ? <div className={styles.formCard}><h1>Case submitted.</h1><p role="status">{result.reply}</p><p>Your case identifier: {result.session}</p><Link href={`/workspace#${result.session}`} className={styles.previewLink}>Continue this case →</Link></div> : <form className={styles.formCard} onSubmit={event => { event.preventDefault(); if (step < 4) { setStep(step + 1); return; }
        void run(async ({ signal, commit }) => {
          if (!consent) throw new Error("Allow comparison processing before submitting.");
          const question = intakeQuestion(answers);
          await updateConsent("process_comparison", "grant", { signal });
          const id = caseId || crypto.randomUUID(); setCaseId(id);
          const response = await postMessage(id, question, undefined, { signal });
          commit(() => setResult({ session: response.session_id, reply: response.reply }));
        });
      }}><div className={styles.stepIntro}><span className={styles.stepEyebrow}>{steps[step - 1]}</span><h1 id="intake-heading">{titles[step - 1]}</h1><p>Share only details needed for the health-cover conversation.</p></div>
        <fieldset disabled={busy}><legend className="sr-only">{steps[step - 1]}</legend>
          {step === 1 && <div className={styles.fieldGrid}>
            <label className={styles.field} htmlFor="adults"><span>Adults to cover</span><select id="adults" required value={answers.adults} onChange={e => update("adults", e.target.value)}><option value="">Select number</option>{[1, 2, 3].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className={styles.field} htmlFor="children"><span>Children to cover</span><select id="children" required value={answers.children} onChange={e => update("children", e.target.value)}><option value="">Select number</option>{[0, 1, 2, 3].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className={styles.field} htmlFor="eldest-age"><span>Age of the eldest member</span><Input id="eldest-age" size="md" type="number" min={18} max={99} step={1} required value={answers.age} onChange={e => update("age", e.target.value)} /></label>
            <label className={styles.field} htmlFor="city-tier"><span>Where would you seek treatment?</span><select id="city-tier" required value={answers.city} onChange={e => update("city", e.target.value)}><option value="">Select a city profile</option><option value="tier_1">Metro or major city</option><option value="tier_2">State capital or regional hub</option><option value="tier_3">Another town or city</option></select></label>
          </div>}
          {step === 2 && <div className={styles.optionGrid}>{priorities.map(priority => <label key={priority} className={styles.checkOption}><input type="checkbox" aria-label={priority} checked={answers.priorities.includes(priority)} onChange={e => update("priorities", e.target.checked ? [...answers.priorities, priority] : answers.priorities.filter(item => item !== priority))} /><span>{priority}</span><span className={styles.checkMark} aria-hidden="true">{answers.priorities.includes(priority) ? "✓" : "+"}</span></label>)}</div>}
          {step === 3 && <><p>These are your budget preferences; they are not insurer premium quotations.</p><div className={styles.radioStack}>{budgets.map(budget => <label className={styles.radioOption} key={budget}><input type="radio" name="budget" aria-label={budget} required checked={answers.budget === budget} onChange={() => update("budget", budget)} /><span className={styles.radioDot} aria-hidden="true" /><span>{budget}</span></label>)}</div></>}
          {step === 4 && <><div className={styles.radioStack}>{covers.map(cover => <label className={styles.radioOption} key={cover}><input type="radio" name="cover" aria-label={cover} required checked={answers.cover === cover} onChange={() => update("cover", cover)} /><span className={styles.radioDot} aria-hidden="true" /><span>{cover}</span></label>)}</div><label className={styles.checkOption}><input type="checkbox" aria-label="I allow these details to be processed for my comparison" required checked={consent} onChange={e => setConsent(e.target.checked)} /><span>I allow these details to be processed for my comparison. This does not opt me into saved profiles or updates.</span><span className={styles.checkMark} aria-hidden="true">{consent ? "✓" : "+"}</span></label></>}
        </fieldset><div className={styles.formFooter}><Button type="button" variant="neutral-light" appearance="ghost" size="md" disabled={busy || step === 1} onClick={() => setStep(step - 1)}><ButtonLabel>← Back</ButtonLabel></Button><Button type="submit" variant="primary" appearance="solid" size="md" disabled={busy} loading={busy}><ButtonLabel>{step < 4 ? "Continue →" : "Submit my case"}</ButtonLabel></Button></div>
      </form>}
      {notice && <InlineAlert variant={notice.failed ? "danger" : "info"} appearance="soft" role={notice.failed ? "alert" : "status"}><InlineAlertContent><InlineAlertDescription className="line-clamp-none">{notice.text}</InlineAlertDescription></InlineAlertContent></InlineAlert>}
      {!result && caseId && <p>If submission could not be confirmed, <Link href={`/workspace#${caseId}`}>check this case status</Link> before submitting again.</p>}
    </div></div><footer className={styles.pageFoot}><span>HEALTH INSURANCE · INDIA</span><span>Clear questions make for a clearer conversation.</span></footer>
  </div></section>;
}
