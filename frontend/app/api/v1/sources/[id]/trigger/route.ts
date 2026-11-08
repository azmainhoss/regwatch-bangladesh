import { NextRequest, NextResponse } from "next/server";
import { updateSource } from "@/lib/seedDb";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const nowIso = new Date().toISOString();
  updateSource(params.id, {
    last_attempted_run_at: nowIso,
    last_successful_run_at: nowIso,
    last_checked_at: nowIso,
    last_error: null,
    access_restriction_status: "HEALTHY",
  });

  return NextResponse.json({
    id: "run-" + Date.now(),
    source_id: params.id,
    run_type: "CONTINUOUS_MONITORING",
    status: "COMPLETED",
    pages_inspected: 5,
    candidate_links_discovered: 3,
    valid_documents_discovered: 3,
    downloads_attempted: 3,
    downloads_successful: 3,
    duplicate_count: 0,
    access_restricted: false,
    access_restriction_details: {},
    retry_count: 0,
    error_count: 0,
    started_at: new Date(Date.now() - 3200).toISOString(),
    completed_at: nowIso,
    message: "Continuous monitoring completed: 5 pages inspected, 3 candidate circulars verified.",
  });
}
