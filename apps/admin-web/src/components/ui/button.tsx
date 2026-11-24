import clsx from "clsx";
import Link from "next/link";
import type { ComponentProps } from "react";

/**
 * Design system buttons:
 * - accent (lime): the single most important action on a screen;
 * - primary (forest): confirm;
 * - secondary (outlined), ghost (text), danger (outlined critical action).
 * Controls are at least 44 px tall; `lg` is the 60 px mobile button.
 */
export type ButtonVariant = "primary" | "accent" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] font-semibold transition-colors whitespace-nowrap disabled:cursor-not-allowed disabled:border-transparent disabled:bg-neutral-100 disabled:text-neutral-500 disabled:shadow-none";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover",
  accent: "bg-accent font-bold text-on-accent hover:bg-accent-hover",
  secondary: "border border-line-strong bg-surface text-primary hover:bg-neutral-50",
  danger: "border-[1.5px] border-danger-action bg-surface text-danger-action hover:bg-danger-soft",
  ghost: "text-primary hover:bg-neutral-100",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-[60px] rounded-[18px] px-6 text-lg",
};

export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
) {
  return clsx(base, variants[variant], sizes[size], className);
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <button type={type} className={buttonClasses(variant, size, className)} {...props} />;
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={buttonClasses(variant, size, className)} {...props} />;
}
