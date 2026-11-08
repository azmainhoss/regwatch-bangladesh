import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "healthy",
    configured_provider: "gemini",
    default_model: "gemini-flash-lite-latest",
    gemini_api_key_configured: true,
    timeout_seconds: 60,
    max_retries: 3,
    billing_policy: "strictly_free_tier",
    admin_diagnostics: {
      provider_name: "Google Gemini Free-Tier",
      model_identifier: "gemini-flash-lite-latest",
      free_tier_eligible: true,
      billing_tier: "free_tier",
      rate_limits: {
        requests_per_minute: 15,
        tokens_per_minute: 1000000,
        requests_per_day: 1500,
      },
    },
  });
}

