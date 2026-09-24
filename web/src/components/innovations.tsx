"use client";

import Link from "next/link";
import { Radar, Database, Calculator, GitBranch, ArrowUpRight } from "lucide-react";
import GlowingBadge from "@/components/ui/glowing-badge";

const INNOVATIONS = [
  {
    title: "Autonomous Monitor",
    headline: "5 D9 Discoveries",
    description: "Proactive graph daemon uncovered 5 high-yield syndicates outside transaction triggers.",
    icon: Radar,
    badge: "INNOVATION · D9",
    accentColor: "#F4C93B",
    targetHref: "/case/BONUS_001/",
  },
  {
    title: "Case Memory (Ablation)",
    headline: "0.0454 → 0.9838",
    description: "Cross-case graph memory resolved false negative in HHG-012, jumping probability by +0.9384.",
    icon: Database,
    badge: "ABLATION PROVEN",
    accentColor: "#FF0080",
    targetHref: "/case/HHG-012/",
  },
  {
    title: "Expected-Value Economics",
    headline: "VOI vs Delay Gate",
    description: "Bayesian stopping policy halts queries when marginal value of information drops below delay cost.",
    icon: Calculator,
    badge: "OPTIMAL STOPPING",
    accentColor: "#8EB89B",
    targetHref: "/case/HHG-014/",
  },
  {
    title: "Deterministic Recourse",
    headline: "100% Grounded Flips",
    description: "Verifiable counterfactual sentences specify exact minimal conditions to flip adverse decisions.",
    icon: GitBranch,
    badge: "EXPLAINABILITY",
    accentColor: "#FEE101",
    targetHref: "/case/HHG-017/",
  },
];

export function Innovations() {
  return (
    <section id="innovations" className="w-full py-20 px-4 sm:px-8 bg-forest max-w-6xl mx-auto">
      <div className="mb-12">
        <div className="flex items-center gap-2 mb-3">
          <GlowingBadge variant="d9">Autonomous Breakthroughs</GlowingBadge>
        </div>
        <h2 className="font-heading text-3xl sm:text-4xl font-bold text-cream tracking-tight">
          Four Core Agent Innovations
        </h2>
        <p className="mt-2 text-sage text-sm sm:text-base max-w-2xl leading-relaxed">
          Grounded directly in verifiable TigerGraph telemetry and automated Bayesian decisioning.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {INNOVATIONS.map((item, idx) => {
          const Icon = item.icon;
          return (
            <Link
              key={idx}
              href={item.targetHref}
              className="group relative p-6 sm:p-8 rounded-2xl glass-panel glass-panel-hover flex flex-col justify-between overflow-hidden"
            >
              {/* Subtle accent corner glow */}
              <div
                className="absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl opacity-20 pointer-events-none group-hover:opacity-40 transition-opacity"
                style={{ backgroundColor: item.accentColor }}
              />

              <div>
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center border border-white/10"
                    style={{ backgroundColor: `${item.accentColor}18` }}
                  >
                    <Icon className="w-5 h-5" style={{ color: item.accentColor }} />
                  </div>
                  <span className="font-mono text-[10px] tracking-widest text-[#F4C93B] uppercase border border-[#F4C93B]/30 px-2 py-0.5 rounded-full">
                    {item.badge}
                  </span>
                </div>

                <div className="font-heading text-xl font-semibold text-cream mb-1">
                  {item.title}
                </div>
                <div
                  className="font-mono text-2xl sm:text-3xl font-bold tracking-tight mb-3"
                  style={{ color: item.accentColor }}
                >
                  {item.headline}
                </div>
                <p className="text-sage text-sm leading-relaxed">
                  {item.description}
                </p>
              </div>

              <div className="mt-6 pt-4 border-t border-[#F4C93B]/10 flex items-center justify-between font-mono text-xs text-[#F4C93B] group-hover:text-[#FEE101] transition-colors">
                <span>Inspect in Case Study</span>
                <ArrowUpRight className="w-4 h-4 transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

export default Innovations;
