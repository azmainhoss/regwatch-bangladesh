import { NextRequest, NextResponse } from "next/server";
import { updateSource } from "@/lib/seedDb";

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await request.json().catch(() => ({}));
  const isActive = Boolean(body.is_active);

  const updated = updateSource(params.id, {
    is_active: isActive ? 1 : 0,
    access_restriction_status: isActive ? "HEALTHY" : "IMPERVA_TSPD_CAPTCHA",
    last_error: isActive
      ? null
      : "Access restricted by Imperva/TSPD WAF JavaScript challenge. Automation halted per security rules.",
    updated_at: new Date().toISOString(),
  });

  return NextResponse.json(
    updated || {
      id: params.id,
      is_active: isActive,
      access_restriction_status: isActive ? "HEALTHY" : "IMPERVA_TSPD_CAPTCHA",
      message: "Source status updated successfully.",
    }
  );
}
