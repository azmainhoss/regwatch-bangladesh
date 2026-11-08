import { NextRequest, NextResponse } from "next/server";
import { getDocumentAnalysis } from "@/lib/seedDb";

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const analysis = getDocumentAnalysis(params.id);
  if (!analysis) {
    return NextResponse.json({ detail: "Document analysis initialized" }, { status: 200 });
  }
  return NextResponse.json(analysis);
}
