"use client";
import { useState } from "react";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";

const facts = [
  { label: "Sum insured", icon: "shield", detail: "The amount available for eligible claims.", question: "What limit applies to each person and the whole family?" },
  { label: "Room rent limit", icon: "heart", detail: "Check whether your room choice changes the amount payable.", question: "Is there a room category or daily expense limit?" },
  { label: "Waiting period", icon: "clock", detail: "Check when each type of cover starts.", question: "Which waiting periods apply to this application?" },
  { label: "Day-care surgery", icon: "file", detail: "Look for the procedures and conditions listed in the wording.", question: "Which day-care treatments are included or excluded?" },
  { label: "Co-payment", icon: "compare", detail: "Check any share of an eligible claim you would need to pay.", question: "When does a co-payment apply, and how is it calculated?" },
  { label: "Pre-existing conditions", icon: "heart", detail: "Review disclosure requirements and the relevant policy clauses.", question: "How are declared conditions treated by this policy?" },
];
const sections = [
  ["Policy facts", "The terms, in plain language", "file"],
  ["Coverage analysis", "What to examine for your needs", "shield"],
  ["Gaps & limits", "The details worth a closer look", "search"],
  ["Sources & trail", "Where each answer comes from", "folder"],
];

export default function ReferenceWorkspace({ comparison = false }: { comparison?: boolean }) {
  const [section, setSection] = useState(0);
  const [selected, setSelected] = useState(1);
  const [claim, setClaim] = useState("");
  const [checked, setChecked] = useState(false);
  return <div className={`reference-workspace${comparison ? " is-comparison" : ""}`}>
    <div className="preview-note"><span className="preview-dot" />Interactive design preview · No policy has been verified. Examples are not insurance recommendations.</div>
    <div className="case-grid" id="policy-decoder">
      <section className="paper-panel case-panel">
        <div className="case-tabs"><span className="active"><Glyph name="folder" size={17} />Health insurance case</span><span>YOUR COVER, UNDERSTOOD</span></div>
        <div className="case-body">
          <div className="panel-heading"><Glyph name="folder" size={30} /><div><h2>Health Insurance Case</h2><p>Policy details, coverage, exclusions and what the evidence shows.</p></div><span className="mini-stamp"><Glyph size={17} /> SAMPLE<br />CASE FILE</span></div>
          <h3 className="eyebrow">A clearer picture</h3>
          <div className="findings"><span><Glyph name="file" size={13} />6 areas to explore</span><span><Glyph name="search" size={13} />Sources pending</span><span>Every detail deserves<br />a closer look.</span></div>
          <div className="case-content"><div className="case-menu">{sections.map(([title, subtitle, icon], i) => <button key={title} className={section === i ? "selected" : ""} onClick={() => setSection(i)} aria-pressed={section === i}><Glyph name={icon} size={21} /><span><strong>{title}</strong><small>{subtitle}</small></span><span>›</span></button>)}</div><div className="case-folder"><span className="paper-clip" /><p>Your<br />independent<br />case file</p><Glyph size={26} /></div></div>
          <div className="section-detail" aria-live="polite">{[
            "Select a policy fact below to see the question to ask.",
            "Your profile and policy wording will be needed to assess need-fit.",
            "Exclusions, room limits and waiting periods need document checks.",
            "Source documents and verification dates will appear with each checked claim.",
          ][section]}</div>
        </div>
      </section>
      <section className="paper-panel claim-panel">
        <Glyph name="search" size={47} /><h2>What did they tell you?</h2><p>Tell us what the agent said.<br />Let’s check it against the policy wording.</p>
        <form onSubmit={e => { e.preventDefault(); setChecked(true); }}>
          <label htmlFor="agent-claim" className="sr-only">What did the agent tell you?</label>
          <input id="agent-claim" value={claim} onChange={e => { setClaim(e.target.value); setChecked(false); }} placeholder="“All hospital rooms are covered…”" required maxLength={600} />
          <small>No policy document connected in this preview.</small>
          <button className="pill-button small" type="submit">Check against policy <Glyph name="arrow" size={14} /></button>
        </form>
        <div className="claim-result" role="status"><div className="result-title"><Glyph name={checked ? "search" : "file"} size={24} /><div><strong>{checked ? "Policy wording needed" : "Evidence before an answer"}</strong><span>{checked ? "Your statement has not been verified." : "A claim needs a source, not an assumption."}</span></div></div>
          {checked && <blockquote>“{claim}”</blockquote>}
          <p>{checked ? "This preview cannot check a claim. A source document and a verification date are required before a result can be shown." : "The source clause and its verification date belong beside every policy answer."}</p><div className="evidence-meta"><span><Glyph name="file" size={12} />Source pending</span><span><Glyph name="clock" size={12} />Date pending</span></div>
        </div>
      </section>
    </div>
    <div className="facts-grid" id="what-we-compare">
      <section className="paper-panel facts-panel">
        <div className="panel-heading"><Glyph name="file" size={30} /><div><h2>{comparison ? "Policy comparison" : "Policy Facts"}</h2><p>What to look for in the wording — one detail at a time.</p></div><span className="mini-stamp"><Glyph name="lock" size={16} /> EVIDENCE<br />PENDING</span></div>
        <div className="facts-table-wrap"><table className="facts-table"><thead><tr><th>What you get</th><th>{comparison ? "Policy A" : "Policy details"}</th>{comparison && <th>Policy B</th>}<th>Status</th><th>Explore</th></tr></thead><tbody>{facts.map((fact, i) => <tr key={fact.label} className={selected === i ? "active-fact" : ""}><th scope="row"><span><Glyph name={fact.icon} size={17} />{fact.label}</span></th><td>Awaiting document</td>{comparison && <td>Awaiting document</td>}<td><span className="pending-status">Unverified</span></td><td><button onClick={() => setSelected(i)} aria-label={`Explore ${fact.label}`} aria-pressed={selected === i}><Glyph name="search" size={17} /></button></td></tr>)}</tbody></table></div>
        <div className="facts-footer"><span>Source: not supplied</span><span>Last verified: not yet verified</span></div>
      </section>
      <aside className="paper-panel evidence-panel" aria-live="polite">
        <div className="clause-paper"><span className="paper-clip" /><div className="eyebrow"><Glyph name="search" size={15} />EXHIBIT {String.fromCharCode(65 + selected)} · EXAMPLE</div><h3>{facts[selected].label}</h3><p>Original policy wording will appear here after the source document is checked.</p><span className="document-lines" /></div>
        <h3 className="eyebrow">In plain language</h3><p>{facts[selected].detail}</p>
        <h3 className="eyebrow">A question worth asking</h3><p>{facts[selected].question}</p>
        <div className="evidence-meta"><span><Glyph name="file" size={12} />Source pending</span><span><Glyph name="clock" size={12} />Date pending</span></div>
      </aside>
    </div>
    <section className="trail-panel paper-panel" id="trust"><div><h2>Every recommendation has a trail.</h2><p>Trace each answer to its source.<br />Know what was checked — and what still needs review.</p></div><div className="trail-links"><span><Glyph name="file" />Policy document</span><span><Glyph name="search" />Source clause</span><span><Glyph name="clock" />Verification date</span><span><Glyph name="shield" />Advisor review</span></div><Link className="trail-home" href="/intake" aria-label="Start your health insurance case"><Glyph size={35} /><span>Start your case ↗</span></Link></section>
  </div>;
}
