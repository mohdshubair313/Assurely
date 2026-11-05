import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import * as oidc from "openid-client";
import { authMode } from "@/lib/auth-config";
import {
  accessToken, appOrigin, cookieOptions, sameOrigin, seal, sessionCookie,
  transactionCookie, unseal,
} from "@/lib/server-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function provider() {
  const issuer = new URL(process.env.OIDC_ISSUER ?? "");
  const client = process.env.OIDC_CLIENT_ID;
  if (!client || issuer.protocol !== "https:" || issuer.username || issuer.password) {
    throw new Error("Account access is unavailable");
  }
  return oidc.discovery(issuer, client, process.env.OIDC_CLIENT_SECRET);
}

const unavailable = () => {
  try { return NextResponse.redirect(new URL("/sign-in?error=account", appOrigin()), 303); }
  catch { return NextResponse.json({ detail: "Account access is unavailable." }, { status: 503 }); }
};

export async function POST(request: Request, context: { params: Promise<{ action: string }> }) {
  if (authMode !== "legacy_oidc") return new Response(null, { status: 404 });
  try {
    if (!sameOrigin(request)) return new Response(null, { status: 403 });
    const { action } = await context.params;
    const jar = await cookies();
    if (action === "sign-out") {
      jar.set(sessionCookie, "", { ...cookieOptions, maxAge: 0 });
      jar.set(transactionCookie, "", { ...cookieOptions, maxAge: 0 });
      return NextResponse.redirect(new URL("/sign-in", appOrigin()), 303);
    }
    if (action !== "sign-in") return new Response(null, { status: 404 });
    const config = await provider();
    const verifier = oidc.randomPKCECodeVerifier();
    const state = oidc.randomState();
    const nonce = oidc.randomNonce();
    const redirect = oidc.buildAuthorizationUrl(config, {
      redirect_uri: `${appOrigin()}/api/auth/callback`,
      scope: process.env.OIDC_SCOPE ?? "openid",
      code_challenge: await oidc.calculatePKCECodeChallenge(verifier),
      code_challenge_method: "S256", state, nonce,
      ...(process.env.OIDC_RESOURCE ? { resource: process.env.OIDC_RESOURCE } : {}),
      ...(process.env.OIDC_AUDIENCE ? { audience: process.env.OIDC_AUDIENCE } : {}),
    });
    jar.set(transactionCookie, seal({ verifier, state, nonce, exp: Date.now() / 1000 + 600 }),
      { ...cookieOptions, maxAge: 600 });
    return NextResponse.redirect(redirect, 303);
  } catch { return unavailable(); }
}

export async function GET(request: Request, context: { params: Promise<{ action: string }> }) {
  if (authMode !== "legacy_oidc") return new Response(null, { status: 404 });
  const { action } = await context.params;
  if (action === "session") {
    return NextResponse.json({ authenticated: Boolean(await accessToken()) },
      { headers: { "Cache-Control": "no-store" } });
  }
  if (action !== "callback") return new Response(null, { status: 404 });
  const jar = await cookies();
  try {
    const value = jar.get(transactionCookie)?.value;
    jar.set(transactionCookie, "", { ...cookieOptions, maxAge: 0 });
    const data = value ? unseal(value) : null;
    if (!data || ![data.verifier, data.state, data.nonce].every(v => typeof v === "string")) {
      throw new Error("Invalid transaction");
    }
    const url = new URL(request.url);
    if (url.origin !== appOrigin()) throw new Error("Invalid callback origin");
    const tokens = await oidc.authorizationCodeGrant(await provider(), url, {
      pkceCodeVerifier: data.verifier as string, expectedState: data.state as string,
      expectedNonce: data.nonce as string, idTokenExpected: true,
    });
    if (tokens.token_type.toLowerCase() !== "bearer") throw new Error("Unsupported token type");
    const seconds = Math.min(tokens.expires_in ?? 300, 900);
    if (!Number.isFinite(seconds) || seconds <= 0) throw new Error("Expired token");
    jar.set(sessionCookie, seal({ token: tokens.access_token, exp: Date.now() / 1000 + seconds }),
      { ...cookieOptions, maxAge: Math.floor(seconds) });
    return NextResponse.redirect(new URL("/workspace", appOrigin()), 303);
  } catch {
    jar.set(sessionCookie, "", { ...cookieOptions, maxAge: 0 });
    return NextResponse.redirect(new URL("/sign-in?error=account", appOrigin()), 303);
  }
}
