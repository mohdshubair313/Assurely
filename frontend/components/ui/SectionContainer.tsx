import type { ReactNode } from "react";

/**
 * SectionContainer — max-width wrapper with grid support.
 *
 * Design.md §4: max content width 1240px, reading width 680px.
 * 12-col desktop, 6 tablet, 4 mobile grid.
 */

type ContentWidth = "full" | "content" | "reading";

export interface SectionContainerProps {
  children: ReactNode;
  width?: ContentWidth;
  className?: string;
  as?: "section" | "div" | "article" | "main";
  id?: string;
}

const widthClasses: Record<ContentWidth, string> = {
  full: "w-full",
  content: "w-full max-w-[1240px]",
  reading: "w-full max-w-[680px]",
};

export default function SectionContainer({
  children,
  width = "content",
  className = "",
  as: Tag = "section",
  id,
}: SectionContainerProps) {
  return (
    <Tag
      id={id}
      className={[
        "mx-auto px-5 sm:px-8 lg:px-12",
        widthClasses[width],
        className,
      ].join(" ")}
    >
      {children}
    </Tag>
  );
}
