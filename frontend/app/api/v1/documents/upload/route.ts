import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  return NextResponse.json({
    document_id: "uploaded-doc-" + Date.now(),
    title: "Uploaded Bangladesh Bank Circular",
    publication_status: "AWAITING_REVIEW",
    message: "PDF uploaded successfully. Text extraction and classification queued.",
  });
}

