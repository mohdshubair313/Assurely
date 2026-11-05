import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { authMode, clerkConfigured } from "@/lib/auth-config";

export const sessionCookie = "assurely_session";
export const transactionCookie = "assurely_login";
export const cookieOptions = {
  httpOnly: true, sameSite: "lax" as const, path: "/",
  secure: process.env.NODE_ENV === "production",
};

function key() {
  const value = process.env.SESSION_SECRET ?? "";
  const result = Buffer.from(value, "base64");
  if (result.length !== 32) throw new Error("Session configuration unavailable");
  return result;
}

export function appOrigin() {
  const url = new URL(process.env.APP_ORIGIN ?? "http://localhost:3000");
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash ||
      (url.protocol !== "https:" && !(process.env.NODE_ENV !== "production" &&
        url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) {
    throw new Error("Application origin unavailable");
  }
  return url.origin;
}

export function sameOrigin(request: Request) {
  return request.headers.get("origin") === appOrigin();
}

export function seal(value: Record<string, unknown>) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), iv);
  cipher.setAAD(Buffer.from("assurely-session-v1"));
  const data = Buffer.concat([cipher.update(JSON.stringify(value)), cipher.final()]);
  const result = Buffer.concat([iv, cipher.getAuthTag(), data]).toString("base64url");
  if (result.length > 3600) throw new Error("Session exceeds cookie capacity");
  return result;
}

export function unseal(value: string): Record<string, unknown> | null {
  try {
    if (value.length > 3600) return null;
    const bytes = Buffer.from(value, "base64url");
    const decipher = createDecipheriv("aes-256-gcm", key(), bytes.subarray(0, 12));
    decipher.setAAD(Buffer.from("assurely-session-v1"));
    decipher.setAuthTag(bytes.subarray(12, 28));
    const data = JSON.parse(Buffer.concat([
      decipher.update(bytes.subarray(28)), decipher.final(),
    ]).toString());
    return typeof data.exp === "number" && data.exp > Date.now() / 1000 ? data : null;
  } catch { return null; }
}

export async function accessToken() {
  if (authMode === "clerk") {
    if (!clerkConfigured || !process.env.CLERK_SECRET_KEY) throw new Error("Account access is unavailable");
    const { auth } = await import("@clerk/nextjs/server");
    const session = await auth({ acceptsToken: "session_token" });
    if (!session.isAuthenticated) return undefined;
    return (await session.getToken()) ?? undefined;
  }
  if (authMode !== "legacy_oidc") throw new Error("Account access is unavailable");
  const value = (await cookies()).get(sessionCookie)?.value;
  const data = value ? unseal(value) : null;
  return typeof data?.token === "string" ? data.token : undefined;
}
