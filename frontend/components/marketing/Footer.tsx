import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import styles from "./Footer.module.css";

export default function Footer() {
  return <footer className={styles.footer}><div className={styles.footerMain}><div><Link href="/" className={styles.brand}><Glyph size={27} />Assurely</Link><p>Understand your cover<br />before life asks for it.</p></div><nav aria-label="Footer navigation"><Link href="/#how-it-works">The journey</Link><Link href="/#policy-decoder">Policy decoder</Link><Link href="/#trust">The evidence</Link><Link href="/#faq">Your questions</Link></nav><div className={styles.footerNote}><span className={styles.star} aria-hidden="true">✦</span><span>A calmer place<br />to begin.</span></div></div><div className={styles.footerBottom}><span>Health insurance · India</span><span>Design preview · Policy examples are unverified</span><Link href="/intake">Start with your needs ↗</Link></div></footer>;
}
