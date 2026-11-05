"use client";
import Link from "next/link";
import { Button, ButtonLabel } from "@/components/createui/button";
import styles from "./workspace/workspace.module.css";
export default function ProductError({ retry }: { error: unknown; retry: () => void }) {
  return <section className={styles.page}><div className={styles.panel} role="alert"><h1>This page could not be opened.</h1>
    <p>Your last request may already have reached the service. Check your case status before submitting it again.</p>
    <div className={styles.actions}><Button variant="primary" appearance="outline" size="md" onClick={() => retry()}><ButtonLabel>Reload this page</ButtonLabel></Button><Link href="/workspace">Return to your case workspace</Link></div>
  </div></section>;
}
