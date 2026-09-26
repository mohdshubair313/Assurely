import type { Metadata } from "next";
import Link from "next/link";
import ReferenceWorkspace from "@/components/product/ReferenceWorkspace";
export const metadata: Metadata = { title: "Your policy comparison — Assurely", description: "Explore health policy terms, questions and evidence in a clearly labeled design preview." };
export default function ComparisonPage() {
  return <div className="reference-container comparison-page"><div className="comparison-heading"><div><p className="eyebrow">YOUR NEEDS. THE POLICY DETAILS.</p><h1>A clearer view of your cover.</h1><p>Understand the differences. See the evidence. Decide with clarity.</p></div><Link className="pill-button secondary" href="/intake">Edit your priorities ↗</Link></div><ReferenceWorkspace comparison /></div>;
}
