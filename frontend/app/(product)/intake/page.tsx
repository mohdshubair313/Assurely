"use client";

import Link from "next/link";
import { useState } from "react";
import Button from "@/components/ui/Button";
import ProgressPath from "@/components/ui/ProgressPath";
import styles from "./intake.module.css";

const intakeSteps = [
  { label: "Your household", eyebrow: "01 / WHO NEEDS COVER?" },
  { label: "Your priorities", eyebrow: "02 / WHAT MATTERS TO YOU?" },
  { label: "Your budget", eyebrow: "03 / WHAT FEELS COMFORTABLE?" },
  { label: "Existing cover", eyebrow: "04 / WHERE ARE YOU STARTING?" },
] as const;

const priorities = [
  "Room choices without a room-rent limit",
  "A shorter wait for pre-existing conditions",
  "No co-payment, where available",
  "Cashless hospitals near me",
  "Day-care treatment cover",
  "Restoration or recharge benefit",
  "Maternity and newborn cover",
  "Cover for non-medical items",
];

const budgets = [
  "Under ₹15,000 a year",
  "₹15,000–₹25,000 a year",
  "₹25,000–₹40,000 a year",
  "₹40,000–₹60,000 a year",
  "Above ₹60,000 a year",
  "I’m still exploring the cost",
];

const coverOptions = [
  { value: "retail", label: "Yes, I have an active health policy" },
  { value: "employer", label: "I have cover through my employer" },
  { value: "none", label: "No, this would be my first policy" },
  { value: "unsure", label: "I’m not sure about my current cover" },
];

function StepContent({ step }: { step: number }) {
  if (step === 1) {
    return <>
      <div className={styles.stepIntro}>
        <span className={styles.stepEyebrow}>{intakeSteps[0].eyebrow}</span>
        <h1 id="intake-heading">Who would you like to protect?</h1>
        <p>A few starting details help shape a useful health-cover conversation.</p>
      </div>
      <div className={styles.fieldGrid}>
        <label className={styles.field} htmlFor="adults"><span>Adults to cover</span><select id="adults" defaultValue=""><option value="" disabled>Select number</option><option value="1">1 adult</option><option value="2">2 adults</option><option value="3">3 adults</option></select></label>
        <label className={styles.field} htmlFor="children"><span>Children to cover</span><select id="children" defaultValue=""><option value="" disabled>Select number</option><option value="0">No children</option><option value="1">1 child</option><option value="2">2 children</option><option value="3">3 children</option></select></label>
        <label className={styles.field} htmlFor="eldest-age"><span>Age of the eldest member</span><input id="eldest-age" type="number" min="18" max="99" placeholder="For example, 34" /></label>
        <label className={styles.field} htmlFor="city-tier"><span>Where would you seek treatment?</span><select id="city-tier" defaultValue=""><option value="" disabled>Select a city profile</option><option value="tier_1">Metro or major city</option><option value="tier_2">State capital or regional hub</option><option value="tier_3">Another town or city</option></select></label>
      </div>
    </>;
  }

  if (step === 2) {
    return <>
      <div className={styles.stepIntro}>
        <span className={styles.stepEyebrow}>{intakeSteps[1].eyebrow}</span>
        <h1 id="intake-heading">What matters most to you?</h1>
        <p>Choose any details you would want to understand while reviewing a policy.</p>
      </div>
      <div className={styles.optionGrid}>{priorities.map((priority, index) => <label className={styles.checkOption} key={priority}><input type="checkbox" /><span className={styles.optionIndex}>{String(index + 1).padStart(2, "0")}</span><span>{priority}</span><span className={styles.checkMark} aria-hidden="true">+</span></label>)}</div>
    </>;
  }

  if (step === 3) {
    return <>
      <div className={styles.stepIntro}>
        <span className={styles.stepEyebrow}>{intakeSteps[2].eyebrow}</span>
        <h1>What annual premium range feels comfortable?</h1>
        <p>This is a guide to your preferences. Any premium figures need to be checked against verified policy details.</p>
      </div>
      <div className={styles.radioStack}>{budgets.map((budget) => <label className={styles.radioOption} key={budget}><input type="radio" name="budget" /><span className={styles.radioDot} aria-hidden="true" /><span>{budget}</span></label>)}</div>
    </>;
  }

  return <>
    <div className={styles.stepIntro}>
      <span className={styles.stepEyebrow}>{intakeSteps[3].eyebrow}</span>
      <h1>Are you already covered?</h1>
      <p>Knowing where you are starting can help frame the questions to explore next.</p>
    </div>
    <div className={styles.radioStack}>{coverOptions.map((option) => <label className={styles.radioOption} key={option.value}><input type="radio" name="existing-cover" /><span className={styles.radioDot} aria-hidden="true" /><span>{option.label}</span></label>)}</div>
  </>;
}

export default function IntakePage() {
  const [currentStep, setCurrentStep] = useState(1);

  return <section className={styles.page} aria-labelledby="page-title">
    <div className={styles.ambient} aria-hidden="true" />
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div className={styles.headerMark}><span className={styles.markIcon} aria-hidden="true">A</span><span>HEALTH COVER <small>A GUIDED STARTING POINT</small></span></div>
        <Link href="/" className={styles.exitLink}>Back to the overview <span aria-hidden="true">↗</span></Link>
      </header>

      <div className={styles.layout}>
        <aside className={styles.story}>
          <span className={styles.storyLabel}><span /> A CLEARER START</span>
          <h2 id="page-title">Your needs,<br /><em>before the fine print.</em></h2>
          <p className={styles.storyCopy}>A thoughtful health-cover conversation starts with what matters in your life. We’ll use these steps to help organize the questions worth asking.</p>
          <div className={styles.storyPath} aria-label="Four steps in this preview">
            {intakeSteps.map((item, index) => <div className={`${styles.pathItem} ${currentStep === index + 1 ? styles.pathActive : ""} ${currentStep > index + 1 ? styles.pathComplete : ""}`} key={item.label}><span className={styles.pathNumber}>{currentStep > index + 1 ? "✓" : `0${index + 1}`}</span><span>{item.label}</span></div>)}
          </div>
          <div className={styles.storyNote}><span className={styles.noteSeal} aria-hidden="true">✳</span><p><strong>Take your time.</strong><br />You can move back and change your answers.</p></div>
          <div className={styles.paperLines} aria-hidden="true"><span /><span /><span /></div>
        </aside>

        <div className={styles.formColumn}>
          <div className={styles.formMeta}><span>YOUR COVER, YOUR WAY</span><span>STEP {String(currentStep).padStart(2, "0")} <i>/ 04</i></span></div>
          <div className={styles.progressWrap}><ProgressPath currentStep={currentStep} totalSteps={intakeSteps.length} labels={intakeSteps.map((step) => step.label)} /></div>
          <div className={styles.formCard} key={currentStep}>
            <StepContent step={currentStep} />
            <div className={styles.formFooter}>
              <Button variant="ghost" size="md" disabled={currentStep === 1} onClick={() => setCurrentStep((step) => Math.max(1, step - 1))}>← Back</Button>
              {currentStep < intakeSteps.length ? <Button variant="primary" size="md" onClick={() => setCurrentStep((step) => Math.min(intakeSteps.length, step + 1))}>Continue <span aria-hidden="true">→</span></Button> : <Link href="/comparison" className={styles.previewLink}>Open comparison preview <span aria-hidden="true">→</span></Link>}
            </div>
          </div>
          <div className={styles.previewNotice}><span aria-hidden="true">✳</span><p><strong>Design preview.</strong> Please use fictional details here; this screen does not submit or save your answers.</p></div>
        </div>
      </div>
      <footer className={styles.pageFoot}><span>HEALTH INSURANCE · INDIA</span><span>Clear questions make for a clearer conversation.</span></footer>
    </div>
  </section>;
}
