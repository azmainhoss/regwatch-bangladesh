import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    id: "discovery-" + Date.now(),
    status: "COMPLETED",
    source_id: params.id,
    candidate_links_discovered: 3,
    valid_documents_discovered: 3,
    duplicate_count: 0,
    scanned_pages: 5,
    message: "Discovery scan cataloged 3 candidate publications from Bangladesh Bank portal.",
  });
}
