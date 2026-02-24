from __future__ import annotations

import json
import re

import requests


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"


def _chat(prompt: str, temperature: float = 0.15) -> str:
    res = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": False,
        },
        timeout=120,
    )
    res.raise_for_status()
    return str(res.json().get("message", {}).get("content", "")).strip()


def _normalize_rewrite_output(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return ""

    text = text.replace("\n", " ").strip()
    text = re.sub(r"^[-•\*\d\.)\s]+", "", text)
    text = text.strip('"\'` ')
    text = re.sub(r"\s+", " ", text).strip()
    return text


def rewrite_bullet(
    original: str,
    jd_requirement: str,
    jd_full: str = "",
    resume_skills: str = "",
    parent_context: str = "",
) -> str:
    prompt = f"""
You are an elite resume optimization assistant. Rewrite ONE resume bullet to align with the JD requirement while staying fully truthful.

STRICT RULES:
- You MUST keep the same factual meaning as the original bullet.
- Do NOT invent technologies, metrics, team sizes, timelines, scope, users, or outcomes.
- Do NOT claim ownership of tools/frameworks not clearly present in original bullet.
- Keep tense and person consistent with original.
- Prefer strong action verbs and concise wording.
- Target length: 14-28 words.
- Return ONLY the rewritten bullet text.

INPUTS:
ORIGINAL_BULLET: {original}
JD_REQUIREMENT: {jd_requirement}
JD_FULL: {jd_full}
RESUME_SKILLS: {resume_skills}
PARENT_CONTEXT: {parent_context}

QUALITY BAR:
- Keep it ATS-friendly and keyword-aligned with JD_REQUIREMENT.
- Preserve credibility over aggressiveness.
- Avoid fluff and vague claims.
- Only use technologies/tools that are explicitly supported by ORIGINAL_BULLET, RESUME_SKILLS, or PARENT_CONTEXT.

OUTPUT:
One plain sentence. No list marker. No JSON. No explanation.
"""

    content = _chat(prompt, temperature=0.15)
    cleaned = _normalize_rewrite_output(content)
    return cleaned or original


def extract_jd_requirements(jd_text: str) -> list[str]:
    prompt = f"""
Extract concise job requirements from the text below.
Return ONLY a JSON array of strings and nothing else.

JD:
{jd_text}
"""

    content = _chat(prompt, temperature=0.1)

    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            cleaned = [str(item).strip() for item in parsed if str(item).strip()]
            if cleaned:
                return cleaned
    except Exception:
        match = re.search(r"\[[\s\S]*\]", content)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    if cleaned:
                        return cleaned
            except Exception:
                pass

    lines = [line.strip(" -•\t") for line in jd_text.splitlines() if line.strip()]
    return lines[:15]
