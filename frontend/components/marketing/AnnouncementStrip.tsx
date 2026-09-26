import Badge from "@/components/ui/Badge";

/**
 * AnnouncementStrip — top-of-page banner.
 *
 * design.md §8.1 section 1:
 * "Health insurance guidance, explained in plain language."
 * + small "Verified policy terms" evidence indicator.
 */

export default function AnnouncementStrip() {
  return (
    <div className="bg-harbor text-white text-sm py-2 px-4">
      <div className="max-w-[1240px] mx-auto flex items-center justify-center gap-3 flex-wrap">
        <span className="font-body">
          Health insurance guidance, explained in plain language.
        </span>
        <Badge variant="verified" className="text-teal-subtle bg-teal border-teal text-[10px]">
          <svg
            className="w-3 h-3"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
            />
          </svg>
          Verified policy terms
        </Badge>
      </div>
    </div>
  );
}
