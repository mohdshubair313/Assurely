import type { Metadata } from "next";
import { DM_Serif_Display, IBM_Plex_Sans, IBM_Plex_Mono, Caveat } from "next/font/google";
import "./globals.css";

/**
 * Root layout — design.md §4 typography + theme support.
 *
 * Font System:
 *   DM Serif Display → --font-dm-serif → font-display (strictly hero headline)
 *   IBM Plex Sans    → --font-ibm-plex-sans → font-body (body/UI with multilingual/Devanagari support)
 *   IBM Plex Mono    → --font-ibm-plex-mono → font-mono (actuarial data, hashes, UINs)
 *   Caveat           → --font-caveat → font-handwritten (tactile case-file margin notes)
 */

const dmSerifDisplay = DM_Serif_Display({
  weight: "400",
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-dm-serif",
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin", "latin-ext"],
  variable: "--font-ibm-plex-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

const caveat = Caveat({
  weight: ["400", "600", "700"],
  subsets: ["latin"],
  variable: "--font-caveat",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Assurely — Understand your cover before life asks for it",
  description:
    "Tell us what matters. We translate policy terms, compare the trade-offs, and show exactly what to ask before you decide.",
  keywords: [
    "health insurance",
    "insurance comparison",
    "policy terms",
    "insurance advisor",
    "India",
    "IRDAI",
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${dmSerifDisplay.variable} ${ibmPlexSans.variable} ${ibmPlexMono.variable} ${caveat.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col font-body bg-canvas text-ink">
        <script dangerouslySetInnerHTML={{ __html: `try{document.documentElement.dataset.theme=localStorage.getItem('assurely-theme')==='dark'?'dark':'light'}catch{document.documentElement.dataset.theme='light'}` }} />
        {children}
      </body>
    </html>
  );
}
