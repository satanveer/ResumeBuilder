from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from services.llm import extract_jd_requirements, rewrite_bullet
from services.matcher import best_matches
from services.parser import parse_resume_pdf
from services.renderer import render_resume

BASE_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = BASE_DIR / "sessions"
OUTPUT_DIR = BASE_DIR / "outputs"
MAX_SESSIONS = 20

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173"]}})


for directory in [SESSIONS_DIR, OUTPUT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _load_session(session_id: str) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_session(session: dict[str, Any]) -> None:
    session_id = session["session_id"]
    session["updated_at"] = datetime.utcnow().isoformat()
    path = _session_path(session_id)
    path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    _prune_sessions()


def _prune_sessions() -> None:
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    stale = files[MAX_SESSIONS:]
    for path in stale:
        sid = path.stem
        path.unlink(missing_ok=True)
        for artifact in OUTPUT_DIR.glob(f"{sid}__*"):
            artifact.unlink(missing_ok=True)
        for ext in [".tex", ".pdf", ".aux", ".log", ".out"]:
            (OUTPUT_DIR / f"{sid}{ext}").unlink(missing_ok=True)


def _flatten_bullets(resume_data: dict[str, Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []

    for job_index, job in enumerate(resume_data.get("experience", [])):
        for bullet_index, bullet in enumerate(job.get("bullets", [])):
            flattened.append(
                {
                    "section": "experience",
                    "parent_index": job_index,
                    "bullet_index": bullet_index,
                    "text": bullet,
                }
            )

    for proj_index, proj in enumerate(resume_data.get("projects", [])):
        for bullet_index, bullet in enumerate(proj.get("bullets", [])):
            flattened.append(
                {
                    "section": "projects",
                    "parent_index": proj_index,
                    "bullet_index": bullet_index,
                    "text": bullet,
                }
            )

    return flattened


def _normalize_url(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://", "mailto:")):
        return text
    if "@" in text and "." in text:
        return f"mailto:{text}"
    return f"https://{text}"


def _extract_contact_context(contact_text: str) -> dict[str, str]:
    raw = re.sub(r"\(cid:\d+\)", " ", contact_text or "")
    raw = re.sub(r"\s+", " ", raw).strip()

    context = {
        "github_url": "",
        "github_label": "",
        "website_url": "",
        "website_label": "",
        "linkedin_url": "",
        "linkedin_label": "",
        "email": "",
        "raw_contact": raw,
    }

    tokens = [item.strip() for item in re.split(r"\s*\|\s*", raw) if item.strip()]
    stop_words = ["education", "skills", "projects", "experience"]

    cleaned_tokens: list[str] = []
    for token in tokens:
        value = token.strip(" -—|,;:")
        lowered = value.lower()
        cut = len(value)
        for marker in stop_words:
            idx = lowered.find(marker)
            if idx > 0:
                cut = min(cut, idx)
        value = value[:cut].strip(" -—|,;:")
        if value:
            cleaned_tokens.append(value)

    tokens = cleaned_tokens

    text_blob = " ".join(tokens)

    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text_blob)
    if email_match and not context["email"]:
        context["email"] = email_match.group(0)

    github_url_match = re.search(r"(https?://(?:www\.)?github\.com/[^\s|]+)", text_blob, flags=re.IGNORECASE)
    if github_url_match and not context["github_url"]:
        url = github_url_match.group(1)
        context["github_url"] = _normalize_url(url)
        context["github_label"] = "github"
    elif "github" in text_blob.lower() and not context["github_url"]:
        context["github_label"] = "github"

    linkedin_url_match = re.search(r"(https?://(?:www\.)?linkedin\.com/[^\s|]+)", text_blob, flags=re.IGNORECASE)
    if linkedin_url_match and not context["linkedin_url"]:
        url = linkedin_url_match.group(1)
        context["linkedin_url"] = _normalize_url(url)
        context["linkedin_label"] = "linkedin"
    elif "linkedin" in text_blob.lower() and not context["linkedin_url"]:
        context["linkedin_label"] = "linkedin"

    website_url_match = re.search(r"(https?://(?:www\.)?[^\s|]+\.[A-Za-z]{2,})", text_blob, flags=re.IGNORECASE)
    if website_url_match and not context["website_url"]:
        url = website_url_match.group(1)
        if "github.com" not in url.lower() and "linkedin.com" not in url.lower():
            context["website_url"] = _normalize_url(url)
            context["website_label"] = url.replace("https://", "").replace("http://", "").strip("/")

    if not context["website_url"]:
        bare_domains = re.findall(r"\b[a-z0-9][a-z0-9.-]*\.(?:com|org|net|io|dev|tech)\b", text_blob, flags=re.IGNORECASE)
        for domain in bare_domains:
            lower_domain = domain.lower()
            if "github.com" in lower_domain or "linkedin.com" in lower_domain:
                continue
            context["website_url"] = _normalize_url(domain)
            context["website_label"] = domain.strip("/")
            break

    for token in tokens:
        lower = token.lower()
        if "github.com" in lower and not context["github_url"]:
            context["github_url"] = _normalize_url(token)
            context["github_label"] = "github"
        elif "linkedin.com" in lower and not context["linkedin_url"]:
            context["linkedin_url"] = _normalize_url(token)
            context["linkedin_label"] = "linkedin"
        elif re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", token) and not context["email"]:
            context["email"] = token.replace("mailto:", "").strip(" -—|,;:")
        elif (
            not context["website_url"]
            and " " not in token
            and any(domain in lower for domain in [".com", ".dev", ".io", ".org", ".net", ".tech"])
            and "@" not in token
            and "github" not in lower
            and "linkedin" not in lower
        ):
            context["website_url"] = _normalize_url(token)
            context["website_label"] = token.replace("https://", "").replace("http://", "").strip(" -—|,;:")

    if not context["website_label"] and context["website_url"]:
        context["website_label"] = context["website_url"].replace("https://", "").replace("http://", "")

    if context["github_url"]:
        context["github_label"] = "github"
    if context["linkedin_url"]:
        context["linkedin_label"] = "linkedin"

    if not context["github_url"] and not context["github_label"] and (context["website_url"] or context["email"]):
        context["github_label"] = "github"
    if not context["linkedin_url"] and not context["linkedin_label"] and (context["website_url"] or context["email"]):
        context["linkedin_label"] = "linkedin"

    return context


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]*", text.lower()) if len(token) > 2}


def _clean_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    cleaned = re.sub(r"^[-•\*\d\.)\s]+", "", cleaned)
    return cleaned.strip('"\'` ')


def _contains_new_number(original: str, rewritten: str) -> bool:
    original_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", original))
    rewritten_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", rewritten))
    return bool(rewritten_numbers - original_numbers)


def _is_rewrite_safe(original: str, rewritten: str) -> tuple[bool, str]:
    if not rewritten:
        return False, "empty"

    original_tokens = _tokenize(original)
    rewritten_tokens = _tokenize(rewritten)

    if not rewritten_tokens:
        return False, "no_tokens"

    shared = original_tokens & rewritten_tokens
    retention_ratio = len(shared) / max(len(original_tokens), 1)
    if retention_ratio < 0.35:
        return False, "low_overlap"

    if _contains_new_number(original, rewritten):
        return False, "new_numbers"

    if len(rewritten.split()) < 6:
        return False, "too_short"

    if len(rewritten.split()) > 38:
        return False, "too_long"

    return True, "ok"


def _score_rewrite(original: str, rewritten: str, jd_requirement: str, match_score: float, used_fallback: bool) -> tuple[int, dict[str, float | int]]:
    original_tokens = _tokenize(original)
    rewritten_tokens = _tokenize(rewritten)
    jd_tokens = _tokenize(jd_requirement)

    retention = len(original_tokens & rewritten_tokens) / max(len(original_tokens), 1)
    jd_alignment = len(rewritten_tokens & jd_tokens) / max(len(jd_tokens), 1)

    base_points = int(round(max(0.0, min(1.0, float(match_score))) * 60))
    alignment_points = int(round(max(0.0, min(1.0, jd_alignment)) * 25))
    retention_points = int(round(max(0.0, min(1.0, retention)) * 15))
    penalty = 10 if used_fallback else 0

    total = max(0, min(100, base_points + alignment_points + retention_points - penalty))
    breakdown: dict[str, float | int] = {
        "base_points": base_points,
        "alignment_points": alignment_points,
        "retention_points": retention_points,
        "penalty": penalty,
        "jd_alignment": round(jd_alignment, 3),
        "retention": round(retention, 3),
    }
    return total, breakdown


def _quality_label(points: int) -> str:
    if points >= 85:
        return "high"
    if points >= 65:
        return "medium"
    return "low"


KNOWN_SKILL_TERMS = {
    "python",
    "django",
    "flask",
    "fastapi",
    "java",
    "c++",
    "c#",
    "javascript",
    "typescript",
    "node",
    "nodejs",
    "react",
    "nextjs",
    "spring",
    "springboot",
    "sql",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "git",
    "github",
    "jest",
    "playwright",
    "selenium",
    "rest",
    "graphql",
    "pandas",
    "numpy",
    "pytorch",
    "tensorflow",
}


def _normalize_skill_term(term: str) -> str:
    text = term.strip().lower().replace(" ", "")
    text = text.replace("node.js", "nodejs")
    text = text.replace("reactjs", "react")
    text = text.replace("next.js", "nextjs")
    text = text.replace("spring boot", "springboot")
    return text


def _extract_known_skills(text: str) -> set[str]:
    normalized_blob = _normalize_skill_term(text or "")
    found: set[str] = set()
    for skill in KNOWN_SKILL_TERMS:
        if skill in normalized_blob:
            found.add(skill)
    return found


def _build_parent_context(resume: dict[str, Any], section: str, parent_index: int) -> str:
    if section == "experience":
        items = resume.get("experience", [])
        if 0 <= parent_index < len(items):
            item = items[parent_index]
            return " | ".join(
                [
                    str(item.get("company", "")).strip(),
                    str(item.get("role", "")).strip(),
                    str(item.get("date", "")).strip(),
                ]
            ).strip(" |")
    if section == "projects":
        items = resume.get("projects", [])
        if 0 <= parent_index < len(items):
            item = items[parent_index]
            return " | ".join(
                [
                    str(item.get("name", "")).strip(),
                    str(item.get("technologies", "")).strip(),
                    str(item.get("date", "")).strip(),
                ]
            ).strip(" |")
    return ""


def _extract_resume_skill_pool(resume: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    parts.extend([str(item) for item in resume.get("skills", [])])
    for exp in resume.get("experience", []):
        parts.extend([str(b) for b in exp.get("bullets", [])])
    for proj in resume.get("projects", []):
        parts.append(str(proj.get("technologies", "")))
        parts.extend([str(b) for b in proj.get("bullets", [])])
    return _extract_known_skills(" ".join(parts))


def _contains_unsupported_skill(rewritten: str, allowed_skill_pool: set[str]) -> tuple[bool, str]:
    rewritten_skills = _extract_known_skills(rewritten)
    unsupported = sorted(rewritten_skills - allowed_skill_pool)
    if unsupported:
        return True, unsupported[0]
    return False, ""


def _format_skill_label(skill: str) -> str:
    mapping = {
        "nodejs": "Node.js",
        "nextjs": "Next.js",
        "springboot": "SpringBoot",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "pytorch": "PyTorch",
    }
    if skill in mapping:
        return mapping[skill]
    if skill == "c++":
        return "C++"
    if skill == "c#":
        return "C#"
    return skill.capitalize()


def _refresh_skills_from_jd(resume: dict[str, Any], jd_requirements: list[str]) -> list[str]:
    existing_lines = [str(item).strip() for item in resume.get("skills", []) if str(item).strip()]
    existing_blob = " ".join(existing_lines)
    existing_skill_set = _extract_known_skills(existing_blob)

    resume_evidence = _extract_resume_skill_pool(resume)
    jd_skill_set = _extract_known_skills(" ".join(jd_requirements or []))

    relevant = sorted((resume_evidence & jd_skill_set) - existing_skill_set)
    if not relevant:
        return existing_lines

    labels = [_format_skill_label(skill) for skill in relevant[:8]]
    updated_lines = list(existing_lines)
    updated_lines.append(f"Relevant to JD: {', '.join(labels)}")
    return updated_lines


@app.post("/parse-resume")
def parse_resume():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    session_id = str(uuid.uuid4())

    stem = Path(file.filename).stem.strip().lower().replace(" ", "-")
    safe_stem = re.sub(r"[^a-z0-9\-]+", "", stem) or "resume"
    upload_path = OUTPUT_DIR / f"{session_id}__input__{safe_stem}.pdf"
    file.save(upload_path)

    resume_data = parse_resume_pdf(upload_path)

    session = {
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "resume": resume_data,
        "jd_text": "",
        "jd_requirements": [],
        "matches": [],
    }
    _save_session(session)

    return jsonify(
        {
            "session_id": session_id,
            "name": resume_data.get("name", ""),
            "contact": resume_data.get("contact", ""),
            "experience": resume_data.get("experience", []),
            "projects": resume_data.get("projects", []),
            "skills": resume_data.get("skills", []),
            "education": resume_data.get("education", []),
        }
    )


@app.post("/analyze-jd")
def analyze_jd():
    payload = request.get_json(silent=True) or {}
    jd_text = str(payload.get("jd_text", "")).strip()
    if not jd_text:
        return jsonify({"error": "jd_text is required"}), 400

    requirements = extract_jd_requirements(jd_text)
    return jsonify({"requirements": requirements})


@app.post("/match/<session_id>")
def match_resume(session_id: str):
    try:
        session = _load_session(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404

    payload = request.get_json(silent=True) or {}
    jd_text = str(payload.get("jd_text", "")).strip()
    if not jd_text:
        return jsonify({"error": "jd_text is required"}), 400

    requirements = extract_jd_requirements(jd_text)
    bullets = _flatten_bullets(session["resume"])
    bullet_texts = [item["text"] for item in bullets]

    top_matches = best_matches(requirements, bullet_texts)

    resolved_matches: list[dict[str, Any]] = []
    for item in top_matches:
        mapping = bullets[item["bullet_index"]]
        resolved_matches.append(
            {
                "jd_index": item["jd_index"],
                "jd_requirement": item["jd_requirement"],
                "score": item["score"],
                "section": mapping["section"],
                "parent_index": mapping["parent_index"],
                "bullet_index": mapping["bullet_index"],
                "original_bullet": mapping["text"],
            }
        )

    session["jd_text"] = jd_text
    session["jd_requirements"] = requirements
    session["matches"] = resolved_matches
    _save_session(session)

    return jsonify({"session_id": session_id, "requirements": requirements, "matches": resolved_matches})


@app.post("/generate/<session_id>")
def generate(session_id: str):
    try:
        session = _load_session(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404

    if not session.get("matches"):
        return jsonify({"error": "No matches found. Run /match first."}), 400

    resume = session["resume"]
    rewritten: list[dict[str, Any]] = []
    total_points = 0
    fallback_count = 0
    jd_full = str(session.get("jd_text", "")).strip()
    jd_requirements = [str(item).strip() for item in session.get("jd_requirements", []) if str(item).strip()]
    global_skill_pool = _extract_resume_skill_pool(resume)
    resume_skills_text = " | ".join([str(item) for item in resume.get("skills", [])])

    for match_item in session["matches"]:
        original = match_item["original_bullet"]
        jd_context = match_item["jd_requirement"]
        match_score = float(match_item.get("score", 0.0))
        section = match_item["section"]
        parent_index = match_item["parent_index"]
        bullet_index = match_item["bullet_index"]

        parent_context = _build_parent_context(resume, section, parent_index)
        local_allowed = set(global_skill_pool)
        local_allowed.update(_extract_known_skills(original))
        local_allowed.update(_extract_known_skills(parent_context))

        llm_candidate = rewrite_bullet(
            original,
            jd_context,
            jd_full=jd_full,
            resume_skills=resume_skills_text,
            parent_context=parent_context,
        )
        cleaned_candidate = _clean_sentence(llm_candidate)
        is_safe, guard_reason = _is_rewrite_safe(original, cleaned_candidate)
        if is_safe:
            has_unsupported_skill, unsupported_skill = _contains_unsupported_skill(cleaned_candidate, local_allowed)
            if has_unsupported_skill:
                is_safe = False
                guard_reason = f"unsupported_skill:{unsupported_skill}"

        rewritten_bullet = cleaned_candidate if is_safe else original
        used_fallback = not is_safe
        if used_fallback:
            fallback_count += 1

        points, breakdown = _score_rewrite(original, rewritten_bullet, jd_context, match_score, used_fallback)
        total_points += points

        if section == "experience":
            resume["experience"][parent_index]["bullets"][bullet_index] = rewritten_bullet
        elif section == "projects":
            resume["projects"][parent_index]["bullets"][bullet_index] = rewritten_bullet

        rewritten.append(
            {
                "section": section,
                "parent_index": parent_index,
                "bullet_index": bullet_index,
                "original": original,
                "rewritten": rewritten_bullet,
                "jd_requirement": jd_context,
                "match_score": match_score,
                "quality_points": points,
                "quality_label": _quality_label(points),
                "used_fallback": used_fallback,
                "guardrail_reason": guard_reason,
                "points_breakdown": breakdown,
            }
        )

    resume["skills"] = _refresh_skills_from_jd(resume, jd_requirements)

    rewrite_count = len(rewritten)
    average_points = round(total_points / rewrite_count, 1) if rewrite_count else 0.0
    quality_summary = {
        "total_points": total_points,
        "average_points": average_points,
        "rewrites": rewrite_count,
        "fallback_count": fallback_count,
    }

    session["resume"] = resume
    session["rewritten"] = rewritten
    session["quality_summary"] = quality_summary
    _save_session(session)

    return jsonify({"session_id": session_id, "rewritten": rewritten, "resume": resume, "quality_summary": quality_summary})


@app.get("/export/<session_id>")
def export_resume(session_id: str):
    try:
        session = _load_session(session_id)
    except FileNotFoundError:
        return jsonify({"error": "Session not found"}), 404

    data = dict(session["resume"])
    raw_skills = data.get("skills", [])
    if isinstance(raw_skills, list):
        skill_groups = [str(skill).strip() for skill in raw_skills if str(skill).strip()]
    elif isinstance(raw_skills, str):
        skill_groups = [item.strip() for item in raw_skills.split("\n") if item.strip()]
    else:
        skill_groups = []

    data["skill_groups"] = skill_groups
    data["updated_date"] = datetime.now().strftime("%B %d, %Y")
    data.update(_extract_contact_context(data.get("contact", "")))

    try:
        pdf_path = render_resume(data, session_id)
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    if not pdf_path.exists():
        return jsonify({"error": "PDF output not found"}), 500

    return send_file(pdf_path, as_attachment=True, download_name=pdf_path.name)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)
