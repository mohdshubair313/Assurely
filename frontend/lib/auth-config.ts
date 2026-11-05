// Explicit rollout switch. Never infer an identity provider from a cookie/token.
export const authMode = process.env.NEXT_PUBLIC_AUTH_PROVIDER ?? "clerk";
export const clerkConfigured = authMode === "clerk" && Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
