"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, ShieldAlert, ShieldCheck, HelpCircle, Sparkles, Filter } from "lucide-react";
import GlowingBadge from "@/components/ui/glowing-badge";
import { formatUsd, formatProbability } from "@/lib/utils";

export interface CaseCardData {
  id: string;
  verdict: string;
  probability: number | null;
  exposureUsd: number | null;
  triggerType: string;
  triggerText: string;
  isFeatured?: boolean;
  isBonus?: boolean;
  summarySnippet: string;
  sarFiled?: boolean;
}

export interface CaseBentoGridProps {
  cases: CaseCardData[];
}

export function CaseBentoGrid({ cases }: CaseBentoGridProps) {
  const [filter, setFilter] = useState<"all" | "fraud" | "legitimate" | "bonus">("all");

  const filteredCases = cases.filter((c) => {
    if (filter === "all") return true;
    if (filter === "fraud") return c.verdict === "fraud";
    if (filter === "legitimate") return c.verdict === "legitimate";
    if (filter === "bonus") return c.isBonus;
    return true;
  });

  return (
    <section id="cases" className="w-full py-20 px-4 sm:px-8 bg-forest-deep max-w-7xl mx-auto">
      {/* Header and Filter Buttons */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <GlowingBadge variant="live">Runtime Evidence</GlowingBadge>
            <span className="font-mono text-xs uppercase tracking-widest text-[#F4C93B]">
              25 Case Dossiers
            </span>
          </div>
          <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-cream">
            Investigation Archive
          </h2>
          <p className="mt-2 text-sage text-sm sm:text-base max-w-2xl leading-relaxed">
            20 core benchmark cases plus 5 autonomous D9 bonus discoveries replayed from TigerGraph.
          </p>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-xl glass-panel border border-[#F4C93B]/20">
          {(
            [
              { key: "all", label: "All Cases (25)" },
              { key: "fraud", label: "Fraud (21)" },
              { key: "legitimate", label: "Legitimate (4)" },
              { key: "bonus", label: "Bonus D9 (5)" },
            ] as const
          ).map((item) => (
            <button
              key={item.key}
              onClick={() => setFilter(item.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono uppercase tracking-wider transition-all ${
                filter === item.key
                  ? "bg-[#F4C93B] text-forest-deep font-bold shadow-[0_0_12px_rgba(244,201,59,0.3)]"
                  : "text-sage hover:text-cream hover:bg-forest/60"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filteredCases.map((caseItem) => {
          const isFeatured = caseItem.isFeatured;
          const isBonus = caseItem.isBonus;
          const isFraud = caseItem.verdict === "fraud";
          const isLegit = caseItem.verdict === "legitimate";

          // Sizing: featured tiles span 2 columns on lg
          const colSpan = isFeatured ? "lg:col-span-2" : "col-span-1";

          return (
            <Link
              key={caseItem.id}
              href={`/case/${caseItem.id}/`}
              className={`group relative p-6 rounded-2xl glass-panel glass-panel-hover flex flex-col justify-between overflow-hidden border ${
                isFeatured
                  ? "border-[#F4C93B]/40 bg-gradient-to-br from-forest-deep/90 via-forest/70 to-green-primary/10 shadow-[0_0_30px_rgba(244,201,59,0.08)]"
                  : isBonus
                  ? "border-[#EDD723]/30 bg-forest-deep/80"
                  : "border-[#F4C93B]/15 bg-forest-deep/70"
              } ${colSpan}`}
            >
              {/* Corner accent glow */}
              <div
                className={`absolute -top-12 -right-12 w-36 h-36 rounded-full blur-3xl opacity-15 pointer-events-none transition-opacity group-hover:opacity-30 ${
                  isFraud ? "bg-[#FF0080]" : isLegit ? "bg-[#8EB89B]" : "bg-[#F4C93B]"
                }`}
              />

              <div>
                {/* Top badges */}
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold tracking-wider text-cream">
                      {caseItem.id}
                    </span>
                    {isBonus && (
                      <span className="font-mono text-[10px] tracking-widest text-[#FEE101] bg-[#FEE101]/10 border border-[#EDD723]/40 px-2 py-0.5 rounded-full flex items-center gap-1">
                        <Sparkles className="w-2.5 h-2.5" />
                        <span>INNOVATION · D9</span>
                      </span>
                    )}
                    {isFeatured && (
                      <span className="font-mono text-[10px] tracking-widest text-[#F4C93B] bg-[#F4C93B]/15 border border-[#F4C93B]/40 px-2 py-0.5 rounded-full">
                        FEATURED
                      </span>
                    )}
                  </div>

                  {/* Verdict Badge */}
                  <GlowingBadge
                    variant={isFraud ? "fraud" : isLegit ? "legitimate" : "uncertain"}
                  >
                    {caseItem.verdict}
                  </GlowingBadge>
                </div>

                {/* Probability & Exposure Stats */}
                <div className="grid grid-cols-2 gap-3 py-3 px-3.5 my-3 rounded-xl bg-forest-track/70 border border-white/5 font-mono text-xs">
                  <div>
                    <span className="text-sage text-[10px] uppercase block">Probability</span>
                    <span
                      className={`text-sm font-bold ${
                        isFraud ? "text-[#FF0080]" : isLegit ? "text-sage" : "text-[#F4C93B]"
                      }`}
                    >
                      {caseItem.probability !== null
                        ? formatProbability(caseItem.probability)
                        : "not recorded"}
                    </span>
                  </div>

                  <div>
                    <span className="text-sage text-[10px] uppercase block">Exposure</span>
                    <span className="text-cream text-sm">
                      {formatUsd(caseItem.exposureUsd)}
                    </span>
                  </div>
                </div>

                {/* Trigger description / Snippet */}
                <div className="mt-2">
                  <div className="font-mono text-[11px] text-[#F4C93B] uppercase tracking-wider mb-1 line-clamp-1">
                    {caseItem.triggerType || "Trigger"}
                  </div>
                  <p className="text-sage text-xs line-clamp-2 leading-relaxed">
                    {caseItem.summarySnippet || caseItem.triggerText || "Investigation concluded."}
                  </p>
                </div>
              </div>

              {/* Card Footer CTA */}
              <div className="mt-6 pt-3 border-t border-[#F4C93B]/10 flex items-center justify-between font-mono text-xs text-[#F4C93B] group-hover:text-[#FEE101] transition-colors">
                <span className="flex items-center gap-1.5">
                  <span>Open Dossier</span>
                  {caseItem.sarFiled && (
                    <span className="text-[10px] text-[#FF0080] border border-[#FF0080]/30 px-1 rounded">
                      SAR FILED
                    </span>
                  )}
                </span>
                <ArrowRight className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

export default CaseBentoGrid;
