import TopNav from "@/components/marketing/TopNav";
export default function ProductLayout({ children }: { children: React.ReactNode }) {
  return <div className="reference-site product-site"><TopNav /><main>{children}</main></div>;
}
