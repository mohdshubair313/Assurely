import type { Citation } from "@/lib/api-client";

export default function EvidenceSources({ citation }: { citation: Citation }) {
  return <div>
    <small>Source: {citation.source} · Last verified: {citation.last_verified}</small>
    <details><summary>Source documents and conditions</summary>
      {([
        ["Policy fact", citation.references], ["Applicability", citation.applicability_evidence],
        ["Condition", citation.condition_evidence],
      ] as const).map(([label, references]) => references?.map((reference, index) => {
        let link: URL;
        try {
          link = new URL(reference.url);
          if (link.protocol !== "https:" || link.username || link.password) return null;
          link.hash = `page=${reference.pdf_page}`;
        } catch { return null; }
        return <p key={`${label}-${index}`}><a href={link.href} target="_blank" rel="noopener noreferrer">
          {label} · PDF page {reference.pdf_page} · {reference.clause}
        </a><br /><span>{reference.quote}</span></p>;
      }))}
    </details>
  </div>;
}
