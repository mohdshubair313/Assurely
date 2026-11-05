"use client";
import Link from 'next/link';
import { Button, ButtonLabel } from '@/components/createui/button';
import { InlineAlert, InlineAlertContent, InlineAlertDescription } from '@/components/createui/inline-alert';
import styles from './AuthLayout.module.css';
import { SignIn, SignUp } from '@clerk/nextjs';
import { authMode, clerkConfigured } from '@/lib/auth-config';

export default function AuthForm({ mode, unavailable = false }: { mode: 'sign-in' | 'sign-up'; unavailable?: boolean }) {
  return <div className={styles.formContent}>
    <div className={styles.eyebrow}>YOUR NEXT CHAPTER</div>
    <h1 className={styles.title}>{mode === 'sign-up' ? 'A clearer picture.' : 'Welcome back.'}<br /><em>Let’s find clarity.</em></h1>
    <p className={styles.intro}>Use your connected account to return to private cases and reviewed reports.</p>
    <div className={styles.notice}><InlineAlert variant="info" appearance="soft" layout="horizontal">
      <InlineAlertContent><InlineAlertDescription className="line-clamp-none">{unavailable ? 'Sign-in could not be completed. Please try again or contact your administrator.' : 'Account access is handled by your identity provider.'}</InlineAlertDescription></InlineAlertContent>
    </InlineAlert></div>
    {clerkConfigured ? (mode === 'sign-in'
      ? <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" forceRedirectUrl="/workspace" />
      : <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" forceRedirectUrl="/intake" />)
      : authMode === 'legacy_oidc' ? <form action="/api/auth/sign-in" method="post">
      <Button type="submit" variant="primary" appearance="solid" size="xl" className="w-full"><ButtonLabel>Continue with your account</ButtonLabel></Button>
    </form> : <p role="status">Account access is awaiting secure provider configuration.</p>}
    <p className={styles.privacy}>Your account password stays with your identity provider.</p>
    <p className={styles.privacy}>Signing in does not grant consent to process health details, save profiles, record audio or share data with a voice vendor.</p>
    <div className={styles.previewPath}><p>Explore without signing in.</p><Link href="/how-it-works">See how Assurely works ↗</Link></div>
  </div>;
}
