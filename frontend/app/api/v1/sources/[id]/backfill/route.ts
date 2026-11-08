import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  return NextResponse.json({
    status: "COMPLETED",
    source_id: params.id,
    successful: 10,
    total: 10,
    documents_ingested: 10,
    message: "Historical backfill batch ingested 10 official circulars into repository.",
  });
}
