import type { Metadata } from "next";
import AuthForm from "@/components/auth/AuthForm";

export const metadata: Metadata = { title: "Create an account — Assurely", description: "A clearer starting point for your health insurance questions." };
export default function SignUpPage() { return <AuthForm key="sign-up" mode="sign-up" />; }
