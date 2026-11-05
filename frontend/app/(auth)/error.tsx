"use client";
import { Button, ButtonLabel } from "@/components/createui/button";

export default function AccountError({ retry }: { error: Error; retry: () => void }) {
  return <section role="alert"><h1>Account access is unavailable</h1>
    <p>Please retry. Contact the operator if secure sign-in remains unavailable.</p>
    <Button type="button" variant="primary" onClick={retry}><ButtonLabel>Try again</ButtonLabel></Button>
  </section>;
}
