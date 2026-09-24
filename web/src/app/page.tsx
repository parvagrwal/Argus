import React from "react";
import BrandBand from "@/components/brand-band";
import Hero from "@/components/hero";
import TheRing from "@/components/the-ring";
import Innovations from "@/components/innovations";
import CaseBentoGrid, { CaseCardData } from "@/components/case-bento-grid";
import Footer from "@/components/footer";
import {
  getAllCases,
  getAggregateStats,
  getCaseVerdict,
  getCaseProbability,
} from "@/lib/data";

export default function HomePage() {
  const allCases = getAllCases();
  const stats = getAggregateStats();

  const casesData: CaseCardData[] = allCases.map(({ id, bundle }) => {
    const verdict = getCaseVerdict(bundle);
    const probability = getCaseProbability(bundle);
    const exposureUsd =
      bundle.answer?.case?.exposure_usd ??
      bundle.economics?.exposure_usd ??
      bundle.answer?.sar?.total_amount_usd ??
      null;

    const triggerType =
      bundle.internal_record?.trigger_type ??
      bundle.answer?.case?.pattern ??
      "Investigation Trigger";

    const triggerText =
      bundle.internal_record?.trigger_text ??
      bundle.answer?.case?.summary ??
      "";

    const isFeatured = id === "HHG-014" || id === "HHG-012" || id === "HHG-017";
    const isBonus = id.startsWith("BONUS_");

    const summarySnippet =
      bundle.answer?.case?.pattern_description ??
      bundle.answer?.case?.summary ??
      triggerText;

    const sarFiled = Boolean(
      bundle.answer?.sar?.filing_recommended ?? bundle.answer?.sar?.file
    );

    return {
      id,
      verdict,
      probability,
      exposureUsd,
      triggerType,
      triggerText,
      isFeatured,
      isBonus,
      summarySnippet,
      sarFiled,
    };
  });

  return (
    <main className="w-full flex flex-col flex-1 bg-forest">
      {/* Section 0: Brand Band (MANDATORY) */}
      <BrandBand />

      {/* Section 1: Hero */}
      <Hero stats={stats} />

      {/* Section 2: The Ring (HHG-014 Network Visualizer) */}
      <TheRing />

      {/* Section 3: Innovations */}
      <Innovations />

      {/* Section 4: 25-Case Bento Grid */}
      <CaseBentoGrid cases={casesData} />

      {/* Section 5: Footer */}
      <Footer />
    </main>
  );
}
