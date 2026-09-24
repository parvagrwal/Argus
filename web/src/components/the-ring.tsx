"use client";

import React, { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ShieldAlert, Server, Network, ArrowRight, ExternalLink } from "lucide-react";
import GlowingBadge from "@/components/ui/glowing-badge";

const CONNECTED_CARDS = [
  "C01289-K1",
  "C01996-K2",
  "C02910-K1",
  "C02975-K1",
  "C03676-K2",
  "C04108-K2",
  "C04274-K1",
  "C05448-K2",
  "C06710-K1",
  "C08168-K1",
  "C09049-K1",
  "C09906-K1",
  "C09975-K1",
  "C10193-K2",
  "C10326-K1",
  "C11082-K1",
  "C11670-K2",
  "C12796-K1",
  "C13291-K1",
];

const FOCAL_CARD = "C13487-K1";
const DEVICE_PROFILE = "SM-G935F (Android 7.0 / Chrome 62)";

export function TheRing() {
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);

  // SVG dimensions & center
  const width = 800;
  const height = 520;
  const cx = width / 2;
  const cy = height / 2;
  const rx = 320;
  const ry = 190;

  // Calculate coordinates for the 19 cards + 1 focal card (20 peripheral nodes)
  const allNodes = [FOCAL_CARD, ...CONNECTED_CARDS];
  const nodePositions = allNodes.map((cardId, index) => {
    // Distribute angles evenly around the ellipse
    const angle = (index / allNodes.length) * 2 * Math.PI - Math.PI / 2;
    const x = cx + rx * Math.cos(angle);
    const y = cy + ry * Math.sin(angle);
    return {
      cardId,
      x,
      y,
      isFocal: cardId === FOCAL_CARD,
    };
  });

  return (
    <section className="relative w-full py-20 px-4 sm:px-8 bg-forest-deep overflow-hidden border-t border-b border-[#F4C93B]/15">
      {/* Background vignette glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] bg-[#FF0080]/10 blur-[130px] rounded-full pointer-events-none" />

      <div className="relative max-w-6xl mx-auto">
        {/* Section Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <GlowingBadge variant="fraud">Network Graph Discovery</GlowingBadge>
              <span className="font-mono text-xs uppercase tracking-widest text-[#F4C93B]">
                CASE HHG-014 · THE RING
              </span>
            </div>
            <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-cream">
              Undocumented Fraud Syndicate
            </h2>
            <p className="mt-2 text-sage text-sm sm:text-base max-w-2xl leading-relaxed">
              Real TigerGraph topology replayed from investigation HHG-014. A single high-risk transaction uncovered 19 coordinated cards linked across a shared proxy device fingerprint.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Link
              href="/case/HHG-014/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#F4C93B] text-forest-deep font-medium text-sm hover:bg-[#FEE101] transition-colors shadow-[0_0_15px_rgba(244,201,59,0.25)]"
            >
              <span>Examine HHG-014</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Network Graph Container */}
        <div className="relative w-full rounded-2xl glass-panel p-4 sm:p-8 overflow-hidden shadow-2xl border border-[#F4C93B]/20">
          {/* Status HUD Header */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-6 mb-4 border-b border-[#F4C93B]/15 font-mono text-xs text-cream">
            <div className="flex items-center gap-6">
              <div>
                <span className="text-sage block text-[10px] uppercase">Probability</span>
                <span className="text-[#FF0080] font-bold text-sm">0.996 (Fraud)</span>
              </div>
              <div className="h-6 w-px bg-forest-track" />
              <div>
                <span className="text-sage block text-[10px] uppercase">SAR Filing</span>
                <span className="text-[#F4C93B] font-bold text-sm">RECOMMENDED</span>
              </div>
              <div className="h-6 w-px bg-forest-track" />
              <div>
                <span className="text-sage block text-[10px] uppercase">Syndicate Size</span>
                <span className="text-cream font-bold text-sm">19 Cards + 1 Focal</span>
              </div>
              <div className="h-6 w-px bg-forest-track hidden sm:block" />
              <div className="hidden sm:block">
                <span className="text-sage block text-[10px] uppercase">Flagged Txn</span>
                <span className="text-cream text-sm">#3478561 ($74.96)</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-[#FF0080] animate-ping" />
              <span className="text-[#FF0080] uppercase tracking-wider text-[11px]">
                Coordinated Ring Active
              </span>
            </div>
          </div>

          {/* SVG Visualizer */}
          <div className="w-full aspect-[16/10] max-h-[550px] relative flex items-center justify-center">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="w-full h-full select-none"
            >
              <defs>
                {/* Neon Pink Radial Gradient for Nodes */}
                <radialGradient id="pinkGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#FF0080" stopOpacity="1" />
                  <stop offset="100%" stopColor="#FF0080" stopOpacity="0.2" />
                </radialGradient>
                {/* Gold Radial Gradient for Hub */}
                <radialGradient id="goldGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#FEE101" stopOpacity="1" />
                  <stop offset="80%" stopColor="#F4C93B" stopOpacity="0.6" />
                  <stop offset="100%" stopColor="#0B6839" stopOpacity="0" />
                </radialGradient>
              </defs>

              {/* Connecting Edges from Central Hub to Card Nodes */}
              {nodePositions.map((pos) => {
                const isHovered = hoveredCard === pos.cardId;
                return (
                  <g key={`edge-${pos.cardId}`}>
                    {/* Background subtle line */}
                    <line
                      x1={cx}
                      y1={cy}
                      x2={pos.x}
                      y2={pos.y}
                      stroke={pos.isFocal ? "#F4C93B" : "#0B6839"}
                      strokeWidth={pos.isFocal ? 2 : 1}
                      strokeOpacity={isHovered ? 0.9 : 0.4}
                    />
                    {/* Animated Drawing Path */}
                    <motion.line
                      x1={cx}
                      y1={cy}
                      x2={pos.x}
                      y2={pos.y}
                      stroke={pos.isFocal ? "#FEE101" : "#FF0080"}
                      strokeWidth={pos.isFocal ? 2.5 : isHovered ? 2 : 1.2}
                      strokeOpacity={isHovered ? 1 : 0.75}
                      strokeDasharray="4 4"
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ duration: 1.2, ease: "easeOut", delay: 0.1 }}
                    />
                  </g>
                );
              })}

              {/* Central Proxy Hub */}
              <g className="cursor-pointer">
                {/* Pulsing ring around hub */}
                <motion.circle
                  cx={cx}
                  cy={cy}
                  r={48}
                  fill="none"
                  stroke="#F4C93B"
                  strokeWidth="1.5"
                  strokeOpacity="0.4"
                  animate={{ scale: [1, 1.25, 1], opacity: [0.4, 0.1, 0.4] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={36}
                  fill="#041F13"
                  stroke="#F4C93B"
                  strokeWidth="2"
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={28}
                  fill="url(#goldGlow)"
                  opacity="0.3"
                />
                {/* Hub Label */}
                <text
                  x={cx}
                  y={cy - 6}
                  textAnchor="middle"
                  fill="#FFFBE8"
                  fontSize="10"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  PROXY HUB
                </text>
                <text
                  x={cx}
                  y={cy + 8}
                  textAnchor="middle"
                  fill="#F4C93B"
                  fontSize="8.5"
                  fontFamily="monospace"
                >
                  SM-G935F
                </text>
                <text
                  x={cx}
                  y={cy + 20}
                  textAnchor="middle"
                  fill="#8EB89B"
                  fontSize="7.5"
                  fontFamily="monospace"
                >
                  Android 7.0
                </text>
              </g>

              {/* Peripheral Card Nodes */}
              {nodePositions.map((pos) => {
                const isHovered = hoveredCard === pos.cardId;
                return (
                  <g
                    key={`node-${pos.cardId}`}
                    onMouseEnter={() => setHoveredCard(pos.cardId)}
                    onMouseLeave={() => setHoveredCard(null)}
                    className="cursor-pointer transition-transform"
                  >
                    {/* Pink/Gold Glow Pulse */}
                    <motion.circle
                      cx={pos.x}
                      cy={pos.y}
                      r={pos.isFocal ? 16 : 11}
                      fill="none"
                      stroke={pos.isFocal ? "#F4C93B" : "#FF0080"}
                      strokeWidth="1.5"
                      animate={{ scale: [1, 1.4, 1], opacity: [0.8, 0.15, 0.8] }}
                      transition={{
                        duration: 2.2,
                        repeat: Infinity,
                        delay: (pos.x % 10) * 0.1,
                        ease: "easeInOut",
                      }}
                    />

                    {/* Node Core */}
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={pos.isFocal ? 10 : 7}
                      fill={pos.isFocal ? "#F4C93B" : "#FF0080"}
                      stroke="#041F13"
                      strokeWidth="2"
                    />

                    {/* Node Label */}
                    <text
                      x={pos.x}
                      y={pos.y > cy ? pos.y + 16 : pos.y - 12}
                      textAnchor="middle"
                      fill={pos.isFocal ? "#FEE101" : isHovered ? "#FFFBE8" : "#8EB89B"}
                      fontSize={pos.isFocal ? "10" : "8"}
                      fontFamily="monospace"
                      fontWeight={pos.isFocal || isHovered ? "bold" : "normal"}
                    >
                      {pos.cardId}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Hover Tooltip Overlay */}
            {hoveredCard && (
              <div className="absolute top-4 left-4 glass-panel px-3 py-2 rounded-lg font-mono text-xs border border-[#F4C93B]/40 shadow-lg pointer-events-none">
                <div className="text-cream font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-[#FF0080]" />
                  <span>Card {hoveredCard}</span>
                </div>
                <div className="text-sage text-[11px]">
                  {hoveredCard === FOCAL_CARD
                    ? "Flagged trigger card (Txn 3478561)"
                    : "Confirmed linked syndicate card"}
                </div>
              </div>
            )}
          </div>

          {/* Real Findings Callout */}
          <div className="mt-6 pt-4 border-t border-[#F4C93B]/15 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-xs font-mono text-sage">
            <div className="flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-[#FF0080] shrink-0 mt-0.5" />
              <span>
                <strong className="text-cream">Graph Finding:</strong> Pattern is undocumented (R9) — shared proxy device profile across cards with confirmed fraud. Probability 0.996 rests on 2 independent graph queries (card_window, device_neighbors).
              </span>
            </div>

            <Link
              href="/case/HHG-014/"
              className="text-[#F4C93B] hover:text-[#FEE101] underline underline-offset-4 flex items-center gap-1 shrink-0"
            >
              <span>Full Investigation Trace</span>
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export default TheRing;
