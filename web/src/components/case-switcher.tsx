"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Home, ChevronDown, Sparkles } from "lucide-react";
import GlowingBadge from "@/components/ui/glowing-badge";

export interface CaseSwitcherItem {
  id: string;
  verdict: string;
  isBonus?: boolean;
}

interface CaseSwitcherProps {
  currentId: string;
  cases: CaseSwitcherItem[];
}

export function CaseSwitcher({ currentId, cases }: CaseSwitcherProps) {
  const router = useRouter();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const currentIndex = cases.findIndex((c) => c.id === currentId);
  const prevCase = currentIndex > 0 ? cases[currentIndex - 1] : cases[cases.length - 1];
  const nextCase = currentIndex < cases.length - 1 ? cases[currentIndex + 1] : cases[0];
  const currentItem = cases[currentIndex] || { id: currentId, verdict: "not recorded" };

  return (
    <div className="sticky top-0 z-40 w-full bg-[#041F13]/90 backdrop-blur-md border-b border-[#F4C93B]/20 px-4 sm:px-8 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Left: Home + Prev/Next Controls */}
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#F4C93B]/20 bg-forest/50 text-[#F4C93B] hover:text-[#FEE101] hover:border-[#F4C93B]/40 font-mono text-xs transition-colors"
          >
            <Home className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Overview</span>
          </Link>

          <div className="flex items-center gap-1">
            <Link
              href={`/case/${prevCase.id}/`}
              title={`Previous: ${prevCase.id}`}
              className="p-1.5 rounded-lg border border-[#F4C93B]/20 bg-forest/50 text-cream hover:text-[#F4C93B] hover:border-[#F4C93B]/40 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </Link>

            <Link
              href={`/case/${nextCase.id}/`}
              title={`Next: ${nextCase.id}`}
              className="p-1.5 rounded-lg border border-[#F4C93B]/20 bg-forest/50 text-cream hover:text-[#F4C93B] hover:border-[#F4C93B]/40 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Center: Current Case Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl border border-[#F4C93B]/30 bg-forest-track text-cream hover:border-[#F4C93B]/60 transition-all font-mono text-xs sm:text-sm font-semibold"
          >
            <span>{currentId}</span>
            <GlowingBadge
              variant={
                currentItem.verdict === "fraud"
                  ? "fraud"
                  : currentItem.verdict === "legitimate"
                  ? "legitimate"
                  : "uncertain"
              }
            >
              {currentItem.verdict}
            </GlowingBadge>
            {currentItem.isBonus && (
              <span className="hidden sm:inline-flex text-[10px] text-[#FEE101] border border-[#EDD723]/40 px-1.5 py-0.5 rounded-full">
                D9
              </span>
            )}
            <ChevronDown className="w-3.5 h-3.5 text-sage opacity-75" />
          </button>

          {/* Dropdown Menu */}
          {dropdownOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setDropdownOpen(false)}
              />
              <div className="absolute left-1/2 -translate-x-1/2 mt-2 w-72 max-h-96 overflow-y-auto rounded-xl glass-panel border border-[#F4C93B]/30 shadow-2xl p-2 z-40 font-mono text-xs">
                <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-sage border-b border-white/5">
                  Select Investigation (25)
                </div>
                {cases.map((c) => {
                  const isSelected = c.id === currentId;
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setDropdownOpen(false);
                        router.push(`/case/${c.id}/`);
                      }}
                      className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left transition-colors ${
                        isSelected
                          ? "bg-[#F4C93B]/20 text-[#FEE101] font-bold"
                          : "text-cream hover:bg-forest/60"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span>{c.id}</span>
                        {c.isBonus && (
                          <span className="text-[9px] text-[#FEE101] bg-[#FEE101]/10 px-1 rounded">
                            D9
                          </span>
                        )}
                      </div>
                      <span
                        className={`text-[10px] uppercase font-semibold ${
                          c.verdict === "fraud" ? "text-[#FF0080]" : "text-[#8EB89B]"
                        }`}
                      >
                        {c.verdict}
                      </span>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Right: Next Step indicator */}
        <div className="hidden sm:flex items-center gap-2 font-mono text-xs text-sage">
          <span>{currentIndex + 1} / {cases.length}</span>
        </div>
      </div>
    </div>
  );
}

export default CaseSwitcher;
