"use client";
import { useEffect } from "react";
import { useUser } from "@clerk/nextjs";
import { clerkConfigured } from "@/lib/auth-config";

function SessionBoundary({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, user } = useUser();
  useEffect(() => {
    if (isLoaded && !isSignedIn) window.location.replace("/sign-in");
  }, [isLoaded, isSignedIn]);
  // Reset private client state on account change; backend remains authoritative.
  if (!isLoaded || !isSignedIn) return <p role="status">Checking account access…</p>;
  return <div key={user.id}>{children}</div>;
}

export default function AccountBoundary({ children }: { children: React.ReactNode }) {
  return clerkConfigured ? <SessionBoundary>{children}</SessionBoundary> : children;
}
