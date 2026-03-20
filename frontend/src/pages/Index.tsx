import { useState, useEffect, useCallback, useRef } from "react";
import DashboardHeader from "@/components/DashboardHeader";
import MapViewer from "@/components/MapViewer";
import TimelineSlider from "@/components/TimelineSlider";
import AnimationControls from "@/components/AnimationControls";
import FrameInfoPanel from "@/components/FrameInfoPanel";
import LoadingOverlay from "@/components/LoadingOverlay";
import ErrorPanel from "@/components/ErrorPanel";
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
  const intervalRef = useRef<number | null>(null);

  const currentFrame = frames[currentIndex];
  const selectedPair = resolveInterpolationPair(frames, currentIndex);

  useEffect(() => {
    let progress = 0;
    const loadInterval = setInterval(() => {
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
  }, []);

  useEffect(() => {
    setInterpolationNotice(buildInterpolationNotice(dataSource, currentFrame, selectedPair));
  }, [dataSource, currentFrame, selectedPair]);

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

  const fetchFromApi = useCallback(async () => {
    setIsLoading(true);
    setLoadProgress(0);
    setError(null);

    try {
      setLoadProgress(30);
      const [framesResponse, diagnosticsResponse] = await Promise.all([
        fetch("/api/frames"),
        fetch("/api/diagnostics/status"),
      ]);

      if (!framesResponse.ok) {
        throw new Error(`API returned ${framesResponse.status}`);
      }

      setLoadProgress(70);
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
      fetchFromApi();
    } else {
      setError(null);
      setFrames(MOCK_FRAMES);
      setRuntimeDiagnostics(null);
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
    fetchFromApi();
  }, [fetchFromApi]);

  const handleGenerateInterpolation = useCallback(async () => {
    if (dataSource !== "api" || !selectedPair) {
      return;
    }

    if (selectedPair.gapMinutes > 30) {
      setInterpolationNotice("Interpolation disabled: gap exceeds 30 minutes");
      return;
    }

    try {
      setInterpolationNotice(`Generating recursive midpoint frames for ${selectedPair.gapMinutes.toFixed(1)} minute gap…`);
      const response = await fetch("/api/frames/interpolate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frame1_id: selectedPair.frame1.timestamp,
          frame2_id: selectedPair.frame2.timestamp,
          steps: 3,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Interpolation failed (${response.status})`);
      }
      await fetchFromApi();
      setInterpolationNotice(
        `Interpolation completed using recursive bisection between ${selectedPair.frame1.timestamp} and ${selectedPair.frame2.timestamp}.`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Interpolation failed";
      setInterpolationNotice(message);
      setError(message);
    }
  }, [dataSource, selectedPair, fetchFromApi]);

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

  const interpolationDisabled = dataSource !== "api" || !selectedPair || selectedPair.gapMinutes > 30;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background text-foreground selection:bg-primary/30">
      <DashboardHeader
        dataSource={dataSource}
        onToggleDataSource={handleToggleDataSource}
        showRawSensorGaps={showRawSensorGaps}
        runtimeSummary={getRuntimeSummary(runtimeDiagnostics)}
      />

      <main className="flex flex-1 min-h-0 relative px-4 pb-4 gap-4">
        <div className="flex-[4] flex flex-col min-w-0 gap-4">
          <div className="flex-1 min-h-0 relative glass rounded-xl overflow-hidden border-white/10">
            {isLoading && (
              <LoadingOverlay
                message={loadProgress < 100 ? "INITIALIZING DATA STREAM…" : "SYNCHRONIZING SENSORS…"}
                progress={loadProgress}
              />
            )}
            {error && <ErrorPanel message={error} onRetry={handleRetry} />}

            {!error && !isLoading && (
              <div className="w-full h-full relative">
                {comparisonMode === "split" ? (
                  <div className="flex w-full h-full gap-2 p-2">
                    <div className="flex-1 relative rounded-lg overflow-hidden border border-white/5">
                      <div className="absolute top-3 left-3 z-10 glass px-2 py-1 rounded text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
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
                        currentFrame={currentFrame}
                        comparisonMode="split"
                        runtimeDiagnostics={runtimeDiagnostics}
                      />
                    </div>
                    <div className="flex-1 relative rounded-lg overflow-hidden border border-primary/20">
                      <div className="absolute top-3 left-3 z-10 glass px-2 py-1 rounded text-[10px] font-mono text-primary uppercase tracking-widest">
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
                    currentFrame={currentFrame}
                    comparisonMode={comparisonMode}
                    runtimeDiagnostics={runtimeDiagnostics}
                  />
                )}

                {!currentFrame && (
                  <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-md z-50">
                    <div className="flex flex-col items-center gap-4">
                      <div className="w-12 h-12 rounded-full border-4 border-primary border-t-transparent animate-spin" />
                      <p className="text-xs tracking-[0.2em] uppercase font-mono text-primary animate-pulse">Establishing Satellite Link...</p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="glass rounded-xl p-6 shadow-2xl">
            <TimelineSlider
              frames={frames}
              currentIndex={currentIndex}
              onIndexChange={setCurrentIndex}
            />
            <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-4">
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

        <aside className="flex-1 min-w-[320px] flex flex-col gap-4">
          {currentFrame && (
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
          )}
        </aside>
      </main>
    </div>
  );
};

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
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const normalized = isDateOnly ? `${value}T00:00:00Z` : `${value.replace(" ", "T")}:00Z`;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

export default Index;
