import React from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  FileText,
  Clock,
  Coins,
  Cpu,
  ArrowRight,
  TrendingUp,
  Scale,
  Sparkles,
} from "lucide-react";
import CaseSwitcher from "@/components/case-switcher";
import TraceReplay from "@/components/trace-replay";
import CaseTimeline from "@/components/case-timeline";
import EvidenceTable from "@/components/evidence-table";
import ConfidenceArcGauge from "@/components/confidence-arc-gauge";
import AblationStrip from "@/components/ablation-strip";
import Footer from "@/components/footer";
import GlowingBadge from "@/components/ui/glowing-badge";
import {
  CASE_IDS,
  getCaseById,
  getAllCases,
  getAblationData,
  getCaseVerdict,
  getCaseProbability,
} from "@/lib/data";
import { formatUsd, formatProbability } from "@/lib/utils";

export function generateStaticParams() {
  return CASE_IDS.map((id) => ({ id }));
}

interface CasePageProps {
  params: {
    id: string;
  };
}

export default function CaseDetailPage({ params }: CasePageProps) {
  const { id } = params;
  const bundle = getCaseById(id);

  if (!bundle) {
    notFound();
  }

  const allCases = getAllCases();
  const switcherItems = allCases.map(({ id: cId, bundle: b }) => ({
    id: cId,
    verdict: getCaseVerdict(b),
    isBonus: cId.startsWith("BONUS_"),
  }));

  const verdict = getCaseVerdict(bundle);
  const probability = getCaseProbability(bundle);
  const isFraud = verdict === "fraud";
  const isLegit = verdict === "legitimate";

  const cardId =
    bundle.internal_record?.card_id ||
    bundle.answer?.case?.connected_card_ids?.[0] ||
    "not recorded";

  const txnId =
    bundle.internal_record?.flagged_txn_id ||
    bundle.answer?.case?.first_suspicious_txn_id ||
    bundle.answer?.case?.affected_txn_ids?.[0] ||
    "not recorded";

  const exposureUsd =
    bundle.answer?.case?.exposure_usd ??
    bundle.economics?.exposure_usd ??
    bundle.answer?.sar?.total_amount_usd ??
    null;

  const triggerType =
    bundle.internal_record?.trigger_type ??
    bundle.answer?.case?.pattern ??
    "Transaction Flag";

  const triggerText =
    bundle.internal_record?.trigger_text ??
    bundle.answer?.case?.summary ??
    "not recorded";

  // Telemetry Traces
  const rawTraces = (bundle.internal_record?.tool_trace ||
    (Array.isArray(bundle.answer?.tool_calls) ? bundle.answer.tool_calls : [])) as Array<any>;

  const traces = rawTraces.map((t, idx) => ({
    step: t.step ?? idx + 1,
    tool: t.tool ?? t.query_name ?? "graph_query",
    args: t.args ?? t.params ?? {},
    rows: t.rows,
    latency_ms: t.latency_ms,
    result_summary: t.result_summary,
    ts: t.ts ?? t.timestamp,
  }));

  // Progression decisions
  const rawProgression = (bundle.internal_record?.decisions || []) as Array<any>;
  const progressionRounds = rawProgression.map((d, idx) => ({
    round: d.round ?? idx,
    probability: d.probability,
    rule_fired: d.rule_fired ?? d.action,
    independent_evidence: d.independent_evidence,
    continue_investigating: d.continue_investigating,
    note: d.note ?? d.reason,
  }));

  // Evidence list
  const evidenceList = (bundle.answer?.case?.evidence || []) as Array<any>;

  // Confidence Breakdown
  const confidenceBreakdown = bundle.internal_record?.confidence_breakdown;
  const features = confidenceBreakdown?.features || {};
  const weights = confidenceBreakdown?.weights || {};

  // Compute feature contributions
  const contributions = Object.keys(features)
    .filter((k) => typeof features[k] === "number" && features[k] !== 0)
    .map((k) => {
      const val = features[k];
      const weight = typeof weights[k] === "number" ? weights[k] : 1;
      const score = val * weight;
      return {
        feature: k,
        value: val,
        weight,
        score,
      };
    })
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score))
    .slice(0, 6);

  // NBA
  const rawNba = bundle.answer?.next_best_actions as any;
  let initialActions: any[] = [];
  let finalActions: any[] = [];
  let whatChanged: string = "not recorded";

  if (rawNba) {
    if (rawNba.initial || rawNba.final) {
      initialActions = Array.isArray(rawNba.initial) ? rawNba.initial : [];
      finalActions = Array.isArray(rawNba.final) ? rawNba.final : [];
      whatChanged = rawNba.what_changed || "No change between initial and final recommendations.";
    } else if (Array.isArray(rawNba)) {
      initialActions = rawNba.map((item: any) => ({
        action: item.initial_action || item.action,
        reason: item.reason || "Automated initial policy gate",
        route: item.route || "auto",
      }));
      finalActions = rawNba.map((item: any) => ({
        action: item.final_action || item.action,
        reason: item.reason || "Policy confirmed after evidence accumulation",
        route: item.route || "auto",
      }));
      whatChanged = rawNba[0]?.what_changed || "Recommendations adapted to gathered graph evidence.";
    }
  }

  // Next actions (Panel 6)
  const finalDecisionList =
    (bundle.answer?.case?.decisions as any[]) ||
    finalActions ||
    [];

  // Counterfactual
  const counterfactualSentence =
    bundle.counterfactual?.sentence ||
    (bundle.counterfactual?.flips && bundle.counterfactual.flips.length > 0
      ? `If ${bundle.counterfactual.flips[0].feature} changed to ${bundle.counterfactual.flips[0].flip_to}, decision would change.`
      : "not recorded");

  // Ablation data for HHG-012
  const ablationData = getAblationData();
  const hhg012Ablation = ablationData["HHG-012"];

  return (
    <div className="w-full min-h-screen bg-forest flex flex-col">
      {/* Case Switcher Sticky Header */}
      <CaseSwitcher currentId={id} cases={switcherItems} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 sm:py-12">
        {/* Case Title Banner */}
        <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#F4C93B]/20">
          <div>
            <div className="flex items-center gap-3 mb-2 font-mono text-xs">
              <span className="text-[#F4C93B] font-bold tracking-widest uppercase">
                Investigation Dossier
              </span>
              <span className="text-sage opacity-50">/</span>
              <span className="text-cream">{id}</span>
              {id.startsWith("BONUS_") && (
                <span className="text-[10px] text-[#FEE101] bg-[#FEE101]/10 border border-[#EDD723]/40 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5" />
                  <span>D9 Autonomous Discovery</span>
                </span>
              )}
            </div>

            <h1 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-cream">
              Case {id}
            </h1>
            <p className="mt-1 text-sage text-sm max-w-3xl leading-relaxed">
              {triggerType}: {triggerText}
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <GlowingBadge
              variant={isFraud ? "fraud" : isLegit ? "legitimate" : "uncertain"}
              className="text-sm px-4 py-1.5"
            >
              {verdict}
            </GlowingBadge>

            <div className="px-4 py-2 rounded-xl bg-forest-track border border-[#F4C93B]/20 font-mono text-right">
              <div className="text-[10px] uppercase text-sage">Exposure</div>
              <div className="text-cream font-bold text-sm">
                {formatUsd(exposureUsd)}
              </div>
            </div>
          </div>
        </div>

        {/* HHG-012 Special Case-Memory Ablation Strip */}
        {id === "HHG-012" && hhg012Ablation && (
          <AblationStrip
            pWithMemory={hhg012Ablation.p_with_memory}
            pWithoutMemory={hhg012Ablation.p_without_memory}
            verdictWith={hhg012Ablation.verdict_with}
            verdictWithout={hhg012Ablation.verdict_without}
            deltaP={hhg012Ablation.delta_p}
          />
        )}

        {/* The Six Panels Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* PANEL 1: Investigation (Trigger Card + Tool Trace Replay) */}
          <div
            className={`p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 1
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Investigation & Telemetry
                </h2>
              </div>
              <span className="font-mono text-[11px] text-sage">
                Txn #{txnId}
              </span>
            </div>

            {/* Trigger Card Header */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 rounded-xl bg-forest-track/70 border border-white/5 font-mono text-xs mb-6">
              <div>
                <span className="text-sage text-[10px] uppercase block">Card ID</span>
                <span className="text-cream font-bold">{cardId}</span>
              </div>
              <div>
                <span className="text-sage text-[10px] uppercase block">Flagged Risk</span>
                <span className="text-[#F4C93B] font-bold">
                  {typeof bundle.internal_record?.flagged_risk_score === "number"
                    ? bundle.internal_record.flagged_risk_score.toFixed(2)
                    : "not recorded"}
                </span>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <span className="text-sage text-[10px] uppercase block">Exposure</span>
                <span className="text-cream font-bold">{formatUsd(exposureUsd)}</span>
              </div>
            </div>

            {/* Trace Replay Feed */}
            <TraceReplay traces={traces} />
          </div>

          {/* PANEL 2: Case Progression (Vertical Timeline) */}
          <div
            className={`p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 2
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Case Progression Timeline
                </h2>
              </div>
              <span className="font-mono text-[11px] text-sage">
                {progressionRounds.length} Rounds
              </span>
            </div>

            <CaseTimeline
              decisions={progressionRounds}
              stopReason={bundle.answer?.stop_reason}
              finalVerdict={verdict}
              finalProbability={probability}
            />
          </div>

          {/* PANEL 3: Evidence (Evidence Table) */}
          <div
            className={`lg:col-span-2 p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 3
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Evidence Inventory
                </h2>
              </div>
              <span className="font-mono text-[11px] text-[#F4C93B]">
                {evidenceList.length} Verified Claims
              </span>
            </div>

            <EvidenceTable evidence={evidenceList} />
          </div>

          {/* PANEL 4: Uncertainty & Economics */}
          <div
            className={`p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 4
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Uncertainty & Economics
                </h2>
              </div>
              <span className="font-mono text-[11px] text-sage">
                Bayesian Gate
              </span>
            </div>

            {/* Arc Gauge Centerpiece */}
            <div className="mb-6 flex justify-center">
              <ConfidenceArcGauge probability={probability} />
            </div>

            {/* Economics Reading Strip */}
            {bundle.economics && (
              <div className="p-4 rounded-xl bg-forest-track/80 border border-[#F4C93B]/20 font-mono text-xs mb-6">
                <div className="flex items-center justify-between text-sage text-[10px] uppercase pb-2 mb-2 border-b border-white/5">
                  <span>Economic Threshold Reading</span>
                  <span className="text-[#F4C93B]">
                    VOI: {formatUsd(bundle.economics.value_of_information_usd)}
                  </span>
                </div>
                <p className="text-cream text-xs leading-relaxed font-sans">
                  {bundle.economics.reading || "not recorded"}
                </p>
                <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between text-[11px] text-sage">
                  <span>Delay Cost Gate:</span>
                  <span className="text-cream font-bold">
                    {formatUsd(bundle.economics.cost_of_delay_gate_usd)}
                  </span>
                </div>
              </div>
            )}

            {/* Per-Feature Contributions */}
            <div>
              <div className="font-mono text-xs text-sage uppercase tracking-wider mb-3">
                Top Contributing Features
              </div>
              {contributions.length > 0 ? (
                <div className="space-y-2 font-mono text-xs">
                  {contributions.map((c, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-forest/50 border border-white/5"
                    >
                      <span className="text-cream truncate max-w-[200px]">{c.feature}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sage text-[11px]">w={c.weight}</span>
                        <span
                          className={`font-bold ${
                            c.score > 0 ? "text-[#FF0080]" : "text-[#8EB89B]"
                          }`}
                        >
                          {c.score > 0 ? `+${c.score.toFixed(2)}` : c.score.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="font-mono text-xs text-sage">not recorded</div>
              )}
            </div>
          </div>

          {/* PANEL 5: Recommendations & Counterfactuals */}
          <div
            className={`p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 5
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Next Best Actions
                </h2>
              </div>
              <span className="font-mono text-[11px] text-sage">
                Initial vs Final
              </span>
            </div>

            {/* Side by side Initial vs Final */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              {/* Initial */}
              <div className="p-4 rounded-xl bg-forest-track/70 border border-white/5 font-mono text-xs">
                <div className="text-sage text-[10px] uppercase font-bold mb-2">
                  Initial Recommendation
                </div>
                {initialActions.length > 0 ? (
                  initialActions.map((act, idx) => (
                    <div key={idx} className="mb-2 last:mb-0">
                      <div className="text-[#F4C93B] font-bold">{act.action}</div>
                      <div className="text-sage text-[11px] mt-0.5 leading-snug">
                        {act.reason}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-sage">not recorded</div>
                )}
              </div>

              {/* Final */}
              <div className="p-4 rounded-xl bg-forest-track/70 border border-[#F4C93B]/30 font-mono text-xs">
                <div className="text-[#FEE101] text-[10px] uppercase font-bold mb-2">
                  Final Recommendation
                </div>
                {finalActions.length > 0 ? (
                  finalActions.map((act, idx) => (
                    <div key={idx} className="mb-2 last:mb-0">
                      <div
                        className={`font-bold ${
                          isFraud ? "text-[#FF0080]" : "text-[#8EB89B]"
                        }`}
                      >
                        {act.action}
                      </div>
                      <div className="text-sage text-[11px] mt-0.5 leading-snug">
                        {act.reason}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-sage">not recorded</div>
                )}
              </div>
            </div>

            {/* What Changed Highlight */}
            <div className="p-4 rounded-xl bg-forest-deep border border-[#F4C93B]/20 font-mono text-xs mb-6">
              <span className="text-[#F4C93B] text-[10px] uppercase font-bold block mb-1">
                Evidence Delta
              </span>
              <p className="text-cream text-xs leading-relaxed font-sans">
                {whatChanged}
              </p>
            </div>

            {/* Counterfactual Callout with Gold Left-Border per §7 */}
            <div className="p-4 rounded-xl bg-forest-track border-l-4 border-l-[#F4C93B] border border-white/5 font-mono text-xs">
              <span className="text-[#F4C93B] text-[10px] uppercase font-bold block mb-1">
                Deterministic Counterfactual Recourse
              </span>
              <p className="text-cream text-xs font-sans leading-relaxed italic">
                "{counterfactualSentence}"
              </p>
            </div>
          </div>

          {/* PANEL 6: Next Actions & Route Badges */}
          <div
            className={`lg:col-span-2 p-6 sm:p-8 rounded-2xl glass-panel border ${
              isFraud ? "glow-card-pink" : isLegit ? "glow-card-sage" : "glow-card-gold"
            }`}
          >
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-[#F4C93B]/15">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#F4C93B] font-bold">
                  PANEL 6
                </span>
                <span className="text-sage opacity-50">·</span>
                <h2 className="font-heading text-xl font-bold text-cream">
                  Next Actions & Policy Citations
                </h2>
              </div>
              <span className="font-mono text-[11px] text-sage">
                Operational Dispatch
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {finalDecisionList.length > 0 ? (
                finalDecisionList.map((dec, idx) => {
                  const route = (dec.route || "AUTO").toUpperCase();
                  return (
                    <div
                      key={idx}
                      className="p-4 rounded-xl bg-forest-track/70 border border-[#F4C93B]/15 font-mono text-xs flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <span className="font-bold text-cream text-sm">
                            {dec.action}
                          </span>
                          {/* Route Badge per theme §8: bg-[#FEE101]/15 text-[#FEE101] border-[#EDD723] */}
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-[#FEE101]/15 text-[#FEE101] border border-[#EDD723]/60">
                            {route}
                          </span>
                        </div>

                        <p className="text-sage text-xs font-sans leading-relaxed mb-3">
                          {dec.reason || "Policy guideline executed."}
                        </p>
                      </div>

                      {dec.rule_citations && dec.rule_citations.length > 0 && (
                        <div className="pt-2 border-t border-white/5 text-[10px] text-sage">
                          Rules: {dec.rule_citations.join(", ")}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="font-mono text-xs text-sage col-span-3 py-4 text-center">
                  No subsequent actions dispatched.
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}
