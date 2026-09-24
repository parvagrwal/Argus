"use client";

import Image from "next/image";
import { motion } from "framer-motion";

export function BrandBand() {
  return (
    <section className="relative w-full bg-[#0B6839] border-b border-[#F4C93B]/40 py-[clamp(2rem,6vw,5rem)] px-4 sm:px-8 overflow-hidden">
      {/* Subtle background texture/vignette */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-transparent to-black/25 pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="relative max-w-[1200px] mx-auto flex flex-col items-center"
      >
        {/* Wordmark and Overlapping Pink Sticker */}
        <div className="relative w-full flex justify-center items-center">
          <div className="relative w-[min(92vw,1100px)]">
            <Image
              src="/brand/Hacker-house.png"
              alt="Hacker House"
              width={1148}
              height={237}
              priority
              className="w-full h-auto select-none pointer-events-none"
            />

            {/* Pink sticker horizontally centered over middle of HACKER HOUSE */}
            <div
              className="absolute left-1/2 top-1/2 select-none pointer-events-none z-10"
              style={{
                transform: "translate(-50%, -50%) rotate(-8deg)",
              }}
            >
              <img
                src="/brand/goa_hindi.svg"
                alt="गोवा"
                className="w-[clamp(110px,14vw,200px)] h-auto drop-shadow-[0_8px_16px_rgba(0,0,0,0.45)]"
              />
            </div>
          </div>
        </div>

        {/* Mono Info Strip */}
        <div className="w-[min(92vw,1100px)] mt-4 sm:mt-6 pt-3 border-t border-[#F4C93B]/20 flex flex-col sm:flex-row items-center justify-between gap-2.5 font-mono text-[0.75rem] uppercase tracking-[0.18em] text-[#F4C93B]">
          <div className="flex items-center gap-2">
            <span>GOA, INDIA</span>
            <span className="opacity-50">·</span>
            <span>28 – 31 OCT 2026</span>
          </div>

          <div className="flex items-center opacity-90 hover:opacity-100 transition-opacity">
            <img
              src="/brand/2-47.svg"
              alt="2:47"
              className="h-5 w-auto filter brightness-110"
            />
          </div>
        </div>
      </motion.div>
    </section>
  );
}

export default BrandBand;
