"use client";

import { type ButtonHTMLAttributes, forwardRef } from "react";

/**
 * Button — design-system primitive.
 *
 * Variants:
 *   - primary: Harbor fill (#2C5F73) — deliberate, authoritative action color
 *   - secondary: Outlined with Harbor hover border
 *   - ghost: Text-only Harbor with subtle background hover
 *   - accent: Sky Blue fill (#5BA9D8) — secondary decorative accent
 *   - danger: Semantic Risk Clay fill (#A44A2F)
 *
 * Sizes: sm, md, lg.
 * Motion: 90ms press (scale 0.98), 140ms hover (design.md §5).
 */

type ButtonVariant = "primary" | "secondary" | "ghost" | "accent" | "danger";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-harbor text-white hover:bg-harbor-strong focus-visible:ring-harbor shadow-sm",
  secondary:
    "border border-line bg-surface text-ink hover:bg-surface-raised hover:border-harbor focus-visible:ring-harbor",
  ghost:
    "bg-transparent text-harbor hover:text-harbor-strong hover:bg-harbor-subtle focus-visible:ring-harbor",
  accent:
    "bg-sky text-white hover:bg-sky-strong focus-visible:ring-sky shadow-sm",
  danger:
    "bg-clay text-white hover:opacity-95 focus-visible:ring-clay shadow-sm",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3.5 py-1.5 text-xs gap-1.5",
  md: "px-5 py-2.5 text-sm gap-2",
  lg: "px-7 py-3 text-base gap-2.5",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = "primary", size = "md", className = "", children, ...props },
    ref
  ) => {
    return (
      <button
        ref={ref}
        className={[
          "inline-flex items-center justify-center",
          "font-body font-medium leading-tight",
          "rounded-input",
          "transition-theme",
          "active:scale-[0.98]",
          "disabled:opacity-50 disabled:pointer-events-none",
          "cursor-pointer",
          variantClasses[variant],
          sizeClasses[size],
          className,
        ].join(" ")}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;
