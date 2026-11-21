"""Times the Gemini call alone with the real Ask prompt, for different settings."""
import asyncio, time, sys, json
sys.path.insert(0, ".")
import backend.app.main  # noqa: registers models
import httpx
from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.research import service as svc

CAPT = {}
class Capture:
    async def generate_structured_json(self, system_prompt, user_prompt, **kw):
        CAPT["sys"], CAPT["user"] = system_prompt, user_prompt
        from backend.app.modules.analysis.providers.base import LLMResponse, TokenUsage
        return LLMResponse(raw_content="", parsed_json=None, token_usage=TokenUsage(), model_name="x", latency_ms=0, success=False, error="cap")

async def call(model, sysp, user, gen_extra, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    gc = {"temperature": 0, "responseMimeType": "application/json", **gen_extra}
    payload = {"contents": [{"role": "user", "parts": [{"text": user}]}], "systemInstruction": {"parts": [{"text": sysp}]}, "generationConfig": gc}
    async with httpx.AsyncClient(timeout=60) as c:
        t = time.perf_counter(); r = await c.post(url, json=payload, headers={"x-goog-api-key": key}); dt = time.perf_counter() - t
    try:
        j = r.json(); u = j.get("usageMetadata", {}); txt = j["candidates"][0]["content"]["parts"][0]["text"][:80]
    except Exception:
        u = {}; txt = r.text[:150]
    return dt, r.status_code, u, txt

async def main():
    q = sys.argv[1]
    svc.get_answer_provider = lambda: Capture()
    async with AsyncSessionLocal() as db:
        await svc.ResearchService.query_regulatory_knowledge(db, q)
    print("prompt chars", len(CAPT["user"]))
    key = settings.GEMINI_API_KEY
    for model, extra in json.loads(sys.argv[2]):
        dt, st, u, txt = await call(model, CAPT["sys"], CAPT["user"], extra, key)
        print(f"{model} {extra} -> {dt:.2f}s {st} in={u.get('promptTokenCount')} out={u.get('candidatesTokenCount')} think={u.get('thoughtsTokenCount')} | {txt}")

if __name__ == "__main__":
    asyncio.run(main())
