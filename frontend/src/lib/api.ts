const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:5001";

export type EducationItem = {
  school: string;
  degree: string;
  date: string;
  detail?: string;
};

export type ExperienceItem = {
  company: string;
  role: string;
  date: string;
  bullets: string[];
};

export type ProjectItem = {
  name: string;
  technologies?: string;
  link?: string;
  link_label?: string;
  date: string;
  bullets: string[];
};

export type ResumeData = {
  name: string;
  contact: string;
  education: EducationItem[];
  skills: string[];
  experience: ExperienceItem[];
  projects: ProjectItem[];
};

export type ParseResumeResponse = {
  session_id: string;
  name?: string;
  contact?: string;
  experience: ExperienceItem[];
  projects: ProjectItem[];
  skills: string[];
  education: EducationItem[];
};

export type AnalyzeJDResponse = {
  requirements: string[];
};

export type MatchResponse = {
  session_id: string;
  requirements: string[];
  matches: Array<{
    jd_index: number;
    jd_requirement: string;
    score: number;
    section: "experience" | "projects";
    parent_index: number;
    bullet_index: number;
    original_bullet: string;
  }>;
};

export type GenerateResponse = {
  session_id: string;
  rewritten: Array<{
    section: "experience" | "projects";
    parent_index: number;
    bullet_index: number;
    original: string;
    rewritten: string;
    jd_requirement: string;
    match_score: number;
    quality_points: number;
    quality_label: "high" | "medium" | "low";
    used_fallback: boolean;
    guardrail_reason: string;
    points_breakdown: {
      base_points: number;
      alignment_points: number;
      retention_points: number;
      penalty: number;
      jd_alignment: number;
      retention: number;
    };
  }>;
  quality_summary: {
    total_points: number;
    average_points: number;
    rewrites: number;
    fallback_count: number;
  };
  resume: ResumeData;
};

async function parseJson<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload as T;
}

export async function parseResume(file: File): Promise<ParseResumeResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/parse-resume`, {
    method: "POST",
    body: formData,
  });
  return parseJson<ParseResumeResponse>(response);
}

export async function analyzeJD(jdText: string): Promise<AnalyzeJDResponse> {
  const response = await fetch(`${API_BASE}/analyze-jd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText }),
  });
  return parseJson<AnalyzeJDResponse>(response);
}

export async function matchResume(sessionId: string, jdText: string): Promise<MatchResponse> {
  const response = await fetch(`${API_BASE}/match/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText }),
  });
  return parseJson<MatchResponse>(response);
}

export async function generateResume(sessionId: string): Promise<GenerateResponse> {
  const response = await fetch(`${API_BASE}/generate/${sessionId}`, {
    method: "POST",
  });
  return parseJson<GenerateResponse>(response);
}

export async function exportResume(sessionId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/export/${sessionId}`);
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.error || "Export failed");
  }
  return response.blob();
}
