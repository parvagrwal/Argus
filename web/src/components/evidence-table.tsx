"use client";

import React from "react";
import { Database, UserCheck, Shield, FileSpreadsheet } from "lucide-react";
import { EvidenceItem } from "@/lib/types";

interface EvidenceTableProps {
  evidence: Array<{
    id?: string;
    claim?: string;
    source?: string;
    ref?: string;
    type?: string;
    supports?: string;
    entity_ids?: string[];
  }>;
}

export function EvidenceTable({ evidence }: EvidenceTableProps) {
  if (!evidence || evidence.length === 0) {
    return (
      <div className="font-mono text-xs text-sage py-6 text-center">
        No formal evidence rows recorded in bundle.
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full text-left font-mono text-xs border-collapse">
        <thead>
          <tr className="border-b border-[#F4C93B]/20 text-sage uppercase text-[10px] tracking-wider">
            <th className="py-2.5 px-3">ID</th>
            <th className="py-2.5 px-3">Claim & Findings</th>
            <th className="py-2.5 px-3">Source</th>
            <th className="py-2.5 px-3">Query / Reference</th>
            <th className="py-2.5 px-3">Entities</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#F4C93B]/10 text-cream">
          {evidence.map((item, idx) => {
            const id = item.id || `E${idx + 1}`;
            const source = (item.source || "graph").toLowerCase();
            const isGraph = source.includes("graph");
            const isCustomer = source.includes("customer");

            return (
              <tr
                key={`ev-${idx}`}
                className="hover:bg-forest-track/50 transition-colors"
              >
                {/* ID */}
                <td className="py-3 px-3 font-bold text-[#F4C93B] whitespace-nowrap">
                  {id}
                </td>

                {/* Claim */}
                <td className="py-3 px-3 max-w-sm sm:max-w-md font-sans text-xs text-cream leading-relaxed">
                  {item.claim || "not recorded"}
                </td>

                {/* Source Chip: Pink for Graph, Gold for Customer/Other per §7 & §8 */}
                <td className="py-3 px-3 whitespace-nowrap">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider ${
                      isGraph
                        ? "bg-[#FF0080]/15 text-[#FF0080] border border-[#FF0080]/30"
                        : isCustomer
                        ? "bg-[#F4C93B]/15 text-[#F4C93B] border border-[#F4C93B]/30"
                        : "bg-[#8EB89B]/15 text-[#8EB89B] border border-[#8EB89B]/30"
                    }`}
                  >
                    {isGraph ? (
                      <Database className="w-2.5 h-2.5" />
                    ) : (
                      <UserCheck className="w-2.5 h-2.5" />
                    )}
                    <span>{item.source || "graph"}</span>
                  </span>
                </td>

                {/* Query / Reference */}
                <td className="py-3 px-3 text-sage text-[11px] max-w-xs truncate" title={item.ref || item.type || ""}>
                  {item.ref || item.type || item.supports || "direct fact"}
                </td>

                {/* Entities */}
                <td className="py-3 px-3 text-[11px] text-cream whitespace-nowrap">
                  {item.entity_ids && item.entity_ids.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {item.entity_ids.map((ent, eIdx) => (
                        <span
                          key={eIdx}
                          className="px-1.5 py-0.5 rounded bg-forest border border-white/10 text-[10px]"
                        >
                          {ent}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sage opacity-75">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default EvidenceTable;
