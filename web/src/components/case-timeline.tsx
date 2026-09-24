"use client";

import React from "react";
import { CheckCircle, AlertTriangle, ShieldAlert, ArrowDown } from "lucide-react";
import { formatProbability } from "@/lib/utils";

export interface ProgressionRound {
  round: number;
  probability?: number;
  rule_fired?: string;
  independent_evidence?: number;
  continue_investigating?: boolean;
  note?: string;
}

interface CaseTimelineProps {
  decisions: ProgressionRound[];
  stopReason?: string;
  finalVerdict: string;
  finalProbability: number | null;
}

export function CaseTimeline({
  decisions,
  stopReason,
  finalVerdict,
  finalProbability,
}: CaseTimelineProps) {
  const isFraud = finalVerdict === "fraud";
  const isLegit = finalVerdict === "legitimate";

  return (
    <div className="relative pl-6 sm:pl-8 py-2 w-full">
      {/* Vertical Spine (Gold-dim #EDD723 at 40% per §8) */}
      <div className="absolute left-3 top-3 bottom-3 w-0.5 bg-[#EDD723]/40" />

      <div className="space-y-6">
        {/* Rounds */}
        {decisions.map((step, idx) => {
          const stepProb = step.probability ?? null;
          const stepIsFraud = stepProb !== null && stepProb >= 0.85;
          const stepIsLegit = stepProb !== null && stepProb <= 0.15;

          const dotColor = stepIsFraud
            ? "bg-[#FF0080] border-[#FF0080]"
            : stepIsLegit
            ? "bg-[#8EB89B] border-[#8EB89B]"
            : "bg-[#F4C93B] border-[#F4C93B]";

          return (
            <div key={`step-${idx}`} className="relative group">
              {/* Timeline Node Dot */}
              <div
                className={`absolute -left-[19px] sm:-left-[27px] top-1.5 w-3.5 h-3.5 rounded-full border-2 border-forest-deep ${dotColor} shadow-md`}
              />

              <div className="p-3.5 rounded-xl bg-forest-track/70 border border-[#F4C93B]/10 hover:border-[#F4C93B]/30 transition-colors font-mono text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sage text-[10px] uppercase font-bold">
                      Round {step.round ?? idx}
                    </span>
                    <span className="text-[#F4C93B] font-semibold">
                      {step.rule_fired || "Graph Evaluation"}
                    </span>
                  </div>

                  {stepProb !== null && (
                    <span className="px-2 py-0.5 rounded bg-forest border border-white/10 font-bold text-cream">
                      P = {formatProbability(stepProb)}
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between text-[11px] text-sage">
                  <span>
                    Signals: {step.independent_evidence ?? "1"} independent
                  </span>
                  <span>
                    {step.continue_investigating ? (
                      <span className="text-[#FEE101]">CONTINUE GATHERING</span>
                    ) : (
                      <span className="text-cream">STOPPED</span>
                    )}
                  </span>
                </div>

                {step.note && (
                  <div className="mt-1 text-[11px] text-sage/80 italic">
                    {step.note}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Stopping Decision */}
        <div className="relative">
          {/* Stopping Marker Node */}
          <div
            className={`absolute -left-[21px] sm:-left-[29px] top-2 w-4 h-4 rounded-full border-2 border-forest-deep ${
              isFraud ? "bg-[#FF0080]" : isLegit ? "bg-[#8EB89B]" : "bg-[#F4C93B]"
            } shadow-[0_0_10px_currentColor]`}
          />

          <div className="p-4 rounded-xl bg-forest-deep border border-[#F4C93B]/30 shadow-lg font-mono text-xs">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="text-[#F4C93B] text-[10px] uppercase tracking-wider font-bold">
                Stopping Criterion Satisfied
              </span>
              <span
                className={`px-2 py-0.5 rounded uppercase font-bold text-[11px] ${
                  isFraud
                    ? "bg-[#FF0080]/20 text-[#FF0080] border border-[#FF0080]/40"
                    : "bg-[#062C1B] text-[#8EB89B] border border-[#0B6839]"
                }`}
              >
                Verdict: {finalVerdict}
              </span>
            </div>

            <p className="text-cream text-xs leading-relaxed mb-2">
              {stopReason ||
                (isFraud
                  ? "Hard stop threshold reached: posterior probability >= 0.85 with verified graph signals."
                  : "Investigation closed: probability <= 0.15 or VOI < cost of delay gate.")}
            </p>

            <div className="pt-2 border-t border-[#F4C93B]/10 flex items-center justify-between text-[11px] text-sage">
              <span>Final Posterior</span>
              <span className="font-bold text-cream">
                {finalProbability !== null ? formatProbability(finalProbability) : "N/A"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CaseTimeline;
