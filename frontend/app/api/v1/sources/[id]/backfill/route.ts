import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    status: "COMPLETED",
    source_id: params.id,
    documents_ingested: 5,
    message: "Historical backfill batch ingested successfully into repository.",
  });
}
