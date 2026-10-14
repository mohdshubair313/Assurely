import Image from "next/image";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import celestialStation from "@/public/images/Celestial Station Above the Clouds.png";
import HeroClouds from "./HeroClouds";
import styles from "./CelestialHero.module.css";

export default function HeroSection() {
  return (
    <section className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.art}>
        <Image src={celestialStation} alt="" preload sizes="100vw" className={styles.image} />
        <HeroClouds />
      </div>
      <div className={styles.constellation} aria-hidden="true"><span>✦</span><span>✦</span><span>✦</span><span>✦</span></div>
      <div className={styles.copy}>
        <p className={styles.eyebrow}><span /> A clearer way to explore health insurance</p>
        <h1 id="hero-title" className={styles.title}>Less guesswork.<br /><em>More peace of mind.</em></h1>
        <p className={styles.description}>Understand the fine print, explore the trade-offs,<br className={styles.desktopBreak} /> and find cover that fits your life.</p>
        <div className={styles.actions}>
          <Link className={styles.primary} href="/intake">Find my cover <Glyph name="arrow" size={18} /></Link>
          <Link className={styles.secondary} href="/#how-it-works">See how it works <span aria-hidden="true">↗</span></Link>
        </div>
        <p className={styles.caption}>Your needs. Your pace. No pressure to buy.</p>
      </div>
      <div className={styles.sceneNote} aria-hidden="true"><span /> A little clarity goes a long way.</div>
    </section>
  );
}
