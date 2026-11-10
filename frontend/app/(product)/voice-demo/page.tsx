import type { Metadata } from "next";
import VoiceDemo from "@/components/product/VoiceDemo";

export const metadata: Metadata = {
  title: "Assurely voice guide prototype",
  description: "A private, synthetic no-audio prototype for the Assurely AI voice guide.",
};

export default function VoiceDemoPage() {
  return <VoiceDemo />;
}
