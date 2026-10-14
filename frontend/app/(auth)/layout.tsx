import Link from "next/link";
import { AuthSlideshow } from "@/components/auth/AuthSlideshow";
import Glyph from "@/components/ui/Glyph";
import ThemeToggle from "@/components/ui/ThemeToggle";
import styles from "@/components/auth/AuthLayout.module.css";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <main className={styles.shell} data-auth-shell>
    <section className={styles.visual} aria-label="A clearer way to explore your cover">
      <Link href="/" className={styles.brand} aria-label="Assurely home"><span><Glyph name="shield" size={23} /></span>Assurely<span className={styles.brandStar} aria-hidden="true">✦</span></Link>
      <AuthSlideshow />
    </section>
    <div className={styles.divider} data-auth-divider aria-hidden="true" />
    <section className={styles.panel} aria-label="Account access">
      <div className={styles.panelHeader}><Link href="/" className={styles.homeLink}><span aria-hidden="true">←</span> Back to home</Link><ThemeToggle /></div>
      <div className={styles.formCenter}>{children}</div>
      <footer className={styles.footer}><span>Clarity before commitment.</span><span>© {new Date().getFullYear()} Assurely</span></footer>
    </section>
  </main>;
}
