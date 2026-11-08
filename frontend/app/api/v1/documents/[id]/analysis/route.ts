import { NextRequest, NextResponse } from "next/server";
import { getDocumentAnalysis } from "@/lib/seedDb";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const analysis = getDocumentAnalysis(params.id);
  if (!analysis) {
    return NextResponse.json({ detail: "Analysis not found" }, { status: 404 });
  }
  return NextResponse.json(analysis);
}

