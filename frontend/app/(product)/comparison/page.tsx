import type { Metadata } from "next";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import ReferenceWorkspace from "@/components/product/ReferenceWorkspace";
import styles from "./comparison.module.css";

export const metadata: Metadata = {
  title: "Your health policy comparison | Assurely",
  description: "Compare health policy details side by side, with the source and verification status clearly shown.",
};

export default function ComparisonPage() {
  return <div className={styles.page}>
    <div className={styles.pageGlow} aria-hidden="true" />
    <div className={styles.shell}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}><span /> YOUR NEEDS, SIDE BY SIDE</p>
          <h1>Compare the details.<br /><em>Keep the evidence close.</em></h1>
          <p className={styles.lede}>Review the terms that shape your health cover. Each difference should lead back to the policy wording that supports it.</p>
        </div>
        <Link className={styles.editLink} href="/intake"><Glyph name="compare" size={16} /> Edit my priorities <span aria-hidden="true">↗</span></Link>
      </header>
      <ReferenceWorkspace />
    </div>
  </div>;
}
