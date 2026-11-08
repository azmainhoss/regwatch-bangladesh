import { NextResponse } from "next/server";
import { getSources } from "@/lib/seedDb";

export async function GET() {
  const sources = getSources();
  return NextResponse.json(sources);
}
