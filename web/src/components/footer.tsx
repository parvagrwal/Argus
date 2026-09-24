"use client";

import Link from "next/link";
import { Terminal, Shield, ArrowUpRight } from "lucide-react";

export function Footer() {
  return (
    <footer className="w-full bg-[#041F13] border-t border-[#F4C93B]/20 py-12 px-4 sm:px-8 text-cream">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-8">
        {/* Compact Echo of Brand Band (§6 Item 5) */}
        <div className="flex flex-col sm:flex-row items-center gap-4 sm:gap-6">
          <div className="flex items-center gap-3">
            <span className="font-serif font-black tracking-wider text-xl uppercase text-[#F4C93B]">
              HACKER HOUSE
            </span>
            <img
              src="/brand/goa_hindi.svg"
              alt="गोवा"
              className="h-9 w-auto drop-shadow-md -rotate-6"
            />
          </div>

          <div className="hidden sm:block h-6 w-px bg-[#F4C93B]/30" />

          <div className="font-mono text-xs text-[#F4C93B] uppercase tracking-[0.18em] flex items-center gap-2">
            <span>GOA, INDIA · 28 – 31 OCT 2026</span>
            <img
              src="/brand/2-47.svg"
              alt="2:47 PM Studio"
              className="h-3.5 w-auto inline-block ml-1 opacity-90"
            />
          </div>
        </div>

        {/* Honest Label & Disclaimer (§6 Item 5 & §9) */}
        <div className="text-center md:text-right">
          <p className="font-mono text-[11px] text-sage max-w-md leading-relaxed">
            Recorded investigations — replayed from live TigerGraph runs, not live execution.
          </p>
          <div className="mt-2 flex items-center justify-center md:justify-end gap-4 font-mono text-[10px] text-[#F4C93B]/80 uppercase tracking-wider">
            <span>TigerGraph Enterprise 3.10</span>
            <span>·</span>
            <span>IEEE-CIS GraphRAG</span>
            <span>·</span>
            <span>Argus Autonomous Agent</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
