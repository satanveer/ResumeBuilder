import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Document, Page, pdfjs } from "react-pdf";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import {
  analyzeJD,
  exportResume,
  generateResume,
  matchResume,
  parseResume,
  type AnalyzeJDResponse,
  type GenerateResponse,
  type MatchResponse,
  type ParseResumeResponse,
  type ResumeData,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Step = 1 | 2 | 3 | 4 | 5;

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export default function App() {
  const [step, setStep] = useState<Step>(1);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [jdText, setJdText] = useState<string>("");
  const [parseData, setParseData] = useState<ParseResumeResponse | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalyzeJDResponse | null>(null);
  const [matchData, setMatchData] = useState<MatchResponse | null>(null);
  const [generateData, setGenerateData] = useState<GenerateResponse | null>(null);
  const [resumePreview, setResumePreview] = useState<ResumeData | null>(null);
  const [exportPreviewUrl, setExportPreviewUrl] = useState<string | null>(null);
  const [pdfPreviewError, setPdfPreviewError] = useState<string>("");
  const [isPdfReady, setIsPdfReady] = useState<boolean>(false);
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [pdfScale, setPdfScale] = useState<number>(1.05);
  const [error, setError] = useState<string>("");

  const updateExactPdfPreview = (blob: Blob) => {
    const url = window.URL.createObjectURL(blob);
    setExportPreviewUrl((previous) => {
      if (previous) {
        window.URL.revokeObjectURL(previous);
      }
      return url;
    });
    setPdfPreviewError("");
    setIsPdfReady(true);
  };

  const parseMutation = useMutation({
    mutationFn: parseResume,
    onSuccess: (data) => {
      setParseData(data);
      setResumePreview(mapParseToResume(data));
      setSessionId(data.session_id);
      setStep(2);
      setIsPdfReady(false);
      setPdfPreviewError("");
      setError("");
    },
    onError: (err: Error) => setError(err.message),
  });

  const analyzeMutation = useMutation({
    mutationFn: analyzeJD,
    onSuccess: (data) => {
      setAnalysisData(data);
      setStep(3);
      setError("");
    },
    onError: (err: Error) => setError(err.message),
  });

  const matchMutation = useMutation({
    mutationFn: (vars: { sessionId: string; jdText: string }) => matchResume(vars.sessionId, vars.jdText),
    onSuccess: (data) => {
      setMatchData(data);
      setStep(4);
      setError("");
    },
    onError: (err: Error) => setError(err.message),
  });

  const generateMutation = useMutation({
    mutationFn: generateResume,
    onSuccess: (data) => {
      setGenerateData(data);
      setResumePreview(data.resume);
      setStep(5);
      setIsPdfReady(false);
      setError("");
    },
    onError: (err: Error) => setError(err.message),
  });

  const previewMutation = useMutation({
    mutationFn: exportResume,
    onSuccess: (blob) => {
      updateExactPdfPreview(blob);
    },
    onError: (err: Error) => {
      setPdfPreviewError(err.message);
    },
  });

  const exportMutation = useMutation({
    mutationFn: exportResume,
    onSuccess: (blob) => {
      updateExactPdfPreview(blob);
      const a = document.createElement("a");
      a.href = window.URL.createObjectURL(blob);
      a.download = "tailored_resume.pdf";
      a.click();
      window.setTimeout(() => window.URL.revokeObjectURL(a.href), 1000);
      setError("");
    },
    onError: (err: Error) => setError(err.message),
  });

  useEffect(() => {
    return () => {
      if (exportPreviewUrl) {
        window.URL.revokeObjectURL(exportPreviewUrl);
      }
    };
  }, [exportPreviewUrl]);

  useEffect(() => {
    setPageNumber(1);
  }, [exportPreviewUrl]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }
    if (step < 2) {
      return;
    }
    if (previewMutation.isPending) {
      return;
    }
    previewMutation.mutate(sessionId);
  }, [sessionId, step]);

  const canAnalyze = useMemo(() => jdText.trim().length > 0, [jdText]);
  const canAnalyzeAction = Boolean(sessionId) && canAnalyze && !analysisData;
  const canMatchAction = Boolean(sessionId) && Boolean(analysisData) && canAnalyze;
  const canGenerateAction = Boolean(sessionId) && Boolean(matchData);
  const canPreviewAction = Boolean(sessionId) && Boolean(generateData);
  const canExportAction = Boolean(sessionId) && Boolean(generateData);

  const progressLabel = useMemo(() => {
    if (step === 1) {
      return "Waiting for resume parse";
    }
    if (step === 2) {
      return "Ready to analyze JD";
    }
    if (step === 3) {
      return "Ready to match requirements";
    }
    if (step === 4) {
      return "Ready to generate rewrite";
    }
    return "Ready for preview and export";
  }, [step]);

  const canPrevPage = pageNumber > 1;
  const canNextPage = pageNumber < numPages;

  return (
    <main className="mx-auto min-h-screen max-w-[1680px] p-4 lg:p-6">
      <div className="grid gap-4 xl:grid-cols-[460px_1fr]">
        <div className="space-y-4 xl:sticky xl:top-4 xl:h-[calc(100vh-2rem)] xl:overflow-y-auto">
          <Card>
            <CardHeader className="space-y-2">
              <CardTitle>RoleFit Local</CardTitle>
              <p className="text-sm text-slate-600">Everything on one screen: workflow + context on the left, clean PDF review on the right.</p>
            </CardHeader>
            <CardContent className="space-y-4">
              {error ? <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{error}</p> : null}

              <div className="rounded border bg-slate-50 p-3">
                <p className="text-xs font-semibold text-slate-700">Step Progress</p>
                <p className="mt-1 text-xs text-slate-600">{progressLabel}</p>
                {parseData ? (
                  <p className="mt-2 text-[11px] text-slate-500">
                    Session {sessionId.slice(0, 12)}... • Experience {parseData.experience.length} • Projects {parseData.projects.length} • Preview {isPdfReady ? "Synced" : "Pending"}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-slate-700">1) Resume PDF</label>
                <Input
                  type="file"
                  accept="application/pdf"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
                <Button onClick={() => selectedFile && parseMutation.mutate(selectedFile)} disabled={!selectedFile || parseMutation.isPending} className="w-full">
                  {parseMutation.isPending ? "Parsing..." : "Parse Resume"}
                </Button>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-slate-700">2) Job Description</label>
                <Textarea
                  placeholder="Paste job description"
                  value={jdText}
                  onChange={(event) => setJdText(event.target.value)}
                  className="min-h-[135px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <Button onClick={() => analyzeMutation.mutate(jdText)} disabled={!canAnalyzeAction || analyzeMutation.isPending}>
                  {analyzeMutation.isPending ? "Analyzing..." : "Analyze"}
                </Button>
                <Button variant="secondary" onClick={() => matchMutation.mutate({ sessionId, jdText })} disabled={!canMatchAction || matchMutation.isPending}>
                  {matchMutation.isPending ? "Matching..." : "Match"}
                </Button>
                <Button variant="secondary" onClick={() => generateMutation.mutate(sessionId)} disabled={!canGenerateAction || generateMutation.isPending}>
                  {generateMutation.isPending ? "Generating..." : "Generate"}
                </Button>
                <Button variant="secondary" onClick={() => previewMutation.mutate(sessionId)} disabled={!canPreviewAction || previewMutation.isPending}>
                  {previewMutation.isPending ? "Updating..." : "Refresh PDF"}
                </Button>
              </div>

              <Button onClick={() => exportMutation.mutate(sessionId)} disabled={!canExportAction || exportMutation.isPending} className="w-full">
                {exportMutation.isPending ? "Exporting..." : "Export PDF"}
              </Button>
              <p className="text-[11px] text-slate-500">Locked order: Parse → Analyze → Match → Generate → Refresh/Export.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Requirements</CardTitle>
            </CardHeader>
            <CardContent>
              {matchData?.matches?.length ? (
                <ul className="max-h-44 list-disc space-y-1 overflow-y-auto pr-2 pl-4 text-xs text-slate-700">
                  {matchData.matches.map((item, index) => (
                    <li key={`${item.jd_requirement}-${index}`}>
                      {item.jd_requirement} <span className="text-slate-500">({item.score.toFixed(3)})</span>
                    </li>
                  ))}
                </ul>
              ) : analysisData?.requirements?.length ? (
                <ul className="max-h-44 list-disc space-y-1 overflow-y-auto pr-2 pl-4 text-xs text-slate-700">
                  {analysisData.requirements.map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500">Run Analyze or Match to populate requirements.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Changes Made</CardTitle>
            </CardHeader>
            <CardContent>
              {generateData?.rewritten?.length ? (
                <>
                  <div className="mb-2 rounded border bg-slate-50 p-2 text-[11px] text-slate-700">
                    Total points: <span className="font-semibold">{generateData.quality_summary.total_points}</span> • Avg: <span className="font-semibold">{generateData.quality_summary.average_points}</span> • Guardrail fallbacks: <span className="font-semibold">{generateData.quality_summary.fallback_count}</span>
                  </div>
                  <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                    {generateData.rewritten.map((item, index) => {
                      const location = resolveRewriteLocation(resumePreview, item.section, item.parent_index, item.bullet_index);
                      return (
                        <div key={`${item.section}-${item.parent_index}-${item.bullet_index}-${index}`} className="rounded border p-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-xs font-medium text-slate-800">{location}</p>
                            <p className="text-[11px] text-slate-600">
                              Points: <span className="font-semibold text-slate-800">{item.quality_points}</span> • Match: {item.match_score.toFixed(3)}
                            </p>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500">Before</p>
                          <p className="text-[11px] text-slate-700">{item.original}</p>
                          <p className="mt-1 text-[11px] text-slate-500">After</p>
                          <p className="text-[11px] text-emerald-700">{item.rewritten}</p>
                          {item.used_fallback ? <p className="mt-1 text-[10px] text-amber-700">Guardrail fallback: kept original bullet ({item.guardrail_reason}).</p> : null}
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="text-xs text-slate-500">Generate a tailored resume to see rewritten bullets and locations.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-slate-50/60">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">PDF Preview</CardTitle>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => setPageNumber((prev) => Math.max(1, prev - 1))} disabled={!canPrevPage || !exportPreviewUrl}>
                  Prev
                </Button>
                <span className="text-xs text-slate-600">Page {numPages ? pageNumber : 0} / {numPages || 0}</span>
                <Button variant="secondary" onClick={() => setPageNumber((prev) => Math.min(numPages, prev + 1))} disabled={!canNextPage || !exportPreviewUrl}>
                  Next
                </Button>
                <Button variant="secondary" onClick={() => setPdfScale((prev) => Math.max(0.8, Number((prev - 0.1).toFixed(2))))} disabled={!exportPreviewUrl}>
                  -
                </Button>
                <span className="text-xs text-slate-600">{Math.round(pdfScale * 100)}%</span>
                <Button variant="secondary" onClick={() => setPdfScale((prev) => Math.min(1.5, Number((prev + 0.1).toFixed(2))))} disabled={!exportPreviewUrl}>
                  +
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="h-[calc(100vh-7.5rem)] overflow-auto bg-slate-100 p-4">
            {pdfPreviewError ? <p className="mb-3 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{pdfPreviewError}</p> : null}

            {exportPreviewUrl ? (
              <div className="flex min-h-full items-start justify-center">
                <Document
                  file={exportPreviewUrl}
                  loading={<p className="text-sm text-slate-500">Loading PDF...</p>}
                  error={<p className="text-sm text-red-600">Unable to render preview.</p>}
                  onLoadSuccess={({ numPages: loadedPages }) => {
                    setNumPages(loadedPages);
                    setPageNumber((prev) => Math.min(Math.max(prev, 1), loadedPages));
                  }}
                >
                  <Page
                    pageNumber={pageNumber}
                    scale={pdfScale}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    className="shadow-lg"
                  />
                </Document>
              </div>
            ) : (
              <div className="flex h-full min-h-[520px] items-center justify-center rounded border border-dashed bg-white text-sm text-slate-500">
                {sessionId ? "Generating exact PDF preview..." : "Parse a resume to load the preview."}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function mapParseToResume(parsed: ParseResumeResponse): ResumeData {
  return {
    name: parsed.name || "Candidate",
    contact: parsed.contact || "",
    education: parsed.education || [],
    skills: parsed.skills || [],
    experience: parsed.experience || [],
    projects: parsed.projects || [],
  };
}

function resolveRewriteLocation(
  resume: ResumeData | null,
  section: "experience" | "projects",
  parentIndex: number,
  bulletIndex: number
): string {
  if (!resume) {
    return `${section} → bullet ${bulletIndex + 1}`;
  }

  if (section === "experience") {
    const item = resume.experience[parentIndex];
    const header = item?.company || `Experience item ${parentIndex + 1}`;
    return `Experience → ${header} → Bullet ${bulletIndex + 1}`;
  }

  const item = resume.projects[parentIndex];
  const header = item?.name || `Project item ${parentIndex + 1}`;
  return `Projects → ${header} → Bullet ${bulletIndex + 1}`;
}
