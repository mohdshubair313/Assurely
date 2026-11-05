import type { Metadata } from "next";
import CaseReportView from "@/components/product/CaseReportView";

export const metadata: Metadata = {
  title: "Your health policy comparison | Assurely",
  description: "Compare health policy details side by side, with the source and verification status clearly shown.",
};

export default function ComparisonPage() {
  return <CaseReportView mode="comparison" />;
}
