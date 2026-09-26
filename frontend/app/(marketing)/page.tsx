import type { Metadata } from "next";
import HeroSection from "@/components/marketing/HeroSection";
import ReferenceWorkspace from "@/components/product/ReferenceWorkspace";
import Glyph from "@/components/ui/Glyph";
export const metadata: Metadata = { title: "Assurely — Insurance shouldn’t make you guess" };
const steps = [
  { icon: "chat", title: "Tell us your priorities", text: "Share a few details about your health, family and what matters most to you." },
  { icon: "compare", title: "Compare the terms that change the outcome", text: "Explore the real-world trade-offs and hidden gaps — not just the price." },
  { icon: "shield", title: "Decide with a clear explanation", text: "See each assumption and the questions to ask before you decide." },
];
export default function LandingPage() {
  return <>
    <HeroSection />
    <div className="reference-container landing-content">
      <section className="guide-section" id="how-it-works"><h2>How Assurely Guides Your Choice</h2><div className="guide-steps paper-panel">{steps.map((step, i) => <div className="guide-step" key={step.title}><span className="step-icon"><Glyph name={step.icon} size={27} /></span><span className="step-number">{i + 1}</span><div><h3>{step.title}</h3><p>{step.text}</p></div>{i < 2 && <span className="step-arrow">→</span>}</div>)}</div></section>
      <ReferenceWorkspace />
      <section id="faq" className="faq-section"><h2>A little more clarity.</h2><details><summary>Can I use this preview to choose insurance?</summary><p>This is a design preview. Policy documents, figures and calculator assumptions still require verification before real recommendations can be delivered.</p></details><details><summary>What happens when a case needs an advisor?</summary><p>Advisor notification and delivery hold are still being built. This preview does not send a request to an advisor.</p></details><details><summary>Which insurance can I explore?</summary><p>This version focuses on health insurance. Other product types are outside the current scope.</p></details></section>
    </div>
  </>;
}
