import { NextRequest, NextResponse } from "next/server";
import { getDocuments } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const docs = getDocuments();
  const deptBreakdown: Record<string, number> = {};
  for (const d of docs) {
    const code = (d.reference_number || "").split(" ")[0] || "BRPD";
    deptBreakdown[code] = (deptBreakdown[code] || 0) + 1;
  }

  return NextResponse.json({
    source_id: params.id,
    source_name: "Bangladesh Bank Regulatory Portal",
    is_active: true,
    total_discovered: docs.length,
    total_ingested: docs.length,
    total_pending: 0,
    total_duplicates: 0,
    total_failed: 0,
    department_breakdown: deptBreakdown,
    year_breakdown: { "2024": 6, "2025": 8, "2026": 4 },
    language_breakdown: { "bn": docs.length },
    last_polled_at: new Date().toISOString(),
    last_successful_run_at: new Date().toISOString(),
    access_restriction_status: "UNRESTRICTED",
  });
}

