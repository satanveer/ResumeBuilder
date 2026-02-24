from __future__ import annotations

from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("all-MiniLM-L6-v2")


def match(jd_lines: list[str], resume_bullets: list[str]):
    if not jd_lines or not resume_bullets:
        return []

    jd_emb = model.encode(jd_lines, convert_to_tensor=True)
    res_emb = model.encode(resume_bullets, convert_to_tensor=True)

    scores = util.cos_sim(jd_emb, res_emb)
    return scores


def best_matches(jd_lines: list[str], resume_bullets: list[str], threshold: float = 0.25) -> list[dict[str, object]]:
    scores = match(jd_lines, resume_bullets)
    if scores == []:
        return []

    output: list[dict[str, object]] = []
    for jd_idx, jd_line in enumerate(jd_lines):
        row = scores[jd_idx]
        max_val, max_idx = row.max(dim=0)
        score = float(max_val.item())
        bullet_idx = int(max_idx.item())
        output.append(
            {
                "jd_index": jd_idx,
                "jd_requirement": jd_line,
                "bullet_index": bullet_idx,
                "resume_bullet": resume_bullets[bullet_idx],
                "score": score,
            }
        )

    return output
