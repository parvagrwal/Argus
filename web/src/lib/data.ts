import fs from "fs";
import path from "path";
import { CaseBundle, AblationMap } from "./types";

export const CASE_IDS: string[] = [
  ...Array.from({ length: 20 }, (_, i) => `HHG-${String(i + 1).padStart(3, "0")}`),
  ...Array.from({ length: 5 }, (_, i) => `BONUS_${String(i + 1).padStart(3, "0")}`),
];

export function getCaseById(caseId: string): CaseBundle | null {
  try {
    const filePath = path.join(process.cwd(), "public", "data", `${caseId}.json`);
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as CaseBundle;
  } catch (err) {
    console.error(`Error loading case ${caseId}:`, err);
    return null;
  }
}

export function getAllCases(): { id: string; bundle: CaseBundle }[] {
  const result: { id: string; bundle: CaseBundle }[] = [];
  for (const id of CASE_IDS) {
    const bundle = getCaseById(id);
    if (bundle) {
      result.push({ id, bundle });
    }
  }
  return result;
}

export function getAblationData(): AblationMap {
  try {
    const filePath = path.join(process.cwd(), "public", "data", "_ablation.json");
    if (!fs.existsSync(filePath)) {
      return {};
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as AblationMap;
  } catch (err) {
    console.error("Error loading ablation data:", err);
    return {};
  }
}

export function getCaseVerdict(bundle: CaseBundle): string {
  return (
    bundle.answer?.case?.verdict ||
    bundle.internal_record?.verdict ||
    "not recorded"
  ).toLowerCase();
}

export function getCaseProbability(bundle: CaseBundle): number | null {
  const prob =
    bundle.answer?.case?.confidence_breakdown?.adjusted_probability ??
    bundle.answer?.case?.flagged_risk_score ??
    bundle.internal_record?.confidence_breakdown?.adjusted_probability ??
    bundle.economics?.probability;
  return typeof prob === "number" ? prob : null;
}

export function getAggregateStats() {
  const all = getAllCases();
  const totalTransactions = 590742;
  const closedCases = 5565;
  const investigations = all.length;
  // Mechanically count fraud verdicts across the bundles
  const fraudCount = all.filter(({ bundle }) => getCaseVerdict(bundle) === "fraud").length;

  return {
    totalTransactions,
    closedCases,
    investigations,
    fraudCount,
  };
}
