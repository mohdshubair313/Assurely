import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest, type NextFetchEvent } from "next/server";
import { authMode, clerkConfigured } from "@/lib/auth-config";

const clerk = clerkMiddleware({
  authorizedParties: [process.env.APP_ORIGIN ?? "http://localhost:3000"],
});

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  // Keyless mode must not provision an unclaimed provider application.
  if (authMode === "legacy_oidc" || !clerkConfigured || !process.env.CLERK_SECRET_KEY) {
    return NextResponse.next();
  }
  // This establishes SDK context. Each private resource additionally checks auth.
  return clerk(request, event);
}

export const config = {
  matcher: ["/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)", "/(api|trpc)(.*)"],
};
