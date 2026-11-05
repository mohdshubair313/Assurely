"use client";
import { SignOutButton } from "@clerk/nextjs";
import { Button, ButtonLabel } from "@/components/createui/button";
import { clerkConfigured } from "@/lib/auth-config";

export default function SignOutControl() {
  const button = <Button type={clerkConfigured ? "button" : "submit"} variant="neutral-light" appearance="ghost" size="md"><ButtonLabel>Sign out</ButtonLabel></Button>;
  return clerkConfigured ? <SignOutButton redirectUrl="/">{button}</SignOutButton>
    : <form action="/api/auth/sign-out" method="post">{button}</form>;
}
