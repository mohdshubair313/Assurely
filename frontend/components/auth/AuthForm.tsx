"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, ButtonLabel } from "@/components/createui/button";
import { Badge } from "@/components/createui/badge";
import { Field, FieldLabel, FieldError } from "@/components/createui/field";
import { Input, InputProvider, InputShell, InputAffix } from "@/components/createui/input";
import { InlineAlert, InlineAlertIcon, InlineAlertContent, InlineAlertHeading, InlineAlertDescription } from "@/components/createui/inline-alert";
import Glyph from "@/components/ui/Glyph";
import styles from "./AuthLayout.module.css";

type Mode = "sign-in" | "sign-up";
type FieldKey = "name" | "email" | "password" | "confirm";
type Values = Record<FieldKey, string>;
const labels: Record<FieldKey, string> = { name: "Full name", email: "Email address", password: "Password", confirm: "Confirm password" };

function validate(key: FieldKey, values: Values, signup: boolean) {
  if (key === "name" && !values.name.trim()) return "Enter your name.";
  if (key === "email") {
    if (!values.email.trim()) return "Enter your email address.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) return "Enter a valid email address.";
  }
  if (key === "password") {
    if (!values.password) return "Enter your password.";
    if (signup && values.password.length < 8) return "Use at least 8 characters for this preview.";
  }
  if (key === "confirm") {
    if (!values.confirm) return "Confirm your password.";
    if (values.confirm !== values.password) return "Passwords do not match.";
  }
  return "";
}

function Eye({ hidden }: { hidden: boolean }) {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" /><circle cx="12" cy="12" r="3" />{hidden && <path d="m4 20 16-16" />}</svg>;
}

/** UI preview only: the app verifies external JWTs but has no account provider. */
export default function AuthForm({ mode }: { mode: Mode }) {
  const signup = mode === "sign-up";
  const [values, setValues] = useState<Values>({ name: "", email: "", password: "", confirm: "" });
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [visible, setVisible] = useState({ password: false, confirm: false });
  const keys: FieldKey[] = signup ? ["name", "email", "password", "confirm"] : ["email", "password"];
  return <div className={styles.formContent} data-auth-mode={mode}>
    <div className={styles.eyebrow}><span /> YOUR NEXT CHAPTER <Badge variant="neutral" appearance="outline" size="xs" shape="pill">Preview</Badge></div>
    <h1 className={styles.title}>{signup ? <>A clearer picture.<br /><em>Starts with you.</em></> : <>Welcome back.<br /><em>Let’s find clarity.</em></>}</h1>
    <p className={styles.intro}>{signup ? "A place for your questions, your policy details, and the evidence behind them." : "Return to your questions and the details that matter to you."}</p>
    <div className={styles.notice} data-auth-notice><InlineAlert variant="neutral" appearance="default" layout="horizontal" role="status"><InlineAlertIcon><Glyph name="lock" size={19} /></InlineAlertIcon><InlineAlertContent><InlineAlertHeading><InlineAlertDescription className="line-clamp-none">Account access isn’t connected yet. This form is a preview; entries aren’t submitted.</InlineAlertDescription></InlineAlertHeading></InlineAlertContent></InlineAlert></div>
    <form noValidate className={styles.form} onSubmit={event => {
      event.preventDefault();
      setTouched(Object.fromEntries(keys.map(key => [key, true])));
    }}>
      {keys.map(key => {
        const error = touched[key] ? validate(key, values, signup) : "";
        const passwordField = key === "password" || key === "confirm";
        const id = `auth-${key}`;
        const input = <Input id={id} name={key} type={passwordField ? (visible[key] ? "text" : "password") : key === "email" ? "email" : "text"} value={values[key]} onChange={event => setValues(previous => ({ ...previous, [key]: event.target.value }))} onBlur={() => setTouched(previous => ({ ...previous, [key]: true }))} autoComplete={key === "name" ? "name" : key === "email" ? "email" : signup ? "new-password" : "current-password"} autoCapitalize={key === "name" ? "words" : "none"} spellCheck={false} inputMode={key === "email" ? "email" : undefined} required maxLength={key === "name" ? 120 : key === "email" ? 254 : undefined} minLength={signup && key === "password" ? 8 : undefined} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : key === "password" && signup ? "password-guidance" : undefined} placeholder={key === "name" ? "Your full name" : key === "email" ? "you@example.com" : key === "confirm" ? "Repeat password" : signup ? "Choose password" : "Enter your password"} />;
        return <Field key={key} size="sm" invalid={!!error} className={styles.field}><FieldLabel htmlFor={id}>{labels[key]}</FieldLabel>{passwordField ? <InputProvider><InputShell>{input}<InputAffix><Button type="button" variant="neutral-light" appearance="ghost" size="md" iconOnly className="min-h-11 min-w-11" aria-label={key === "confirm" ? (visible.confirm ? "Hide confirmation password" : "Show confirmation password") : visible.password ? "Hide password" : "Show password"} aria-pressed={visible[key]} onClick={() => setVisible(previous => ({ ...previous, [key]: !previous[key] }))}><Eye hidden={visible[key]} /></Button></InputAffix></InputShell></InputProvider> : input}{error && <FieldError id={`${id}-error`}>{error}</FieldError>}{signup && key === "password" && !error && <p id="password-guidance" className={styles.fieldHelp}>8+ characters for this preview.</p>}</Field>;
      })}
      <Button type="submit" variant="primary" appearance="solid" size="xl" shape="rounded" className="w-full" disabled aria-describedby="auth-unavailable"><ButtonLabel>{signup ? "Create account" : "Sign in"}</ButtonLabel><Glyph name="arrow" size={18} /></Button>
      <p id="auth-unavailable" className={styles.submitHelp}>Available when account access is connected.</p>
    </form>
    <p className={styles.switch}>{signup ? "Already have an account?" : "New to Assurely?"} <Link href={signup ? "/sign-in" : "/sign-up"}>{signup ? "Sign in" : "Create an account"} <span aria-hidden="true">↗</span></Link></p>
    <div className={styles.previewPath}><span className={styles.previewRule} /><p>No account needed to take a look.</p><Button asChild variant="primary" appearance="ghost" size="md" shape="pill"><Link href="/intake" data-auth-preview><ButtonLabel>Explore the preview</ButtonLabel><Glyph name="arrow" size={16} /></Link></Button></div>
    <p className={styles.privacy}><Glyph name="lock" size={14} />Preview entries stay on this page and aren’t submitted.</p>
  </div>;
}
