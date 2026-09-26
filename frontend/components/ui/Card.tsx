import type { ReactNode } from "react";

/**
 * Card — elevated container with surface/raised variants.
 *
 * Radius: 20px (design.md §4). Shadows: broad, low-opacity blue-gray.
 * Enter animation: 220–280ms (design.md §5).
 */

type CardVariant = "surface" | "raised";

export interface CardProps {
  children: ReactNode;
  variant?: CardVariant;
  hoverable?: boolean;
  className?: string;
  as?: "div" | "article" | "section";
}

const variantClasses: Record<CardVariant, string> = {
  surface: "bg-surface shadow-card",
  raised: "bg-surface-raised shadow-elevated",
};

export default function Card({
  children,
  variant = "surface",
  hoverable = false,
  className = "",
  as: Tag = "div",
}: CardProps) {
  return (
    <Tag
      className={[
        "rounded-card border border-line",
        "transition-card",
        variantClasses[variant],
        hoverable && "hover:shadow-card-hover hover:-translate-y-0.5 cursor-pointer",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </Tag>
  );
}
