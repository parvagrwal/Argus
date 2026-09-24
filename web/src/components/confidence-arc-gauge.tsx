"use client";

import React from "react";
import { motion } from "framer-motion";
import AnimatedNumber from "@/components/ui/animated-number";

interface ConfidenceArcGaugeProps {
  probability: number | null;
  className?: string;
}

export function ConfidenceArcGauge({ probability, className }: ConfidenceArcGaugeProps) {
  const prob = probability !== null && !isNaN(probability) ? Math.min(Math.max(probability, 0), 1) : 0;
  const pct = Math.round(prob * 100);

  // SVG Geometry
  const width = 280;
  const height = 160;
  const cx = 140;
  const cy = 140;
  const radius = 100;
  const strokeWidth = 14;

  // Semicircle arc: from angle -180 deg (left) to 0 deg (right)
  // Arc length for semicircle: PI * radius
  const arcLength = Math.PI * radius;
  // Filled length proportional to probability
  const fillOffset = arcLength * (1 - prob);

  // Determine verdict color
  const isFraud = prob >= 0.85;
  const isLegit = prob <= 0.15;
  const statusColor = isFraud ? "#FF0080" : isLegit ? "#8EB89B" : "#F4C93B";

  // Arc path description (starts at cx-radius,cy and sweeps clockwise to cx+radius,cy)
  const d = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;

  return (
    <div className={`relative flex flex-col items-center select-none ${className || ""}`}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-[280px] h-auto overflow-visible"
      >
        <defs>
          {/* Signature Gauge Gradient per spec: #8EB89B 0%, #F4C93B 50%, #FF0080 100% */}
          <linearGradient id="signatureGaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#8EB89B" />
            <stop offset="50%" stopColor="#F4C93B" />
            <stop offset="100%" stopColor="#FF0080" />
          </linearGradient>

          {/* Glow filter */}
          <filter id="gaugeGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Background Track on #021D15 */}
        <path
          d={d}
          fill="none"
          stroke="#021D15"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />

        {/* Animated Sweep Arc */}
        <motion.path
          d={d}
          fill="none"
          stroke="url(#signatureGaugeGrad)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={arcLength}
          initial={{ strokeDashoffset: arcLength }}
          animate={{ strokeDashoffset: fillOffset }}
          transition={{ duration: 1.2, ease: "easeOut" }}
          filter="url(#gaugeGlow)"
        />

        {/* Threshold Markers: 0.15 and 0.85 */}
        {/* Angle for 0.15 = 180 * 0.15 = 27 deg from left (-180 + 27 = -153 deg) */}
        {/* Angle for 0.85 = 180 * 0.85 = 153 deg from left (-180 + 153 = -27 deg) */}
        <g opacity="0.4" stroke="#FFFBE8" strokeWidth="1.5">
          <line
            x1={cx + (radius - 12) * Math.cos(-Math.PI * 0.85)}
            y1={cy + (radius - 12) * Math.sin(-Math.PI * 0.85)}
            x2={cx + (radius + 12) * Math.cos(-Math.PI * 0.85)}
            y2={cy + (radius + 12) * Math.sin(-Math.PI * 0.85)}
          />
          <line
            x1={cx + (radius - 12) * Math.cos(-Math.PI * 0.15)}
            y1={cy + (radius - 12) * Math.sin(-Math.PI * 0.15)}
            x2={cx + (radius + 12) * Math.cos(-Math.PI * 0.15)}
            y2={cy + (radius + 12) * Math.sin(-Math.PI * 0.15)}
          />
        </g>

        {/* Center Readout Text */}
        <text
          x={cx}
          y={cy - 22}
          textAnchor="middle"
          fill={statusColor}
          fontSize="32"
          fontFamily="monospace"
          fontWeight="bold"
        >
          {probability !== null ? (prob).toFixed(3) : "N/A"}
        </text>

        <text
          x={cx}
          y={cy - 5}
          textAnchor="middle"
          fill="#8EB89B"
          fontSize="10"
          fontFamily="monospace"
          letterSpacing="0.1em"
        >
          POSTERIOR P(FRAUD)
        </text>
      </svg>

      {/* Threshold Zone Legend */}
      <div className="w-full max-w-[280px] flex items-center justify-between font-mono text-[10px] text-sage -mt-2 px-2">
        <span className="text-[#8EB89B]">0.00 (LEGIT)</span>
        <span className="text-[#F4C93B]">0.50 (UNCERTAIN)</span>
        <span className="text-[#FF0080]">1.00 (FRAUD)</span>
      </div>
    </div>
  );
}

export default ConfidenceArcGauge;
