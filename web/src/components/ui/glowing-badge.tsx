"use client";

import { type HTMLAttributes } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export type GlowingBadgeVariant =
  | "default"
  | "fraud"
  | "legitimate"
  | "uncertain"
  | "d9"
  | "live"
  | "recorded"
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral";

export interface GlowingBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: GlowingBadgeVariant;
  pulse?: boolean;
  dot?: boolean;
}

const variantStyles: Record<
  GlowingBadgeVariant,
  { badge: string; glow: string; dot: string }
> = {
  fraud: {
    badge: "bg-[#FF0080]/15 text-[#FF0080] border border-[#FF0080]/40 shadow-[0_0_12px_rgba(255,0,128,0.25)]",
    glow: "bg-[#FF0080]/30",
    dot: "bg-[#FF0080]",
  },
  legitimate: {
    badge: "bg-[#062C1B] text-[#8EB89B] border border-[#0B6839] shadow-[0_0_12px_rgba(14,184,155,0.15)]",
    glow: "bg-[#8EB89B]/30",
    dot: "bg-[#8EB89B]",
  },
  uncertain: {
    badge: "bg-[#F4C93B]/15 text-[#F4C93B] border border-[#F4C93B]/40 shadow-[0_0_12px_rgba(244,201,59,0.2)]",
    glow: "bg-[#F4C93B]/30",
    dot: "bg-[#F4C93B]",
  },
  d9: {
    badge: "bg-[#FEE101]/15 text-[#FEE101] border border-[#EDD723]/60 shadow-[0_0_12px_rgba(254,225,1,0.2)] font-mono text-[11px]",
    glow: "bg-[#FEE101]/30",
    dot: "bg-[#FEE101]",
  },
  live: {
    badge: "bg-[#0B6839]/30 text-[#8EB89B] border border-[#0B6839]",
    glow: "bg-[#0B6839]/40",
    dot: "bg-[#8EB89B]",
  },
  recorded: {
    badge: "bg-[#041F13] text-[#F4C93B] border border-[#F4C93B]/30",
    glow: "bg-[#F4C93B]/20",
    dot: "bg-[#F4C93B]",
  },
  default: {
    badge: "bg-forest-deep text-cream border border-forest-deep",
    glow: "bg-sage/20",
    dot: "bg-cream",
  },
  neutral: {
    badge: "bg-forest-deep text-sage border border-green-jungle/40",
    glow: "bg-sage/20",
    dot: "bg-sage",
  },
  success: {
    badge: "bg-emerald-950 text-emerald-300 border border-emerald-700",
    glow: "bg-emerald-500/30",
    dot: "bg-emerald-400",
  },
  warning: {
    badge: "bg-amber-950 text-amber-300 border border-amber-700",
    glow: "bg-amber-500/30",
    dot: "bg-amber-400",
  },
  error: {
    badge: "bg-rose-950 text-rose-300 border border-rose-700",
    glow: "bg-rose-500/30",
    dot: "bg-rose-400",
  },
  info: {
    badge: "bg-sky-950 text-sky-300 border border-sky-700",
    glow: "bg-sky-500/30",
    dot: "bg-sky-400",
  },
};

export function GlowingBadge({
  variant = "default",
  pulse = true,
  dot = true,
  children,
  className,
  ...props
}: GlowingBadgeProps) {
  const styles = variantStyles[variant] || variantStyles.default;

  return (
    <span className="relative inline-flex items-center">
      <span
        className={cn(
          "absolute inset-0 rounded-full blur-md opacity-50",
          styles.glow
        )}
      />
      <span
        className={cn(
          "relative inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide uppercase",
          styles.badge,
          className
        )}
        {...props}
      >
        {dot && (
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            {pulse && (
              <motion.span
                className={cn(
                  "absolute inline-flex h-full w-full rounded-full opacity-75",
                  styles.dot
                )}
                animate={{ scale: [1, 2.4, 1], opacity: [0.75, 0, 0.75] }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
            )}
            <span
              className={cn(
                "relative inline-flex h-1.5 w-1.5 rounded-full",
                styles.dot
              )}
            />
          </span>
        )}
        {children}
      </span>
    </span>
  );
}

export default GlowingBadge;
