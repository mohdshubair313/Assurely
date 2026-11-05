import TopNav from "@/components/marketing/TopNav";
import { accessToken } from "@/lib/server-session";
import { redirect } from "next/navigation";
import AccountBoundary from "@/components/auth/AccountBoundary";
export const dynamic = "force-dynamic";
export default async function ProductLayout({ children }: { children: React.ReactNode }) {
  let token: string | undefined;
  try { token = await accessToken(); }
  catch { return <main className="reference-container"><h1>Account access is unavailable</h1><p>Authentication has not been configured or could not be verified. Please try again later.</p></main>; }
  if (!token) redirect("/sign-in");
  return <AccountBoundary><div className="reference-site product-site"><TopNav /><main>{children}</main></div></AccountBoundary>;
}
