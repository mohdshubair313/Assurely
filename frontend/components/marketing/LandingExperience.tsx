"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Badge } from "@/components/createui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/createui/tabs";
import { Input } from "@/components/createui/input";
import { InlineAlert, InlineAlertIcon, InlineAlertContent, InlineAlertHeading, InlineAlertTitle, InlineAlertDescription } from "@/components/createui/inline-alert";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/createui/accordion";
import LandingMotion from "./LandingMotion";
import CoverageObservatory from "./CoverageObservatory";
import ReflectiveSurface from "./ReflectiveSurface";
import styles from "./LandingExperience.module.css";

const terms = [
  { id: "room", title: "Room rent", icon: "heart", question: "What happens if I choose a different room?", intro: "Start with the room-category clause. Then follow any linked conditions before drawing a conclusion.", checks: ["Allowed room categories", "Any daily limit", "Related deduction clauses"] },
  { id: "waiting", title: "Waiting periods", icon: "clock", question: "When would each part of my cover begin?", intro: "Look for separate clauses rather than assuming that every benefit starts on the same date.", checks: ["Initial waiting-period wording", "Specific-condition clauses", "Declared-condition requirements"] },
  { id: "copay", title: "Co-payment", icon: "compare", question: "What share would I need to pay?", intro: "Ask which situations trigger a co-payment and where the calculation is documented.", checks: ["When the clause applies", "The documented calculation", "Exceptions and conditions"] },
  { id: "sum", title: "Sum insured", icon: "shield", question: "Which limit applies to me and my family?", intro: "Check the actual policy schedule alongside the wording. Leave figures open until the evidence is available.", checks: ["Individual or shared cover", "Policy-schedule limits", "Benefit-specific conditions"] },
  { id: "daycare", title: "Day-care", icon: "file", question: "Which procedures should I check?", intro: "Find the relevant wording for the treatment in question, including its conditions and exclusions.", checks: ["Treatment-specific wording", "Admission requirements", "Applicable exclusions"] },
  { id: "conditions", title: "Existing conditions", icon: "heart", question: "How should I disclose my health history?", intro: "Keep your disclosures and application questions together. Ask for a review when the wording is unclear.", checks: ["Disclosure questions", "Relevant policy clauses", "Questions for an advisor"] },
];
const comparisonLenses = [
  { label: "Your needs", detail: "Health history, household and budget", icon: "heart" },
  { label: "Policy conditions", detail: "Limits, waiting periods and exclusions", icon: "file" },
  { label: "Evidence", detail: "The wording behind each explanation", icon: "search" },
];
const questions = [
  { title: "Can this preview verify a policy?", answer: "No. These interactive examples explain what to look for. No policy document is connected here, so no policy-specific answer or figure is verified." },
  { title: "What if I need an advisor?", answer: "You can identify questions that need a human review. This landing-page preview does not send an advisor request; the live handoff needs a configured advisor destination." },
  { title: "Which insurance can I explore?", answer: "This version focuses on health insurance. Start with your needs, then examine the policy wording and its conditions before deciding." },
];

function EvidenceFolio() {
  const folio = useRef<HTMLDivElement>(null);
  return <div className={styles.folioStage} aria-hidden="true" onPointerMove={(event) => {
    if (!folio.current || event.pointerType !== "mouse" || !window.matchMedia("(hover: hover) and (pointer: fine)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width - 0.5) * 10;
    const y = ((event.clientY - box.top) / box.height - 0.5) * -8;
    folio.current.style.transform = `rotateX(${y}deg) rotateY(${x}deg)`;
  }} onPointerLeave={() => { if (folio.current) folio.current.style.transform = "rotateX(0deg) rotateY(0deg)"; }}>
    <div className={styles.orbitRing} /><div className={styles.orbitRingTwo} />
    <div className={styles.evidenceRail}><span>01 / DOCUMENT</span><span>02 / CLAUSE</span><span>03 / VERIFICATION</span></div><span className={styles.folioStar}>✦</span>
    <div className={styles.folio} ref={folio}>
      <div className={styles.backSheet}><span>THE POLICY DOCUMENT</span><Glyph name="file" size={36} /><div className={styles.paperLines} /></div>
      <div className={styles.middleSheet}><span>THE SOURCE CLAUSE</span><div className={styles.paperLines} /><div className={styles.highlightLine} /></div>
      <div className={styles.frontSheet}><div className={styles.folioHead}><Glyph name="shield" size={26} /><span>ASSURELY<br />EVIDENCE FILE</span></div><p>A clearer picture.<br /><em>One source at a time.</em></p><div className={styles.folioDivider} /><div className={styles.folioStatus}><span>SOURCE</span><strong>Not supplied</strong><span>LAST VERIFIED</span><strong>Not yet verified</strong></div><span className={styles.folioSeal}>A</span></div>
    </div>
    <span className={styles.folioNote}>A visual preview, not a verified policy.</span>
  </div>;
}

export default function LandingExperience() {
  const [claim, setClaim] = useState("");
  const [checkedClaim, setCheckedClaim] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  return <LandingMotion className={styles.landing}>
    <CoverageObservatory />

    <section className={styles.decoder} id="policy-decoder" aria-labelledby="decoder-heading">
      <div className={styles.decoderHeader} data-reveal><div><p className={styles.kicker}><span /> THE POLICY DECODER</p><h2 className={styles.heading} id="decoder-heading">Small clauses.<br /><em>Questions worth asking.</em></h2></div><p className={styles.lede}>Explore the details behind the headline.<br />Choose a term to open its question file.</p></div>
      <ReflectiveSurface className={styles.decoderPanel}>
        <div className={styles.decoderBar}><span><Glyph name="folder" size={18} /> YOUR COVER, UNDERSTOOD</span><Badge variant="warning" appearance="soft" size="md" shape="pill">Interactive preview</Badge></div>
        <Tabs defaultValue="room" size="md" activationMode="manual">
          <TabsList aria-label="Policy details to explore">{terms.map((term) => <TabsTrigger value={term.id} key={term.id} leading={<Glyph name={term.icon} size={18} />}>{term.title}</TabsTrigger>)}</TabsList>
          <p className={styles.tabHint}>Six details to explore. Scroll the tabs to see them all.</p>
          {terms.map((term, index) => <TabsContent value={term.id} key={term.id}><div className={styles.termContent}><div className={styles.termQuestion}><p className={styles.fileNumber}>QUESTION FILE / {String(index + 1).padStart(2, "0")}</p><h3>{term.question}</h3><p>{term.intro}</p><Badge variant="neutral" appearance="outline" size="sm" shape="pill" leading={<Glyph name="file" size={13} />}>Policy wording required</Badge></div><div className={styles.inspection}><p className={styles.fileNumber}>WHAT TO LOOK FOR</p><ul>{term.checks.map((check, i) => <li key={check}><span>{String(i + 1).padStart(2, "0")}</span>{check}<Glyph name="search" size={17} /></li>)}</ul><div className={styles.sourceState}><span>Source <strong>Not supplied</strong></span><span>Last verified <strong>Not yet verified</strong></span></div></div></div></TabsContent>)}
        </Tabs>
      </ReflectiveSurface>
    </section>

    <section className={styles.claimSection} id="what-we-compare" aria-labelledby="claim-heading">
      <div className={styles.claimCopy} data-reveal><p className={styles.kicker}><span /> WHAT WE COMPARE</p><h2 className={styles.heading} id="claim-heading">“It’s all covered.”<br /><em>Let’s look closer.</em></h2><p className={styles.lede}>Keep the statement. Find the clause.<br />Make space for what still needs checking.</p><ol className={styles.comparisonLenses}>{comparisonLenses.map((lens, i) => <li key={lens.label}><span className={styles.lensNumber}>{String(i + 1).padStart(2, "0")}</span><Glyph name={lens.icon} size={20} /><div><strong>{lens.label}</strong><p>{lens.detail}</p></div></li>)}</ol><div className={styles.claimFootnote}><Glyph name="file" size={18} /><p>A statement alone is not evidence.<br />The wording comes first.</p></div></div>
      <ReflectiveSurface className={styles.claimCard}><Badge variant="primary" appearance="soft" size="md" shape="pill" leading={<Glyph name="search" size={15} />}>Statement explorer</Badge><h3>What did they tell you?</h3><p>Try a statement you would want to check.</p><form onSubmit={(event) => { event.preventDefault(); if (!claim.trim()) { setInvalid(true); return; } setInvalid(false); setCheckedClaim(claim.trim()); }}>
        <label htmlFor="landing-claim" className={styles.inputLabel}>The statement</label><Input id="landing-claim" size="md" value={claim} onChange={(event) => { setClaim(event.target.value); setCheckedClaim(null); setInvalid(false); }} placeholder="All hospital rooms are covered…" maxLength={600} required aria-invalid={invalid} aria-describedby="claim-help" />
        <p id="claim-help" className={styles.formHelp}>{invalid ? "Enter a statement before continuing." : "Design preview · Your text stays in this page and is not submitted."}</p>
        <Button type="submit" variant="primary" appearance="solid" size="xl" shape="pill"><ButtonLabel>Explore this statement</ButtonLabel><Glyph name="arrow" size={18} /></Button>
      </form><div className={styles.claimResponse}><InlineAlert variant={checkedClaim ? "warning" : "neutral"} appearance="default" layout="vertical" role="status"><InlineAlertIcon><Glyph name={checkedClaim ? "search" : "file"} size={20} /></InlineAlertIcon><InlineAlertContent><InlineAlertHeading><InlineAlertTitle>{checkedClaim ? "Policy wording needed" : "Evidence before an answer"}</InlineAlertTitle><InlineAlertDescription>{checkedClaim ? "This statement has not been verified. A policy document, source clause and verification date are needed." : "No document is connected to this preview. No policy-specific result can be shown."}</InlineAlertDescription></InlineAlertHeading></InlineAlertContent></InlineAlert>{checkedClaim && <blockquote>{checkedClaim}</blockquote>}</div></ReflectiveSurface>
    </section>

    <section className={styles.trust} id="trust" aria-labelledby="trust-heading">
      <div className={styles.trustCopy} data-reveal><p className={styles.kicker}><span /> THE AUDIT TRAIL</p><h2 className={styles.heading} id="trust-heading">Clarity should<br /><em>leave a trail.</em></h2><p className={styles.lede}>A useful explanation lets you look behind it.<br />Keep the source, the checks and the open questions together.</p><ol className={styles.trustList}><li><Glyph name="file" size={19} /><div><strong>The document</strong><span>The policy wording that needs checking.</span></div></li><li><Glyph name="search" size={19} /><div><strong>The clause</strong><span>The exact passage behind a policy answer.</span></div></li><li><Glyph name="clock" size={19} /><div><strong>The verification date</strong><span>When the information was checked, or that it remains unverified.</span></div></li></ol></div><EvidenceFolio />
    </section>

    <section className={styles.faq} id="faq" aria-labelledby="faq-heading"><div data-reveal><p className={styles.kicker}><span /> BEFORE YOU SET OFF</p><h2 className={styles.heading} id="faq-heading">A little more<br /><em>clarity.</em></h2><p className={styles.lede}>A few things to know about this preview.</p></div><div className={styles.faqContent} data-reveal><p className={styles.faqLabel}>THE SHORT ANSWERS / 03</p><Accordion type="single" collapsible appearance="ghost-underline">{questions.map((question, i) => <AccordionItem key={question.title} value={`question-${i}`}><AccordionTrigger><span className={styles.faqQuestion}><span className={styles.faqNumber} aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>{question.title}</span></AccordionTrigger><AccordionContent>{question.answer}</AccordionContent></AccordionItem>)}</Accordion></div></section>
    <section className={styles.departure} aria-labelledby="departure-heading" data-reveal><span className={styles.departureStar} aria-hidden="true">✦</span><p className={styles.kicker}>YOUR NEXT CHAPTER</p><h2 className={styles.heading} id="departure-heading">A little less uncertainty.<br /><em>A clearer next step.</em></h2><p>Start with what matters to you.</p><Button asChild variant="primary" appearance="solid" size="xl" shape="pill"><Link href="/intake"><ButtonLabel>Find my cover</ButtonLabel><Glyph name="arrow" size={18} /></Link></Button><span className={styles.departureNote}>Health insurance. At your own pace.</span></section>
  </LandingMotion>;
}
