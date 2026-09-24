"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, RotateCcw, Clock, Terminal, CheckCircle2 } from "lucide-react";
import { ToolCallItem } from "@/lib/types";

interface TraceStep {
  step: number;
  tool: string;
  args?: Record<string, unknown> | string;
  rows?: number;
  latency_ms?: number;
  result_summary?: string;
  ts?: string;
}

interface TraceReplayProps {
  traces: TraceStep[];
}

export function TraceReplay({ traces }: TraceReplayProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [visibleCount, setVisibleCount] = useState<number>(traces.length);

  const startReplay = () => {
    setIsPlaying(true);
    setVisibleCount(0);

    traces.forEach((_, idx) => {
      setTimeout(() => {
        setVisibleCount(idx + 1);
        if (idx === traces.length - 1) {
          setIsPlaying(false);
        }
      }, (idx + 1) * 350);
    });
  };

  const showAll = () => {
    setVisibleCount(traces.length);
    setIsPlaying(false);
  };

  if (!traces || traces.length === 0) {
    return (
      <div className="font-mono text-xs text-sage py-4 text-center">
        No graph tool telemetry recorded for this case.
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full">
      {/* Header Replay Button */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-[#F4C93B]/15">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-[#F4C93B]" />
          <span className="font-mono text-xs uppercase tracking-wider text-cream font-semibold">
            TigerGraph Tool Telemetry
          </span>
          <span className="font-mono text-[10px] text-sage bg-forest px-1.5 py-0.5 rounded border border-white/10">
            {traces.length} {traces.length === 1 ? "query" : "queries"}
          </span>
        </div>

        <button
          onClick={isPlaying ? showAll : startReplay}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#F4C93B] text-forest-deep font-mono text-xs font-bold hover:bg-[#FEE101] transition-all shadow-[0_0_12px_rgba(244,201,59,0.25)]"
        >
          {isPlaying ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Show All</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Replay Investigation</span>
            </>
          )}
        </button>
      </div>

      {/* Scrollable Trace Feed Container with Frosted Edge */}
      <div className="relative max-h-[340px] overflow-y-auto pr-2 space-y-2.5">
        {traces.map((trace, idx) => {
          const isVisible = idx < visibleCount;
          if (!isVisible) return null;

          const paramText =
            typeof trace.args === "object"
              ? Object.entries(trace.args || {})
                  .map(([k, v]) => `${k}=${v}`)
                  .join(", ")
              : String(trace.args || "");

          return (
            <motion.div
              key={`trace-${idx}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25 }}
              className="p-3 rounded-xl bg-forest-track/80 border border-[#F4C93B]/10 hover:border-[#F4C93B]/30 transition-colors font-mono text-xs"
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-4 h-4 rounded-full bg-[#0B6839] text-[#FEE101] flex items-center justify-center text-[10px] font-bold">
                    {trace.step || idx + 1}
                  </span>
                  <span className="text-[#F4C93B] font-bold">
                    {trace.tool}
                  </span>
                  {trace.rows !== undefined && (
                    <span className="text-[10px] text-sage bg-forest px-1.5 py-0.2 rounded border border-white/5">
                      {trace.rows} {trace.rows === 1 ? "row" : "rows"}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 text-[11px] text-sage">
                  <Clock className="w-3 h-3" />
                  <span>
                    {typeof trace.latency_ms === "number"
                      ? `${trace.latency_ms.toFixed(3)} ms`
                      : "not recorded"}
                  </span>
                </div>
              </div>

              {/* Params / Summary */}
              {paramText && (
                <div className="text-[11px] text-sage/80 line-clamp-1 mb-1 font-mono">
                  {paramText}
                </div>
              )}

              {trace.result_summary && (
                <div className="text-cream text-xs bg-forest/50 p-2 rounded border border-white/5 mt-1 leading-relaxed">
                  {trace.result_summary}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

export default TraceReplay;
