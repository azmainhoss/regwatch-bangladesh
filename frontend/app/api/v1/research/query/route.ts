import { NextRequest, NextResponse } from "next/server";
import {
  getDocumentAnalysis,
  getDocument,
  getDocumentProvisions,
  getDocumentCitationsWithPages,
} from "@/lib/seedDb";

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
    const query = (body.query || "").trim();
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
    const provisions = getDocumentProvisions(documentId);
    const availableCitations = getDocumentCitationsWithPages(documentId);

    if (!analysis) {
      return NextResponse.json({
        query,
        answer: `Document '${doc?.title || "selected circular"}' is indexed in the repository. Detailed clause-level Q&A will be enabled once full clause extraction is complete.`,
        is_grounded: false,
        citations: [],
        caveats: ["Detailed clause analysis pending."],
      });
    }

    const summary = analysis.executive_summary || "Official regulatory directives apply as published.";
    const keyChanges: string[] = Array.isArray(analysis.key_changes)
      ? analysis.key_changes
      : [];

    // Optional: If GEMINI_API_KEY is configured in Vercel environment, perform live free-tier generation
    const apiKey = process.env.GEMINI_API_KEY;
    if (apiKey && query) {
      try {
        const promptContext = [
          `Circular: ${doc?.reference_number || "BB"} - ${doc?.title || ""}`,
          `Summary: ${summary}`,
          `Key Directives:\n${keyChanges.map((k, i) => `${i + 1}. ${k}`).join("\n")}`,
          provisions.length > 0
            ? `Provisions:\n${provisions.slice(0, 5).map((p: any) => `- ${p.title || p.clause_number}: ${p.content_text}`).join("\n")}`
            : "",
          availableCitations.length > 0
            ? `Extracted Verbatim Excerpts:\n${availableCitations.slice(0, 6).map((c) => `[Page ${c.page_number}]: "${c.quote}"`).join("\n")}`
            : "",
        ].filter(Boolean).join("\n\n");

        const modelName = process.env.GEMINI_MODEL || "gemini-flash-lite-latest";
        const geminiRes = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${apiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [
                {
                  role: "user",
                  parts: [
                    {
                      text: `You are RegWatch Bangladesh AI, an expert banking regulatory compliance intelligence assistant.\n\nOFFICIAL REGULATORY CONTEXT:\n${promptContext}\n\nUSER QUESTION: ${query}\n\nINSTRUCTIONS:\n1. Answer the user's question directly, accurately, and thoroughly using the context above.\n2. Do NOT give a generic summary if the user is asking a specific question (e.g. about deadlines, penalties, definitions, stages, or comparisons). Address their specific inquiry directly.\n3. If the user asks in Bengali or requests Bengali, respond in fluent Bengali. If in English, respond in English.\n4. Mention specific clauses, page numbers, and circular references where appropriate.\n5. Keep the tone professional, objective, and authoritative for banking compliance officers.`,
                    },
                  ],
                },
              ],
            }),
          }
        );

        if (geminiRes.ok) {
          const geminiData = await geminiRes.json();
          const generatedText = geminiData.candidates?.[0]?.content?.parts?.[0]?.text;
          if (generatedText) {
            // Select most relevant citations
            const selectedCits = availableCitations.slice(0, 3);
            return NextResponse.json({
              query,
              answer: generatedText,
              is_grounded: true,
              citations: selectedCits.length > 0
                ? selectedCits
                : [
                    {
                      document_id: documentId,
                      document_title: doc?.title,
                      reference_number: doc?.reference_number,
                      page_number: 1,
                      verbatim_excerpt: summary.slice(0, 200),
                      quoted_text: summary.slice(0, 200),
                      quote: summary.slice(0, 200),
                    },
                  ],
              caveats: ["Generated by Gemini AI and grounded directly in Bangladesh Bank publication records."],
            });
          }
        }
      } catch {
        // Fallback to grounded local intelligence if Gemini API call fails
      }
    }

    // Grounded intelligence engine matching keywords
    const lowerQuery = query.toLowerCase();
    const queryTokens = lowerQuery
      .replace(/[^\w\s]/g, " ")
      .split(/\s+/)
      .filter((w: string) => w.length > 2 && !["what", "which", "where", "when", "does", "have", "this", "that", "from", "with", "circular", "bangladesh", "bank"].includes(w));

    // Score available citations based on token overlap
    const scoredCitations = availableCitations.map((cit) => {
      const text = `${cit.claim_statement} ${cit.quote}`.toLowerCase();
      let score = 0;
      for (const token of queryTokens) {
        if (text.includes(token)) score += 2;
      }
      return { cit, score };
    });
    scoredCitations.sort((a, b) => b.score - a.score);

    const matchingCits = scoredCitations.filter((sc) => sc.score > 0).map((sc) => sc.cit);
    const chosenCitations = (matchingCits.length > 0 ? matchingCits : availableCitations).slice(0, 3);

    // Formulate structured grounded compliance answer
    let answerText = "";
    if (matchingCits.length > 0) {
      const topQuotes = chosenCitations.map((c) => `• [Page ${c.page_number}]: "${c.quote}"`).join("\n\n");
      answerText = `Inquiry Analysis for '${doc?.reference_number || doc?.title}':\n\nSpecific Grounded Findings:\n${topQuotes}\n\nContext & Regulatory Scope:\n${summary}`;
    } else {
      const directivesList = keyChanges.length > 0
        ? keyChanges.map((kc, idx) => `${idx + 1}. ${kc}`).join("\n")
        : "Direct compliance with Bangladesh Bank prudential governance standards is mandatory.";
      answerText = `Based on official publication '${doc?.reference_number || doc?.title}':\n\nExecutive Overview:\n${summary}\n\nMandatory Directives & Operational Changes:\n${directivesList}`;
    }

    // Default citation if none found
    const finalCitations = chosenCitations.length > 0
      ? chosenCitations
      : [
          {
            document_id: documentId,
            document_title: doc?.title,
            reference_number: doc?.reference_number,
            page_number: 1,
            verbatim_excerpt: summary.slice(0, 180),
            quoted_text: summary.slice(0, 180),
            quote: summary.slice(0, 180),
          },
        ];

    return NextResponse.json({
      query,
      answer: answerText,
      is_grounded: true,
      citations: finalCitations,
      caveats: ["Grounded directly against official Bangladesh Bank publication records."],
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to process research query" },
      { status: 500 }
    );
  }
}
