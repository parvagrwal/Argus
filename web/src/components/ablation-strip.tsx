"use client";

import React from "react";
import { Database, AlertTriangle, ArrowRight, Sparkles } from "lucide-react";
import GlowingBadge from "@/components/ui/glowing-badge";
import { formatProbability } from "@/lib/utils";

interface AblationStripProps {
  pWithMemory: number;
  pWithoutMemory: number;
  verdictWith: string;
  verdictWithout: string;
  deltaP: number;
}

export function AblationStrip({
  pWithMemory,
  pWithoutMemory,
  verdictWith,
  verdictWithout,
  deltaP,
}: AblationStripProps) {
  return (
    <div className="w-full rounded-2xl glass-panel p-6 border-2 border-[#F4C93B]/40 bg-gradient-to-r from-forest-deep via-[#0B6839]/20 to-forest-deep shadow-[0_0_30px_rgba(244,201,59,0.15)] mb-8">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-4 border-b border-[#F4C93B]/20">
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-5 h-5 text-[#FEE101]" />
          <div>
            <h3 className="font-heading text-lg font-bold text-cream">
              Case-Memory Ablation Experiment
            </h3>
            <span className="font-mono text-xs text-[#F4C93B]">
              Direct comparison: With vs. Without Cross-Case Graph Memory
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <GlowingBadge variant="d9">
            Verdict Flipped: {verdictWithout} → {verdictWith}
          </GlowingBadge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
        {/* Without Memory Bar */}
        <div className="p-4 rounded-xl bg-forest-track/90 border border-white/5 font-mono text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sage uppercase font-bold text-[10px]">
              Without Case Memory (Ablated)
            </span>
            <span className="px-2 py-0.5 rounded bg-[#FF0080]/15 text-[#FF0080] border border-[#FF0080]/30 font-bold uppercase">
              {verdictWithout}
            </span>
          </div>

          <div className="text-2xl font-bold text-[#FF0080] mb-2">
            P = {formatProbability(pWithoutMemory)}
          </div>

          {/* Bar track */}
          <div className="w-full h-3 rounded-full bg-forest-track overflow-hidden border border-white/10">
            <div
              className="h-full bg-[#FF0080] rounded-full transition-all"
              style={{ width: `${Math.min(pWithoutMemory * 100, 100)}%` }}
            />
          </div>

          <p className="mt-3 text-sage text-[11px] leading-relaxed font-sans">
            Lacking access to historical graph syndicates, the agent misinterpreted isolated velocity as malicious, producing a false positive fraud verdict.
          </p>
        </div>

        {/* With Memory Bar */}
        <div className="p-4 rounded-xl bg-forest-deep border border-[#F4C93B]/30 font-mono text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[#FEE101] uppercase font-bold text-[10px] flex items-center gap-1">
              <Database className="w-3 h-3" />
              <span>With Case Memory (Full Argus)</span>
            </span>
            <span className="px-2 py-0.5 rounded bg-[#062C1B] text-[#8EB89B] border border-[#0B6839] font-bold uppercase">
              {verdictWith}
            </span>
          </div>

          <div className="text-2xl font-bold text-[#8EB89B] mb-2">
            P = {formatProbability(pWithMemory)}
          </div>

          {/* Bar track */}
          <div className="w-full h-3 rounded-full bg-forest-track overflow-hidden border border-white/10">
            <div
              className="h-full bg-[#8EB89B] rounded-full transition-all"
              style={{ width: `${Math.min(pWithMemory * 100, 100)}%` }}
            />
          </div>

          <p className="mt-3 text-cream text-[11px] leading-relaxed font-sans">
            Cross-case graph memory recalled prior cleared transactions and legitimate merchant relationships, shifting posterior probability by <strong className="text-[#FEE101]">ΔP = {formatProbability(deltaP)}</strong> and clearing the cardholder.
          </p>
        </div>
      </div>
    </div>
  );
}

export default AblationStrip;
