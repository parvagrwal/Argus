"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowDown, Network, ShieldCheck, Terminal, Compass } from "lucide-react";
import ScrambleText from "@/components/ui/scramble-text";
import AnimatedNumber from "@/components/ui/animated-number";
import GlowingBadge from "@/components/ui/glowing-badge";
import { RadialGlowButton } from "@/components/ui/radial-glow-button";

interface HeroProps {
  stats: {
    totalTransactions: number;
    closedCases: number;
    investigations: number;
    fraudCount: number;
  };
}

export function Hero({ stats }: HeroProps) {
  return (
    <section className="relative w-full min-h-[600px] lg:min-h-[680px] flex flex-col justify-center items-center py-20 px-4 sm:px-8 overflow-hidden bg-forest">
      {/* Aurora Ambient Background Glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {/* Animated Green / Gold aurora sweeps */}
        <div className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[1100px] h-[600px] bg-gradient-to-b from-[#0B6839]/40 via-[#F4C93B]/10 to-transparent blur-[120px] rounded-full animate-aurora" />
        <div className="absolute top-[40%] -left-[10%] w-[500px] h-[500px] bg-[#075029]/30 blur-[100px] rounded-full pointer-events-none" />
        <div className="absolute top-[30%] -right-[10%] w-[500px] h-[500px] bg-[#F4C93B]/10 blur-[120px] rounded-full pointer-events-none" />
      </div>

      <div className="relative max-w-5xl mx-auto flex flex-col items-center text-center z-10">
        {/* Live Badge */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-6 flex items-center gap-2"
        >
          <GlowingBadge variant="recorded">Replayed Runtime Telemetry</GlowingBadge>
        </motion.div>

        {/* Scramble-Text ARGUS Wordmark */}
        <div className="font-heading text-6xl sm:text-7xl md:text-8xl lg:text-9xl font-black tracking-tight text-cream select-none drop-shadow-[0_10px_30px_rgba(0,0,0,0.5)]">
          <ScrambleText
            text="ARGUS"
            scrambleSpeed={40}
            scrambledLetterCount={3}
            autoStart={true}
            className="text-cream"
            scrambledClassName="text-[#F4C93B] opacity-70"
          />
        </div>

        {/* Tagline */}
        <motion.h1
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-4 font-heading text-2xl sm:text-3xl md:text-4xl font-semibold tracking-tight text-[#FEE101]"
        >
          Agentic fraud investigation on TigerGraph.
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25 }}
          className="mt-3 text-sage text-base sm:text-lg md:text-xl font-normal max-w-2xl leading-relaxed"
        >
          25 investigations. 590,742 transactions. One graph.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="mt-8 flex flex-col sm:flex-row items-center gap-4"
        >
          <a href="#cases" className="no-underline">
            <RadialGlowButton className="cursor-pointer font-bold tracking-wide">
              Enter the investigations
            </RadialGlowButton>
          </a>

          <a
            href="#innovations"
            className="px-6 py-3 rounded-xl border border-[#F4C93B]/40 hover:border-[#FEE101] text-cream hover:text-[#FEE101] font-mono text-sm uppercase tracking-wider transition-all bg-[#041F13]/60 backdrop-blur-md"
          >
            How it works
          </a>
        </motion.div>

        {/* Animated Stat Row */}
        <motion.div
          initial={{ opacity: 0, y: 25 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.45 }}
          className="mt-16 w-full grid grid-cols-2 md:grid-cols-4 gap-4 p-5 rounded-2xl glass-panel border border-[#F4C93B]/20 text-cream"
        >
          {/* Stat 1 */}
          <div className="flex flex-col items-center justify-center p-3 border-r border-[#F4C93B]/10 last:border-r-0">
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-[#F4C93B] flex items-center justify-center">
              <span>590,742</span>
            </div>
            <div className="mt-1 text-sage text-xs uppercase font-mono tracking-wider">
              Transactions
            </div>
          </div>

          {/* Stat 2 */}
          <div className="flex flex-col items-center justify-center p-3 border-r border-[#F4C93B]/10 last:border-r-0">
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-cream flex items-center justify-center">
              <span>5,565</span>
            </div>
            <div className="mt-1 text-sage text-xs uppercase font-mono tracking-wider">
              Closed Cases
            </div>
          </div>

          {/* Stat 3 */}
          <div className="flex flex-col items-center justify-center p-3 border-r border-[#F4C93B]/10 last:border-r-0">
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-[#FEE101] flex items-center justify-center">
              <AnimatedNumber value={stats.investigations} />
            </div>
            <div className="mt-1 text-sage text-xs uppercase font-mono tracking-wider">
              Investigations
            </div>
          </div>

          {/* Stat 4: Mechanically computed fraud count */}
          <div className="flex flex-col items-center justify-center p-3">
            <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-[#FF0080] flex items-center justify-center">
              <AnimatedNumber value={stats.fraudCount} />
            </div>
            <div className="mt-1 text-sage text-xs uppercase font-mono tracking-wider">
              Fraud Findings
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

export default Hero;
