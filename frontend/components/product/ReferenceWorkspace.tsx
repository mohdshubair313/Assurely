"use client";

import { useState } from "react";
import Glyph from "@/components/ui/Glyph";
import styles from "@/app/(product)/comparison/comparison.module.css";

const facts = [
  { label: "Sum insured", group: "Financial limits", icon: "shield", detail: "Compare the total cover, whether it is shared across the family, and any benefit-specific caps.", question: "What is the total amount available, and which limits apply to each benefit?" },
  { label: "Room category", group: "Hospital expenses", icon: "heart", detail: "Room eligibility can affect more than the room bill. Review linked deductions and conditions in the same wording.", question: "Which room categories are allowed, and can choosing another room affect other costs?" },
  { label: "Co-payment", group: "Your share", icon: "compare", detail: "Check when a co-payment applies, how the share is calculated, and whether any situations are treated differently.", question: "When would I pay a share of an eligible claim, and how is it calculated?" },
  { label: "Waiting periods", group: "When cover begins", icon: "clock", detail: "Different benefits or conditions can have different waiting periods. Compare the exact start and end rules.", question: "Which waiting period applies to each benefit or declared condition?" },
  { label: "Pre-existing conditions", group: "Disclosures", icon: "heart", detail: "Look at the disclosure requirements and the policy wording that applies to conditions declared in the application.", question: "How are declared conditions handled, and what wording supports that answer?" },
  { label: "Day-care procedures", group: "Treatments", icon: "file", detail: "Check the listed procedures, admission requirements, and exclusions rather than relying on a broad summary.", question: "Which day-care treatments are included, and what conditions apply?" },
  { label: "Restoration benefit", group: "Cover during a policy year", icon: "shield", detail: "Compare what triggers restoration, how much can be restored, and which claims can use it.", question: "When does restoration apply, and what limits or conditions govern its use?" },
  { label: "Cashless hospitals", group: "Access to care", icon: "search", detail: "Network information can change. Confirm the hospital and location against a current insurer source.", question: "Is my preferred hospital currently in the network for this policy?" },
];

function SourceCell() {
  return <span className={styles.sourceCell}><Glyph name="file" size={15} /> Awaiting wording<small>Policy document needed</small></span>;
}

export default function ReferenceWorkspace() {
  const [selected, setSelected] = useState(0);
  const [claim, setClaim] = useState("");
  const [checkedClaim, setCheckedClaim] = useState<string | null>(null);
  const selectedFact = facts[selected];

  return <main className={styles.workspace}>
    <div className={styles.previewNote}><span className={styles.previewDot} /><span><strong>Design preview.</strong> No policy documents are connected, so no policy terms have been verified.</span></div>

    <section className={styles.metrics} aria-label="Comparison status">
      <div className={styles.metric}><span className={styles.metricValue}>08</span><span className={styles.metricLabel}>Details to review<small>Questions across your health cover</small></span></div>
      <div className={styles.metric}><span className={styles.metricValue}>02</span><span className={styles.metricLabel}>Policy slots<small>Side-by-side document columns</small></span></div>
      <div className={styles.metric}><span className={styles.metricValue}>00</span><span className={styles.metricLabel}>Terms verified<small>Sources required before comparison</small></span></div>
    </section>

    <section className={`${styles.panel} ${styles.matrixPanel}`} aria-labelledby="matrix-title">
      <div className={styles.panelHeading}><div><p className={styles.panelKicker}>THE SIDE-BY-SIDE REVIEW</p><h2 id="matrix-title">Policy difference matrix</h2></div><p>Each cell stays open until its policy wording is available to check.</p></div>
      <p className={styles.scrollHint}>Swipe sideways to compare both policy columns.</p>
      <div className={styles.tableScroll} role="region" aria-label="Policy difference matrix. Scroll horizontally to compare policy columns." tabIndex={0}>
        <table className={styles.matrix}>
          <caption className={styles.srOnly}>A comparison checklist for two health policies. No policy documents have been provided or verified.</caption>
          <thead><tr><th scope="col">Policy detail</th><th scope="col">Policy A</th><th scope="col">Policy B</th><th scope="col">Evidence status</th><th scope="col"><span className={styles.srOnly}>Explore detail</span></th></tr></thead>
          <tbody>{facts.map((fact, index) => <tr key={fact.label} className={selected === index ? styles.selected : undefined}>
            <th scope="row"><span className={styles.factName}>{fact.label}<small>{fact.group}</small></span></th>
            <td><SourceCell /></td><td><SourceCell /></td>
            <td className={styles.statusCell}><span className={styles.statusTag}>Not checked</span></td>
            <td><button type="button" className={styles.exploreButton} onClick={() => setSelected(index)} aria-label={`Explore ${fact.label}`} aria-pressed={selected === index}><Glyph name="arrow" size={16} /></button></td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className={styles.tableFoot}><span>Both policy columns are placeholders until documents are supplied.</span><span>Source · Not supplied &nbsp; / &nbsp; Verified · No</span></div>
    </section>

    <section className={styles.detailGrid} aria-label="Selected policy detail">
      <article className={`${styles.panel} ${styles.detailPanel}`}>
        <div className={styles.detailTop}><p className={styles.panelKicker}>SELECTED DETAIL / {String(selected + 1).padStart(2, "0")}</p><span className={styles.selectedIndex}>08 ITEMS</span></div>
        <div className={styles.detailContent} key={selected}>
          <h3>{selectedFact.label}</h3>
          <p className={styles.detailSummary}>{selectedFact.detail}</p>
          <div className={styles.questionBox}><span>A QUESTION WORTH ASKING</span><p>{selectedFact.question}</p></div>
        </div>
      </article>
      <aside className={`${styles.panel} ${styles.evidencePanel}`}>
        <h3>What makes a difference verifiable?</h3>
        <ul className={styles.evidenceList}>
          <li><span><Glyph name="file" size={14} /></span><span><strong>The exact document</strong><small>Policy wording and schedule for each option.</small></span></li>
          <li><span><Glyph name="search" size={14} /></span><span><strong>The clause behind the detail</strong><small>Specific wording, not a general summary.</small></span></li>
          <li><span><Glyph name="clock" size={14} /></span><span><strong>A verification date</strong><small>So you can see when the source was checked.</small></span></li>
        </ul>
      </aside>
    </section>

    <section className={`${styles.panel} ${styles.statementPanel}`} aria-labelledby="statement-title">
      <div className={styles.statementIntro}><p className={styles.panelKicker}>CHECK A STATEMENT</p><h2 id="statement-title">“I was told it’s covered.”</h2><p>Use this preview to see how a question is handled when the source is missing. It will not verify policy wording.</p></div>
      <div>
        <form className={styles.claimForm} onSubmit={(event) => { event.preventDefault(); setCheckedClaim(claim.trim()); }}>
          <label htmlFor="agent-claim">What would you like to check?</label>
          <textarea id="agent-claim" value={claim} onChange={(event) => { setClaim(event.target.value); setCheckedClaim(null); }} placeholder="For example: “A private room is included.”" maxLength={600} required />
          <p className={styles.formHelp}>Preview only · Your text stays in this page and is not submitted.</p>
          <button className={styles.submitButton} type="submit">Check the statement <Glyph name="arrow" size={15} /></button>
        </form>
        <div className={styles.claimResult} role="status"><Glyph name="file" size={19} /><div><strong>{checkedClaim ? "Source needed before an answer" : "Evidence comes first"}</strong><p>{checkedClaim ? "This statement has not been verified. Add the policy wording and source date before drawing a conclusion." : "No policy document is connected to this preview, so no policy-specific result can be shown."}</p></div>{checkedClaim && <blockquote>“{checkedClaim}”</blockquote>}</div>
      </div>
    </section>

    <footer className={styles.trail}>
      <div className={styles.trailCopy}><h2>A comparison should leave a trail.</h2><p>Keep each explanation connected to its source, clause, and verification date.</p></div>
      <div className={styles.trailItems} aria-label="Evidence trail requirements"><div className={styles.trailItem}><Glyph name="file" size={17} /><span>Policy document</span></div><div className={styles.trailItem}><Glyph name="search" size={17} /><span>Source clause</span></div><div className={styles.trailItem}><Glyph name="clock" size={17} /><span>Checked date</span></div><div className={styles.trailItem}><Glyph name="shield" size={17} /><span>Review status</span></div></div>
    </footer>
  </main>;
}
