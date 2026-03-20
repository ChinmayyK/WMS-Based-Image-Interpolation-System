import { useState, useEffect, useCallback, useRef } from "react";
import DashboardHeader from "@/components/DashboardHeader";
import MapViewer from "@/components/MapViewer";
import TimelineSlider from "@/components/TimelineSlider";
import AnimationControls from "@/components/AnimationControls";
import FrameInfoPanel from "@/components/FrameInfoPanel";
import LoadingOverlay from "@/components/LoadingOverlay";
import ErrorPanel from "@/components/ErrorPanel";
import JobSubmissionPanel from "@/components/JobSubmissionPanel";
import ExportResultsPanel from "@/components/ExportResultsPanel";
import { MOCK_FRAMES } from "@/lib/mock-data";
import { getRuntimeSummary } from "@/lib/frame-status";
import { SatelliteFrame, PlaybackSpeed, ComparisonMode, DataSource, RuntimeDiagnostics } from "@/lib/types";

type InterpolationPair = {
  frame1: SatelliteFrame;
  frame2: SatelliteFrame;
  gapMinutes: number;
};

const Index = () => {
  const [frames, setFrames] = useState<SatelliteFrame[]>(MOCK_FRAMES);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1.0);
  const [opacity, setOpacity] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [jobPhase, setJobPhase] = useState<string>("");
  const [dataSource, setDataSource] = useState<DataSource>("demo");
  const [comparisonMode, setComparisonMode] = useState<ComparisonMode>("off");
  const [toggleView, setToggleView] = useState<"original" | "generated">("original");
  const [showOverlay, setShowOverlay] = useState(true);
  const [showRawSensorGaps, setShowRawSensorGaps] = useState(false);
  const [showConfidence, setShowConfidence] = useState(false);
  const [showClouds, setShowClouds] = useState(false);
  const [showVectors, setShowVectors] = useState(false);
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState<RuntimeDiagnostics | null>(null);
  const [interpolationNotice, setInterpolationNotice] = useState<string | null>(null);
  const [exportInProgress, setExportInProgress] = useState(false);
  const [evaluationInProgress, setEvaluationInProgress] = useState(false);
  const [exportData, setExportData] = useState<any>(null);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState(false);
  const intervalRef = useRef<number | null>(null);

  const currentFrame = frames[currentIndex];
  // Initial Demo loading simulation
  useEffect(() => {
    if (dataSource !== "demo") return;
    let progress = 0;
    const loadInterval = window.setInterval(() => {
      progress += Math.random() * 25 + 10;
      if (progress >= 100) {
        progress = 100;
        setLoadProgress(100);
        setTimeout(() => setIsLoading(false), 300);
        clearInterval(loadInterval);
      } else {
        setLoadProgress(Math.min(progress, 100));
      }
    }, 400);
    return () => clearInterval(loadInterval);
  }, [dataSource, frames]);

  // Background Job Polling
  useEffect(() => {
    if (!currentJobId) return;
    let pollInterval: number | null = null;
    let eventSource: EventSource | null = null;
    let settled = false;

    const hydrateCompletedJob = async () => {
      try {
        const [framesRes, diagRes] = await Promise.all([
          fetch(`/api/v1/jobs/${currentJobId}/frames`),
          fetch("/api/diagnostics/status"),
        ]);
        const framesData = await framesRes.json();
        if (framesRes.ok && framesData.status === "success") {
          setFrames(framesData.frames);
          setCurrentIndex(0);
        }
        if (diagRes.ok) {
          setRuntimeDiagnostics(await diagRes.json());
        }
        setTimeout(() => {
          setIsLoading(false);
        }, 500);
      } catch (err) {
        console.error(err);
      }
    };

    const applyJobUpdate = async (job: any) => {
      setLoadProgress(job.progress || 0);
      setJobPhase(job.message || job.phase || "Processing...");

      if (settled) return;
      if (job.status === "COMPLETED") {
        settled = true;
        if (pollInterval) clearInterval(pollInterval);
        eventSource?.close();
        await hydrateCompletedJob();
      } else if (job.status === "FAILED") {
        settled = true;
        if (pollInterval) clearInterval(pollInterval);
        eventSource?.close();
        setIsLoading(false);
        setError(job.error || "Job failed");
      }
    };

    const startPollingFallback = () => {
      if (pollInterval !== null) return;
      const checkStatus = async () => {
        try {
          const res = await fetch(`/api/v1/jobs/${currentJobId}/status`);
          if (!res.ok) throw new Error("Job status check failed");
          const data = await res.json();
          await applyJobUpdate(data.job);
        } catch (err) {
          console.error(err);
        }
      };
      pollInterval = window.setInterval(checkStatus, 1500);
      void checkStatus();
    };

    try {
      eventSource = new EventSource(`/api/v1/jobs/${currentJobId}/stream`);
      eventSource.onmessage = async (event: MessageEvent<string>) => {
        const data = JSON.parse(event.data);
        await applyJobUpdate(data.job);
      };
      eventSource.addEventListener("status", async (event: MessageEvent<string>) => {
        const data = JSON.parse(event.data);
        await applyJobUpdate(data.job);
      });
      eventSource.onerror = () => {
        eventSource?.close();
        startPollingFallback();
      };
    } catch (err) {
      console.error(err);
      startPollingFallback();
    }

    return () => {
      if (pollInterval) clearInterval(pollInterval);
      eventSource?.close();
    };
  }, [currentJobId]);

  useEffect(() => {
    const pair = resolveInterpolationPair(frames, currentIndex);
    setInterpolationNotice(buildInterpolationNotice(dataSource, currentFrame, pair));
  }, [dataSource, currentFrame, frames, currentIndex]);

  const goNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % frames.length);
  }, [frames.length]);

  const goPrev = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + frames.length) % frames.length);
  }, [frames.length]);

  useEffect(() => {
    if (isPlaying && frames.length > 0) {
      intervalRef.current = window.setInterval(() => {
        goNext();
      }, 1000 / speed);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isPlaying, speed, goNext, frames.length]);

  const fetchFromApi = useCallback(async (refreshObserved = false) => {
    setIsLoading(true);
    setLoadProgress(0);
    setError(null);

    try {
      if (refreshObserved) {
        setLoadProgress(20);
        const ingestResponse = await fetch("/api/frames/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        const ingestPayload = await ingestResponse.json();
        if (!ingestResponse.ok) {
          throw new Error(ingestPayload.detail || `GOES ingest failed (${ingestResponse.status})`);
        }
      }

      setLoadProgress(refreshObserved ? 55 : 30);
      const [framesResponse, diagnosticsResponse] = await Promise.all([
        fetch("/api/frames"),
        fetch("/api/diagnostics/status"),
      ]);

      if (!framesResponse.ok) {
        throw new Error(`API returned ${framesResponse.status}`);
      }

      setLoadProgress(75);
      const data = await framesResponse.json();
      const diagnosticsData = diagnosticsResponse.ok ? await diagnosticsResponse.json() : null;

      if (data.status === "success" && data.frames?.length > 0) {
        setFrames(data.frames);
        setRuntimeDiagnostics(diagnosticsData);
        setCurrentIndex(0);
        setLoadProgress(100);
        setTimeout(() => setIsLoading(false), 300);
      } else {
        throw new Error("No frames returned from API");
      }
    } catch (err) {
      setIsLoading(false);
      setError(
        err instanceof Error
          ? `API Error: ${err.message}`
          : "Unable to fetch frames. Check backend connection."
      );
    }
  }, []);

  const handleToggleDataSource = useCallback(() => {
    const next = dataSource === "demo" ? "api" : "demo";
    setDataSource(next);
    if (next === "api") {
      setFrames([]); // Clear frames to trigger the form
      setIsLoading(false);
      setError(null);
      setRuntimeDiagnostics(null);
      setCurrentJobId(null);
      setExportData(null);
    } else {
      setError(null);
      setFrames(MOCK_FRAMES);
      setRuntimeDiagnostics(null);
      setCurrentJobId(null);
      setExportData(null);
      setCurrentIndex(0);
      setIsLoading(true);
      setLoadProgress(0);
      setTimeout(() => {
        setLoadProgress(100);
        setTimeout(() => setIsLoading(false), 200);
      }, 800);
    }
  }, [dataSource, fetchFromApi]);

  const handleRetry = useCallback(() => {
    if (dataSource === "api") {
      setError(null);
      setIsLoading(false);
      setFrames([]);
    } else {
      handleToggleDataSource();
      handleToggleDataSource();
    }
  }, [dataSource, handleToggleDataSource]);

  const handleJobSubmit = async (req: any) => {
    setIsLoading(true);
    setLoadProgress(0);
    setError(null);
    setJobPhase("Initializing Job...");
    setExportData(null);
    
    try {
      const res = await fetch("/api/v1/jobs/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to submit job");
      setCurrentJobId(data.job_id);
    } catch(err) {
      setIsLoading(false);
      setError(err instanceof Error ? err.message : "Submission failed");
    }
  };

  const handleJobExport = async () => {
    if (!currentJobId) return;
    setExportInProgress(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/jobs/${currentJobId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Export failed");
      setExportData(data.export);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExportInProgress(false);
    }
  };

  const handleGenerateInterpolation = useCallback(async () => {
    const pair = resolveInterpolationPair(frames, currentIndex);
    if (dataSource !== "api" || !pair) {
      return;
    }

    if (pair.gapMinutes > 30) {
      setInterpolationNotice("Interpolation disabled: gap exceeds 30 minutes");
      return;
    }

    try {
      setInterpolationNotice(`Generating recursive midpoint frames for ${pair.gapMinutes.toFixed(1)} minute gap…`);
      const response = await fetch("/api/frames/interpolate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frame1_id: pair.frame1.timestamp,
          frame2_id: pair.frame2.timestamp,
          steps: 3,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Interpolation failed (${response.status})`);
      }
      await fetchFromApi(false);
      setInterpolationNotice(
        `Interpolation completed using recursive bisection between ${pair.frame1.timestamp} and ${pair.frame2.timestamp}.`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Interpolation failed";
      setInterpolationNotice(message);
      setError(message);
    }
  }, [dataSource, currentIndex, frames, fetchFromApi]);

  const handleExportVideo = useCallback(async () => {
    try {
      setExportInProgress(true);
      setError(null);
      const response = await fetch("/api/video/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frames,
          fps: 15,
          raw_mode: showRawSensorGaps,
          job_name: dataSource === "api" ? "api_sequence_export" : "demo_sequence_export",
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Export failed (${response.status})`);
      }
      setRuntimeDiagnostics((prev) => ({
        ...(prev ?? {}),
        export: payload.export,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExportInProgress(false);
    }
  }, [frames, showRawSensorGaps, dataSource]);

  const handleRunEvaluation = useCallback(async () => {
    try {
      setEvaluationInProgress(true);
      setError(null);
      const response = await fetch("/api/evaluation/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rerun: true }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Evaluation failed (${response.status})`);
      }
      setRuntimeDiagnostics((prev) => ({
        ...(prev ?? {}),
        evaluation: payload.evaluation,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setEvaluationInProgress(false);
    }
  }, []);

  const pair = resolveInterpolationPair(frames, currentIndex);
  const nearestObserved = resolveNearestObservedFrame(frames, currentIndex);
  const interpolationDisabled = dataSource !== "api" || !pair || pair.gapMinutes > 30;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background text-foreground selection:bg-primary/30">
      <DashboardHeader
        dataSource={dataSource}
        onToggleDataSource={handleToggleDataSource}
        showRawSensorGaps={showRawSensorGaps}
        runtimeSummary={getRuntimeSummary(runtimeDiagnostics)}
      />

      <main className="flex-1 relative w-full h-full min-h-0 bg-map-bg">
        <div className="absolute inset-0 z-0">
          {comparisonMode === "split" && frames.length > 0 ? (
            <div className="flex w-full h-full gap-2 p-2 pt-4">
              <div className="flex-1 relative rounded-lg overflow-hidden border border-white/5">
                <div className="absolute top-3 left-3 z-20 glass px-2 py-1 rounded text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
                  Original
                </div>
                <MapViewer
                  opacity={opacity}
                  showOverlay={showOverlay}
                  onToggleOverlay={() => setShowOverlay(!showOverlay)}
                  showRawSensorGaps={showRawSensorGaps}
                  onToggleRawSensorGaps={() => setShowRawSensorGaps(!showRawSensorGaps)}
                  showConfidence={showConfidence}
                  onToggleConfidence={() => setShowConfidence(!showConfidence)}
                  showClouds={showClouds}
                  onToggleClouds={() => setShowClouds(!showClouds)}
                  showVectors={showVectors}
                  onToggleVectors={() => setShowVectors(!showVectors)}
                  currentFrame={nearestObserved || currentFrame}
                  comparisonMode="split"
                  runtimeDiagnostics={runtimeDiagnostics}
                />
              </div>
              <div className="flex-1 relative rounded-lg overflow-hidden border border-primary/20">
                <div className="absolute top-3 left-3 z-20 glass px-2 py-1 rounded text-[10px] font-mono text-primary uppercase tracking-widest">
                  AI Processed
                </div>
                <MapViewer
                  opacity={opacity}
                  showOverlay={showOverlay}
                  onToggleOverlay={() => setShowOverlay(!showOverlay)}
                  showRawSensorGaps={showRawSensorGaps}
                  onToggleRawSensorGaps={() => setShowRawSensorGaps(!showRawSensorGaps)}
                  showConfidence={showConfidence}
                  onToggleConfidence={() => setShowConfidence(!showConfidence)}
                  showClouds={showClouds}
                  onToggleClouds={() => setShowClouds(!showClouds)}
                  showVectors={showVectors}
                  onToggleVectors={() => setShowVectors(!showVectors)}
                  currentFrame={currentFrame}
                  comparisonMode="split"
                  runtimeDiagnostics={runtimeDiagnostics}
                />
              </div>
            </div>
          ) : (
            <MapViewer
              opacity={opacity}
              showOverlay={showOverlay}
              onToggleOverlay={() => setShowOverlay(!showOverlay)}
              showRawSensorGaps={showRawSensorGaps}
              onToggleRawSensorGaps={() => setShowRawSensorGaps(!showRawSensorGaps)}
              showConfidence={showConfidence}
              onToggleConfidence={() => setShowConfidence(!showConfidence)}
              showClouds={showClouds}
              onToggleClouds={() => setShowClouds(!showClouds)}
              showVectors={showVectors}
              onToggleVectors={() => setShowVectors(!showVectors)}
              currentFrame={comparisonMode === "toggle" && toggleView === "original" ? (nearestObserved || currentFrame) : currentFrame}
              comparisonMode={comparisonMode}
              runtimeDiagnostics={runtimeDiagnostics}
            />
          )}

          {!currentFrame && !error && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-md z-50">
              <div className="flex flex-col items-center gap-4">
                <div className="w-12 h-12 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                <p className="text-xs tracking-[0.2em] uppercase font-mono text-primary animate-pulse">Establishing Satellite Link...</p>
              </div>
            </div>
          )}
        </div>

        {/* Floating Modals / Overlays */}
        {dataSource === "api" && frames.length === 0 && !currentJobId && !isLoading && !error && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 overflow-y-auto">
            <JobSubmissionPanel onSubmit={handleJobSubmit} isSubmitting={isLoading} />
          </div>
        )}
        
        {isLoading && (
          <div className="absolute inset-0 z-50">
            <LoadingOverlay
              message={jobPhase || (loadProgress < 100 ? "INITIALIZING DATA STREAM…" : "SYNCHRONIZING SENSORS…")}
              progress={loadProgress}
            />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-50 p-4 pointer-events-none flex items-start justify-center pt-20">
            <div className="pointer-events-auto">
              <ErrorPanel message={error} onRetry={handleRetry} />
            </div>
          </div>
        )}

        {/* Timeline Bottom Bar */}
        {!error && !isLoading && frames.length > 0 && (
          <div className="absolute bottom-0 left-0 right-0 z-40 p-4">
            <div className="glass rounded-xl p-4 shadow-2xl border border-white/10 md:px-6">
              <TimelineSlider
                frames={frames}
                currentIndex={currentIndex}
                onIndexChange={setCurrentIndex}
              />
              <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
                <AnimationControls
                  isPlaying={isPlaying}
                  onPlayPause={() => setIsPlaying(!isPlaying)}
                  onNext={goNext}
                  onPrev={goPrev}
                  speed={speed}
                  onSpeedChange={setSpeed}
                  opacity={opacity}
                  onOpacityChange={setOpacity}
                  onInterpolate={handleGenerateInterpolation}
                  interpolationDisabled={interpolationDisabled}
                  interpolationNotice={interpolationNotice}
                  onExportVideo={handleExportVideo}
                  exportDisabled={frames.length === 0}
                  exportInProgress={exportInProgress}
                  onRunEvaluation={handleRunEvaluation}
                  evaluationInProgress={evaluationInProgress}
                />
              </div>
            </div>
          </div>
        )}

        {/* Top Right Floating Export Panel (if any) */}
        {dataSource === "api" && currentJobId && exportData && (
          <div className="absolute top-24 right-4 z-40 w-80">
            <ExportResultsPanel
              exportData={exportData}
              isExporting={exportInProgress}
              onExport={handleJobExport}
              jobCompleted={!isLoading && frames.length > 0}
            />
          </div>
        )}

        {/* Top Right Toggle button for Diagnostics */}
        {frames.length > 0 && (
          <button
            onClick={() => setIsDiagnosticsOpen(!isDiagnosticsOpen)}
            className="absolute top-4 right-4 z-50 glass h-10 px-4 rounded-lg border border-white/10 flex items-center gap-2 hover:bg-white/10 text-[10px] font-mono font-bold tracking-widest text-primary transition-all shadow-xl"
          >
            {isDiagnosticsOpen ? "CLOSE PANEL" : "ADVANCED "}
            <div className={`w-2 h-2 rounded-full ${isDiagnosticsOpen ? 'bg-confidence-low' : 'bg-primary animate-pulse'}`} />
          </button>
        )}

        {/* Slide-in Diagnostics Panel */}
        <div 
          className={`absolute top-0 right-0 h-full w-[380px] z-40 transition-transform duration-500 ease-in-out p-4 pb-44 ${
            isDiagnosticsOpen && frames.length > 0 ? "translate-x-0" : "translate-x-full"
          }`}
        >
          {currentFrame && (
            <div className="h-full mt-14 shadow-2xl rounded-xl overflow-hidden glass border border-white/10">
              <FrameInfoPanel
                frame={currentFrame}
                frameIndex={currentIndex}
                totalFrames={frames.length}
                comparisonMode={comparisonMode}
                onComparisonModeChange={setComparisonMode}
                toggleView={toggleView}
                onToggleViewChange={setToggleView}
                isDemoMode={dataSource === "demo"}
                showRawSensorGaps={showRawSensorGaps}
                runtimeDiagnostics={runtimeDiagnostics}
                interpolationNotice={interpolationNotice}
              />
            </div>
          )}
        </div>

      </main>
    </div>
  );
};

function resolveNearestObservedFrame(frames: SatelliteFrame[], currentIndex: number): SatelliteFrame | null {
  if (!frames.length || currentIndex < 0 || currentIndex >= frames.length) return null;
  const current = frames[currentIndex];
  if (current.isOriginal) return current;
  
  let offset = 1;
  while (currentIndex - offset >= 0 || currentIndex + offset < frames.length) {
    if (currentIndex - offset >= 0) {
      const leftFrame = frames[currentIndex - offset];
      if (leftFrame.isOriginal) return leftFrame;
    }
    if (currentIndex + offset < frames.length) {
      const rightFrame = frames[currentIndex + offset];
      if (rightFrame.isOriginal) return rightFrame;
    }
    offset++;
  }
  return current;
}

function resolveInterpolationPair(frames: SatelliteFrame[], currentIndex: number): InterpolationPair | null {
  const currentFrame = frames[currentIndex];
  if (!currentFrame) {
    return null;
  }

  if (currentFrame.sourceFrames && currentFrame.sourceFrames.length === 2) {
    const frame1 = frames.find((frame) => frame.timestamp === currentFrame.sourceFrames?.[0] && frame.isOriginal);
    const frame2 = frames.find((frame) => frame.timestamp === currentFrame.sourceFrames?.[1] && frame.isOriginal);
    const gapMinutes = computeGapMinutes(currentFrame.sourceFrames[0], currentFrame.sourceFrames[1]);
    if (frame1 && frame2 && gapMinutes !== null) {
      return { frame1, frame2, gapMinutes };
    }
  }

  if (currentFrame.isOriginal) {
    const nextObserved = frames.slice(currentIndex + 1).find((frame) => frame.isOriginal);
    const gapMinutes = nextObserved ? computeGapMinutes(currentFrame.timestamp, nextObserved.timestamp) : null;
    if (nextObserved && gapMinutes !== null) {
      return { frame1: currentFrame, frame2: nextObserved, gapMinutes };
    }
  }

  const previousObserved = [...frames.slice(0, currentIndex)].reverse().find((frame) => frame.isOriginal);
  const nextObserved = frames.slice(currentIndex + 1).find((frame) => frame.isOriginal);
  const gapMinutes = previousObserved && nextObserved
    ? computeGapMinutes(previousObserved.timestamp, nextObserved.timestamp)
    : null;
  if (previousObserved && nextObserved && gapMinutes !== null) {
    return { frame1: previousObserved, frame2: nextObserved, gapMinutes };
  }
  return null;
}

function buildInterpolationNotice(
  dataSource: DataSource,
  currentFrame: SatelliteFrame | undefined,
  selectedPair: InterpolationPair | null,
): string | null {
  if (dataSource !== "api") {
    return "Interpolation is available in API mode.";
  }
  if (!selectedPair) {
    return currentFrame?.placeholderReason ?? "Select an observed pair to interpolate.";
  }
  if (selectedPair.gapMinutes > 30) {
    return "Interpolation disabled: gap exceeds 30 minutes";
  }
  return `Recursive bisection ready for ${selectedPair.gapMinutes.toFixed(1)} minute gap.`;
}

function computeGapMinutes(left: string, right: string): number | null {
  const leftMs = parseTimestamp(left);
  const rightMs = parseTimestamp(right);
  if (leftMs === null || rightMs === null) {
    return null;
  }
  return Math.abs(rightMs - leftMs) / 60000;
}

function parseTimestamp(value: string): number | null {
  if (!value) {
    return null;
  }
  if (value.includes("T")) {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const normalized = isDateOnly ? `${value}T00:00:00Z` : `${value.replace(" ", "T")}:00Z`;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

export default Index;
