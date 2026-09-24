import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatUsd(amount: number | undefined | null): string {
  if (amount === undefined || amount === null) return "not recorded";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number | undefined | null, decimals = 1): string {
  if (value === undefined || value === null) return "not recorded";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatProbability(value: number | undefined | null): string {
  if (value === undefined || value === null) return "not recorded";
  return value.toFixed(4);
}
