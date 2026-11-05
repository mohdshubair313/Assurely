import type { Metadata } from "next";
import AuthForm from "@/components/auth/AuthForm";

export const metadata: Metadata = { title: "Sign in — Assurely", description: "Return to a clearer view of your health insurance questions." };
export default async function SignInPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const query = await searchParams;
  return <AuthForm key="sign-in" mode="sign-in" unavailable={Boolean(query.error)} />;
}
