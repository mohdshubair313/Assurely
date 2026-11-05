import type { Metadata } from "next";
import CaseReportView from "@/components/product/CaseReportView";
export const metadata: Metadata = { title: "Case review status | Assurely", description: "Check your actual health-cover case status and reviewed report availability." };
export default function HandoffPage() { return <CaseReportView mode="handoff" />; }
