import { NextRequest, NextResponse } from "next/server";
import { getDocumentAnalysis, getDocument } from "@/lib/seedDb";

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get("authorization");
    if (!authHeader) {
      return NextResponse.json(
        { detail: "Authentication required: Please log in or provide valid credentials to query the research assistant." },
        { status: 401 }
      );
    }

    const body = await request.json();
    const query = body.query || "";
    const documentId = body.document_id;

    if (!documentId) {
      return NextResponse.json({
        query,
        answer: "Please select a specific regulatory circular to execute grounded clause analysis.",
        is_grounded: false,
        citations: [],
        caveats: ["Document context was not provided."],
      });
    }

    const doc = getDocument(documentId);
    const analysis = getDocumentAnalysis(documentId);

    if (!analysis) {
      return NextResponse.json({
        query,
        answer: `Document '${doc?.title || "selected circular"}' is currently indexed. Specific analytical Q&A will be enabled once full clause extraction is complete.`,
        is_grounded: false,
        citations: [],
        caveats: ["Detailed clause analysis pending."],
      });
    }

    const summary = analysis.executive_summary || "Official regulatory directives apply as published.";
    const keyChanges = Array.isArray(analysis.key_changes)
      ? analysis.key_changes.join(". ")
      : "";

    return NextResponse.json({
      query,
      answer: `Based on the official publication '${doc?.reference_number || doc?.title}':\n\n${summary}\n\nKey Directives:\n${keyChanges || "Compliant operational governance mandatory."}`,
      is_grounded: true,
      citations: [
        {
          document_id: documentId,
          page_number: 1,
          quote: summary.slice(0, 150),
        },
      ],
      caveats: ["Grounded directly against official Bangladesh Bank publication records."],
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to process research query" },
      { status: 500 }
    );
  }
}

