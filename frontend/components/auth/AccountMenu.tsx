"use client";
import Link from "next/link";
import { useUser, UserButton } from "@clerk/nextjs";
import { clerkConfigured } from "@/lib/auth-config";

function ClerkAccount({ className }: { className?: string }) {
  const { isLoaded, isSignedIn } = useUser();
  if (!isLoaded) return <span role="status">Loading account…</span>;
  return isSignedIn ? <UserButton userProfileMode="modal" />
    : <Link href="/sign-in" className={className}>Sign in</Link>;
}

export default function AccountMenu({ className }: { className?: string }) {
  return clerkConfigured ? <ClerkAccount className={className} />
    : <Link href="/sign-in" className={className}>Sign in</Link>;
}
