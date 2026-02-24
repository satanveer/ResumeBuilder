from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unicodedata
from typing import Any

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "outputs"

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def _escape_latex(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\s+", " ", value).strip()
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = value
    for source, target in replacements.items():
        escaped = escaped.replace(source, target)
    return escaped


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return _escape_latex(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    return value


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return (cleaned[:48].strip("-") or "candidate")


def render_resume(data: dict, session_id: str) -> Path:
    template = env.get_template("resume_template.tex")
    tex = template.render(data=_sanitize(data))

    candidate_slug = _slugify(str(data.get("name", "candidate")))
    base_name = f"{session_id}__{candidate_slug}__tailored_resume"
    tex_path = OUTPUT_DIR / f"{base_name}.tex"
    pdf_path = OUTPUT_DIR / f"{base_name}.pdf"

    tex_path.write_text(tex, encoding="utf-8")

    subprocess.run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(OUTPUT_DIR),
            str(tex_path),
        ],
        check=True,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )

    for ext in [".aux", ".log", ".out"]:
        (OUTPUT_DIR / f"{base_name}{ext}").unlink(missing_ok=True)

    return pdf_path
