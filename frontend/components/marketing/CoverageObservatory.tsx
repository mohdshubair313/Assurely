"use client";

import { useState } from "react";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Badge } from "@/components/createui/badge";
import { SegmentedControl, SegmentedControlItem } from "@/components/createui/segmented-control";
import CoverageScene, { type SceneStatus } from "./CoverageScene";
import styles from "./CoverageObservatory.module.css";

export type CoveragePhase = "uncertainty" | "questions" | "clarity";
const chapters = {
  uncertainty: { label: "01 · The problem", short: "The problem", number: "01", heading: "A promise isn’t the whole picture.", text: "The home is your life. The scattered pages and fragmented canopy represent the questions a policy summary can leave unanswered.", insight: "What does ‘covered’ mean for your situation?", details: ["Different terms, scattered across documents", "Conditions that need a closer look", "Questions left outside the summary"] },
  questions: { label: "02 · Look closer", short: "Look closer", number: "02", heading: "Make the questions visible.", text: "The canopy separates into individual panels. Room limits, waiting periods and shared costs become questions you can explore one at a time.", insight: "Which clause answers each question?", details: ["Find the relevant policy wording", "Examine limits and conditions", "Keep unanswered questions visible"] },
  clarity: { label: "03 · Find clarity", short: "Find clarity", number: "03", heading: "Bring the evidence together.", text: "The pages align into a question file. The amber panel remains open: a question stays unresolved until its wording and evidence are checked.", insight: "A clearer explanation, with its source beside it.", details: ["Your needs guide the comparison", "Source clauses support the explanation", "Uncertainty stays visible for review"] },
} as const;

export default function CoverageObservatory() {
  const [phase, setPhase] = useState<CoveragePhase>("uncertainty");
  const [rotation, setRotation] = useState(0);
  const [instant, setInstant] = useState(false);
  const [sceneStatus, setSceneStatus] = useState<SceneStatus>("loading");
  const chapter = chapters[phase];
  return <section id="how-it-works" className={styles.observatory} aria-labelledby="observatory-heading">
    <div className={styles.introduction} data-reveal><div><p className={styles.kicker}><span /> THE COVER OBSERVATORY</p><h2 id="observatory-heading">Your life is real.<br /><em>Your cover should be clear.</em></h2></div><p className={styles.introText}>A living illustration of the questions behind a policy.<br />Explore the problem. See what clarity looks like.</p></div>
    <div className={styles.experience}>
      <div className={styles.modelColumn}>
        <div className={styles.sceneCaption}><span className={styles.sceneDot} /> A HOME. A POLICY. THE SPACE BETWEEN.</div>
        <CoverageScene phase={phase} rotation={rotation} instant={instant} onRotationChange={setRotation} onStatusChange={setSceneStatus} />
        <div className={styles.modelControls}><span>{sceneStatus === "ready" ? <>Drag with a mouse to explore.<br />Use the controls on any device.</> : sceneStatus === "fallback" ? <>Explore the illustrated chapters below.<br />3D isn’t available in this browser.</> : <>The scene loads as you reach it.<br />You can explore every chapter below.</>}</span><div className={styles.rotationButtons}>
          <Button disabled={sceneStatus !== "ready"} variant="inverse-solid" appearance="outline" size="lg" shape="pill" iconOnly aria-label="Rotate model left" onClick={() => setRotation(value => Math.max(-0.85, value - 0.3))}><span className={styles.leftArrow}><Glyph name="arrow" size={18} /></span></Button>
          <Button disabled={sceneStatus !== "ready"} variant="inverse-solid" appearance="outline" size="lg" shape="pill" iconOnly aria-label="Reset model view" onClick={() => setRotation(0)}><Glyph name="compare" size={18} /></Button>
          <Button disabled={sceneStatus !== "ready"} variant="inverse-solid" appearance="outline" size="lg" shape="pill" iconOnly aria-label="Rotate model right" onClick={() => setRotation(value => Math.min(0.85, value + 0.3))}><Glyph name="arrow" size={18} /></Button>
        </div></div>
      </div>
      <div className={styles.storyColumn}>
        <div className={styles.chapterControl} onKeyDown={() => setInstant(true)} onPointerDown={() => setInstant(false)}>
          <SegmentedControl appearance="grouped" variant="neutral" size="md" shape="pill" value={phase} onValueChange={value => { if (value in chapters) setPhase(value as CoveragePhase); }} aria-label="Explore the insurance story">
            {(Object.keys(chapters) as CoveragePhase[]).map(key => <SegmentedControlItem key={key} value={key}>{chapters[key].short}</SegmentedControlItem>)}
          </SegmentedControl>
        </div>
        <div className={styles.chapterBody} aria-live="polite" aria-atomic="true"><p className={styles.chapterNumber}>CHAPTER / {chapter.number}</p><h3>{chapter.heading}</h3><p className={styles.chapterText}>{chapter.text}</p><ul className={styles.chapterDetails}>{chapter.details.map((detail, index) => <li key={detail}><span>{String(index + 1).padStart(2, "0")}</span>{detail}</li>)}</ul><div className={styles.insight}><Glyph name={phase === "clarity" ? "file" : "search"} size={19} /><p>{chapter.insight}</p></div></div>
        <div className={styles.previewNote}><Badge variant="warning" appearance="soft" size="sm" shape="pill">Illustration only</Badge><p>No policy has been assessed.<br />Source and verification date remain pending.</p></div>
        <Button asChild variant="primary" appearance="ghost" size="lg" shape="pill"><Link href="/#policy-decoder"><ButtonLabel>Explore the real questions</ButtonLabel><Glyph name="arrow" size={18} /></Link></Button>
      </div>
    </div>
    <div className={styles.legend}><span><i className={styles.amberSwatch} /> The open panel: a question to review</span><span><i className={styles.blueSwatch} /> The canopy: policy terms to examine</span><span><Glyph name="file" size={14} /> The pages: evidence still needed</span></div>
  </section>;
}
