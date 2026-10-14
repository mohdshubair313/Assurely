"use client";

import { useState } from "react";
import { RiPauseLine, RiPlayFill } from "@create-ui/assets/icons";
import { Button } from "@/components/createui/button";
import { CloudShader } from "@/components/ui/cloud-shader";
import styles from "./CelestialHero.module.css";

export default function HeroClouds() {
  const [paused, setPaused] = useState(false);
  return <div className={styles.cloudScene}>
    <CloudShader className={styles.cloudField} transparent paused={paused} speed={0.28} count={5} cloudColor="#ffebc9" skyTopColor="#1d4c91" skyBottomColor="#638bb2" />
    <Button type="button" iconOnly variant="inverse-solid" appearance="outline" size="xl" shape="pill" className={styles.cloudControl} aria-label={paused ? "Play cloud animation" : "Pause cloud animation"} aria-pressed={paused} onClick={() => setPaused(value => !value)}>
      {paused ? <RiPlayFill /> : <RiPauseLine />}
    </Button>
  </div>;
}
