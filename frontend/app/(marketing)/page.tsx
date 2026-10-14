import type { Metadata } from "next";
import HeroSection from "@/components/marketing/HeroSection";
import LandingExperience from "@/components/marketing/LandingExperience";

export const metadata: Metadata = { title: "Assurely — Insurance shouldn’t make you guess" };

export default function LandingPage() {
  return <><HeroSection /><LandingExperience /></>;
}
