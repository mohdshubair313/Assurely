import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import HouseScene from "./HouseScene";
export default function HeroSection() {
  return <section className="reference-hero">
    <div className="reference-container hero-grid">
      <div className="hero-copy">
        <h1>Insurance shouldn’t<br className="wide-break" /> make you guess<br className="wide-break" /> what your family is<br className="wide-break" /> <em>covered</em> for.</h1>
        <p>Tell us what matters. We translate policy terms, compare the real-world trade-offs, and show exactly what to ask before you decide.</p>
        <div className="hero-actions"><Link className="pill-button" href="/intake">Find my cover <Glyph name="arrow" size={15} /></Link><Link className="pill-button secondary" href="/#how-it-works"><span className="play-icon">▷</span> See how comparisons work</Link></div>
        <p className="hero-caption">Your needs. A clearer picture. No pressure to buy.</p>
        <div className="hero-assurances"><span><Glyph name="chat" size={18} />Ask in plain<br />language</span><span><Glyph name="file" size={18} />Understand<br />the fine print</span><span><Glyph name="compare" size={18} />See the<br />trade-offs</span></div>
      </div>
      <div className="hero-art-wrap">
        <HouseScene />
      </div>
    </div>
  </section>;
}
