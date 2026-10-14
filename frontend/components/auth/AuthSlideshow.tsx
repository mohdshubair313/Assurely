"use client";

import Image from "next/image";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { RiPauseLine, RiPlayFill } from "@create-ui/assets/icons";
import { Button } from "@/components/createui/button";
import styles from "./AuthSlideshow.module.css";

const slides = [
  {
    chapter: "The happy beginning",
    title: "Signed with a smile.",
    detail: "The cover sounds right. The paperwork is signed, while the conditions go unread.",
    mobileDetail: "The conditions go unread.",
    src: "/images/auth/signing.png",
    caption: "01 / THE SIGNATURE",
    position: "51% 40%",
  },
  {
    chapter: "Month after month",
    title: "Another premium paid.",
    detail: "A debit notification arrives. Payments continue, and everything feels reassuring.",
    mobileDetail: "A debit. A reassuring notification.",
    src: "/images/auth/premium-payment.png",
    caption: "02 / THE PAYMENT",
    position: "57% 35%",
  },
  {
    chapter: "When the details matter",
    title: "An exclusion. A surprise.",
    detail: "In this illustrated case, an exclusion blocks the claim. Ask about the conditions before you commit.",
    mobileDetail: "An exclusion blocks the claim.",
    src: "/images/auth/claim-rejected.png",
    caption: "03 / THE CLAIM",
    position: "55% 40%",
  },
] as const;

/** An independent carousel: slide changes never rerender the adjacent form. */
export function AuthSlideshow({ className = "" }: { className?: string }) {
  const rootRef = useRef<HTMLElement>(null);
  const selectors = useRef<Array<HTMLButtonElement | null>>([]);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(true);
  const [inView, setInView] = useState(false);
  // Static first frame on server and client; motion starts after preference detection.
  const [reduced, setReduced] = useState(true);
  const [instant, setInstant] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const playing = !paused && !hovered && !focused && visible && inView && !reduced;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReduced(media.matches);
    const syncVisibility = () => setVisible(!document.hidden);
    syncMotion();
    syncVisibility();
    media.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting && entry.intersectionRatio >= 0.15), {
      threshold: 0.15,
    });
    if (rootRef.current) observer.observe(rootRef.current);
    return () => {
      media.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!playing) return;
    // A fresh reading interval after every selection/resume; no per-frame React work.
    const timer = window.setTimeout(() => {
      setInstant(false);
      setActive((index) => (index + 1) % slides.length);
    }, 6000);
    return () => window.clearTimeout(timer);
  }, [active, playing]);

  const select = (index: number, keyboard: boolean) => {
    setInstant(keyboard);
    setActive(index);
    setAnnouncement(`Slide ${index + 1} of ${slides.length}: ${slides[index].title}`);
  };

  const onSelectorKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let index: number | undefined;
    if (event.key === "ArrowRight") index = (active + 1) % slides.length;
    if (event.key === "ArrowLeft") index = (active - 1 + slides.length) % slides.length;
    if (event.key === "Home") index = 0;
    if (event.key === "End") index = slides.length - 1;
    if (index === undefined) return;
    event.preventDefault();
    select(index, true);
    selectors.current[index]?.focus();
  };

  return (
    <aside
      ref={rootRef}
      className={`${styles.panel} ${className}`}
      aria-label="Explore insurance clarity with Assurely"
      aria-roledescription="carousel"
      data-auth-slideshow=""
      data-active-slide={active + 1}
      data-playing={playing}
      data-instant={instant || reduced}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") setHovered(true);
      }}
      onPointerLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
      }}
    >
      <div className={styles.images} data-auth-photo aria-hidden="true">
        {slides.map((slide, index) => (
          <div className={styles.imageLayer} data-active={index === active} key={slide.src}>
            <Image
              src={slide.src}
              alt=""
              fill
              sizes="(max-width: 800px) 160vw, (max-width: 1100px) 150vw, 110vw"
              loading="eager"
              className={styles.image}
              style={{ objectPosition: slide.position }}
            />
          </div>
        ))}
      </div>
      <div className={styles.scrim} aria-hidden="true" />
      <div className={styles.frame} aria-hidden="true" />
      <div className={styles.sceneCaption} aria-hidden="true">
        <span className={styles.captionMark} />
        {slides[active].caption}
      </div>

      <div className={styles.editorial}>
        <div className={styles.copyStack}>
          {slides.map((slide, index) => (
            <div
              className={styles.copy}
              key={slide.title}
              data-active={index === active}
              aria-hidden={index !== active}
              role="group"
              aria-roledescription="slide"
              aria-label={`${index + 1} of ${slides.length}`}
            >
              <p className={styles.eyebrow}><span />{slide.chapter}</p>
              <h2>{slide.title}</h2>
              <p className={`${styles.detail} ${styles.desktopDetail}`}>{slide.detail}</p>
              <p className={`${styles.detail} ${styles.mobileDetail}`}>{slide.mobileDetail}</p>
            </div>
          ))}
        </div>

        <div className={styles.controls}>
          <div
            className={styles.selectors}
            role="group"
            aria-label="Choose a slideshow slide"
            onKeyDown={onSelectorKeyDown}
          >
            {slides.map((slide, index) => (
              <Button
                key={slide.title}
                ref={(element) => { selectors.current[index] = element; }}
                type="button"
                iconOnly
                variant="inverse-solid"
                appearance="ghost"
                size="xl"
                shape="pill"
                className={styles.selector}
                aria-label={`Slide ${index + 1}: ${slide.title}`}
                aria-pressed={index === active}
                onClick={(event) => select(index, event.detail === 0)}
              >
                <span className={styles.selectorMark} aria-hidden="true" />
              </Button>
            ))}
          </div>
          <span className={styles.count} aria-hidden="true">0{active + 1}<span>/</span>03</span>
          <Button
            type="button"
            iconOnly
            variant="inverse-solid"
            appearance="outline"
            size="xl"
            shape="pill"
            className={styles.playButton}
            disabled={reduced}
            aria-label={reduced ? "Autoplay disabled for reduced motion" : paused ? "Play slideshow" : "Pause slideshow"}
            aria-pressed={paused || reduced}
            onClick={() => {
              setPaused((value) => !value);
              setAnnouncement(paused ? "Slideshow autoplay enabled" : "Slideshow autoplay paused");
            }}
          >
            {paused || reduced ? <RiPlayFill /> : <RiPauseLine />}
          </Button>
        </div>
        <p className={styles.motionNote} data-auth-story-note>Illustrated scenario · not a policy assessment<span className="sr-only">. Payment amounts, dates and claim details shown are fictional.</span></p>
      </div>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</span>
    </aside>
  );
}
