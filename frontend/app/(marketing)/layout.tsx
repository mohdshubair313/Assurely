import TopNav from "@/components/marketing/TopNav";
import Footer from "@/components/marketing/Footer";
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <div className="reference-site"><TopNav /><main>{children}</main><Footer /></div>;
}
