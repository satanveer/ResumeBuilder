from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import re

import pdfplumber


@dataclass
class EducationEntry:
    school: str
    degree: str
    date: str
    detail: str


@dataclass
class ExperienceEntry:
    company: str
    role: str
    date: str
    bullets: list[str]


@dataclass
class ProjectEntry:
    name: str
    technologies: str
    link: str
    link_label: str
    date: str
    bullets: list[str]


def _extract_date_suffix(text: str) -> tuple[str, str]:
    patterns = [
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*(?:-|--|to|–|—)\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$",
        r"\d{4}\s*(?:-|--|to|–|—)\s*\d{4}$",
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$",
        r"\d{4}$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            start = match.start()
            return text[:start].strip(" -|—"), text[start:].strip(" -|—")
    return text.strip(), ""


def _extract_lines(pdf_path: Path) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                normalized = line.strip()
                if normalized:
                    lines.append(normalized)
    return lines


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    section_aliases = {
        "education": {"education"},
        "skills": {"skills", "technical skills"},
        "experience": {"experience", "work experience", "professional experience"},
        "projects": {"projects", "project"},
    }

    sections: dict[str, list[str]] = {
        "header": [],
        "education": [],
        "skills": [],
        "experience": [],
        "projects": [],
    }
    current = "header"

    for line in lines:
        normalized = line.strip()
        lowered = normalized.lower()
        found = None
        remainder = ""

        for key, aliases in section_aliases.items():
            for alias in aliases:
                if lowered == alias or lowered.startswith(f"{alias}:") or lowered.startswith(f"{alias} "):
                    found = key
                    remainder = normalized[len(alias) :].lstrip(" :|-\t")
                    break
            if found:
                break

        if found:
            current = found
            if remainder:
                sections[current].append(remainder)
            continue

        sections[current].append(line)

    return sections


def _parse_header(header_lines: list[str]) -> tuple[str, str]:
    if not header_lines:
        return "Candidate", ""

    section_markers = ["education", "skills", "experience", "projects"]

    if len(header_lines) == 1:
        raw = header_lines[0]
        lowered = raw.lower()
        cutoff = len(raw)
        for marker in section_markers:
            idx = lowered.find(marker)
            if idx != -1:
                cutoff = min(cutoff, idx)
        trimmed = raw[:cutoff].strip(" -|—")

        if not trimmed:
            return "Candidate", ""

        tokens = [token.strip() for token in trimmed.replace("—", "|").split("|") if token.strip()]
        if not tokens:
            return trimmed, ""

        if len(tokens) == 1:
            single = tokens[0]
            lower_single = single.lower()
            marker_indexes = [
                idx
                for idx in [
                    lower_single.find("github"),
                    lower_single.find("linkedin"),
                    lower_single.find("http"),
                    lower_single.find("www."),
                    lower_single.find("@"),
                ]
                if idx > 0
            ]
            if marker_indexes:
                cut = min(marker_indexes)
                name_part = single[:cut].strip(" -|—")
                contact_part = single[cut:].strip(" -|—")
                if name_part and contact_part:
                    return name_part, contact_part

        def _looks_like_contact(token: str) -> bool:
            lower = token.lower()
            return any(
                marker in lower
                for marker in ["@", "http", "www.", "linkedin", "github", ".com", ".io", ".dev", ".org", ".net"]
            )

        name_tokens: list[str] = []
        contact_tokens: list[str] = []
        hit_contact = False
        for token in tokens:
            if _looks_like_contact(token):
                hit_contact = True
            if hit_contact:
                contact_tokens.append(token)
            else:
                name_tokens.append(token)

        name = " ".join(name_tokens).strip() or tokens[0]
        contact = " | ".join(contact_tokens).strip()
        return name, contact

    first = header_lines[0].strip()
    lower_first = first.lower()
    markers = ["github", "linkedin", "http", "www.", "@", ".com", ".io", ".dev", ".org", ".net"]
    idxs = [lower_first.find(marker) for marker in markers if lower_first.find(marker) > 0]
    if idxs:
        cut = min(idxs)
        name = first[:cut].strip(" -|—")
        first_contact = first[cut:].strip(" -|—")
        remainder_contact = " | ".join(header_lines[1:3]).strip()
        contact = " | ".join([part for part in [first_contact, remainder_contact] if part])
        return name or "Candidate", contact

    name = first
    contact = " | ".join(header_lines[1:3])
    return name, contact


def _parse_skills(skill_lines: list[str]) -> list[str]:
    skills: list[str] = []
    for line in skill_lines:
        normalized = line.strip()
        if not normalized:
            continue
        if ":" in normalized:
            skills.append(normalized)
            continue

        parts = [part.strip() for part in normalized.replace(";", ",").split(",")]
        skills.extend([part for part in parts if part])
    seen = set()
    unique = []
    for skill in skills:
        key = skill.lower()
        if key not in seen:
            seen.add(key)
            unique.append(skill)
    return unique


def _looks_like_bullet(line: str) -> bool:
    return line.startswith(("-", "•", "*"))


def _strip_bullet(line: str) -> str:
    return line.lstrip("-•* ").strip()


def _chunk_entries(lines: list[str], default_title: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if "|" in line and current:
            chunks.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        chunks.append(current)
    if not chunks and lines:
        chunks = [lines]
    if not chunks:
        chunks = [[default_title]]
    return chunks


def _parse_experience(lines: list[str]) -> list[dict[str, Any]]:
    if not lines:
        return []

    chunks = _chunk_entries(lines, "Experience")
    experience: list[ExperienceEntry] = []

    for chunk in chunks:
        header = chunk[0]
        company = header
        role = ""
        date = ""

        if "|" in header:
            parts = [part.strip() for part in header.split("|")]
            company = parts[0] if len(parts) > 0 else company
            role = parts[1] if len(parts) > 1 else role
            date = parts[2] if len(parts) > 2 else date

        bullets = [_strip_bullet(line) for line in chunk[1:] if _looks_like_bullet(line)]
        if not bullets:
            bullets = [line for line in chunk[1:] if line.strip()]

        experience.append(
            ExperienceEntry(
                company=company,
                role=role,
                date=date,
                bullets=bullets,
            )
        )

    return [asdict(entry) for entry in experience]


def _parse_projects(lines: list[str]) -> list[dict[str, Any]]:
    if not lines:
        return []

    chunks = _chunk_entries(lines, "Project")
    projects: list[ProjectEntry] = []

    for chunk in chunks:
        header = chunk[0]
        name = header
        technologies = ""
        link = ""
        link_label = ""
        date = ""
        if "|" in header:
            parts = [part.strip() for part in header.split("|")]
            name = parts[0] if len(parts) > 0 else name
            if len(parts) == 2:
                left, right = parts[0], parts[1]
                _, date_guess = _extract_date_suffix(right)
                if date_guess:
                    date = right
                else:
                    technologies = right
            elif len(parts) >= 3:
                technologies = parts[1]
                date = parts[2]
                if len(parts) > 3:
                    maybe_link = parts[3]
                    if "http" in maybe_link.lower() or "www." in maybe_link.lower():
                        link = maybe_link
                    elif "link" in maybe_link.lower():
                        link_label = "link"

        if date.lower().startswith("link "):
            date = date[5:].strip()
            if not link_label:
                link_label = "link"

        date = date.strip("| ")

        if not date:
            name_guess, date_guess = _extract_date_suffix(name)
            if date_guess:
                name = name_guess
                date = date_guess

        if not link:
            url_match = re.search(r"https?://\S+", header)
            if url_match:
                link = url_match.group(0)

        if not link_label and re.search(r"\blink\b", header, flags=re.IGNORECASE):
            link_label = "link"

        bullets = [_strip_bullet(line) for line in chunk[1:] if _looks_like_bullet(line)]
        if not bullets:
            bullets = [line for line in chunk[1:] if line.strip()]

        projects.append(
            ProjectEntry(
                name=name,
                technologies=technologies,
                link=link,
                link_label=link_label,
                date=date,
                bullets=bullets,
            )
        )

    return [asdict(entry) for entry in projects]


def _parse_education(lines: list[str]) -> list[dict[str, str]]:
    if not lines:
        return []

    entries: list[EducationEntry] = []

    if any("|" in line for line in lines):
        for line in lines:
            parts = [part.strip() for part in line.split("|")]
            school = parts[0] if len(parts) > 0 else ""
            degree = parts[1] if len(parts) > 1 else ""
            date = parts[2] if len(parts) > 2 else ""
            detail = parts[3] if len(parts) > 3 else ""
            entries.append(EducationEntry(school=school, degree=degree, date=date, detail=detail))
        return [asdict(entry) for entry in entries]

    idx = 0
    while idx < len(lines):
        first = lines[idx].strip()
        school, date = _extract_date_suffix(first)

        degree = ""
        detail = ""
        if idx + 1 < len(lines):
            second = lines[idx + 1].strip()
            if "cgpa" in second.lower():
                split_key = "Current CGPA:"
                if split_key in second:
                    left, right = second.split(split_key, 1)
                    degree = left.strip()
                    detail = f"Current CGPA: {right.strip()}"
                else:
                    degree = second
            elif "percentage" in second.lower():
                split_key = "Percentage:"
                if split_key in second:
                    left, right = second.split(split_key, 1)
                    degree = left.strip()
                    detail = f"Percentage: {right.strip()}"
                else:
                    degree = second
            elif "|" not in second:
                degree = second

        entries.append(EducationEntry(school=school, degree=degree, date=date, detail=detail))
        idx += 2 if degree else 1

    return [asdict(entry) for entry in entries]


def parse_resume_pdf(pdf_path: Path) -> dict[str, Any]:
    lines = _extract_lines(pdf_path)
    sections = _split_sections(lines)

    name, contact = _parse_header(sections["header"])
    skills = _parse_skills(sections["skills"])

    experience = _parse_experience(sections["experience"])
    projects = _parse_projects(sections["projects"])

    if not experience and not projects:
        fallback_bullets = [
            _strip_bullet(line)
            for line in lines
            if _looks_like_bullet(line) or line.lower().startswith(("built", "developed", "implemented", "improved", "designed"))
        ]
        if fallback_bullets:
            experience = [
                {
                    "company": "Experience",
                    "role": "",
                    "date": "",
                    "bullets": fallback_bullets,
                }
            ]

    parsed = {
        "name": name,
        "contact": contact,
        "experience": experience,
        "projects": projects,
        "skills": skills,
        "education": _parse_education(sections["education"]),
    }

    return parsed
