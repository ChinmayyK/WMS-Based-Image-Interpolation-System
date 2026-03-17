import { useState, useEffect, useCallback, useRef } from "react";
import DashboardHeader from "@/components/DashboardHeader";
import MapViewer from "@/components/MapViewer";
import TimelineSlider from "@/components/TimelineSlider";
import AnimationControls from "@/components/AnimationControls";
import FrameInfoPanel from "@/components/FrameInfoPanel";
import LoadingOverlay from "@/components/LoadingOverlay";
import ErrorPanel from "@/components/ErrorPanel";
import { MOCK_FRAMES } from "@/lib/mock-data";
import { SatelliteFrame, PlaybackSpeed, ComparisonMode, DataSource } from "@/lib/types";

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
  const [showConfidence, setShowConfidence] = useState(false);
  const [showClouds, setShowClouds] = useState(false);
  const [showVectors, setShowVectors] = useState(false);
  const intervalRef = useRef<number | null>(null);

  const currentFrame = frames[currentIndex];

  // Simulate loading on mount
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

  const goNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % frames.length);
  }, [frames.length]);

  const goPrev = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + frames.length) % frames.length);
  }, [frames.length]);

  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = window.setInterval(() => {
        goNext();
      }, 1000 / speed);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, speed, goNext]);

  // Fetch frames from API
  const fetchFromApi = useCallback(async () => {
    setIsLoading(true);
    setLoadProgress(0);
    setError(null);

    try {
      setLoadProgress(30);
      const response = await fetch("/api/frames");

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      setLoadProgress(70);
      const data = await response.json();

      if (data.status === "success" && data.frames?.length > 0) {
        setFrames(data.frames);
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

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background text-foreground selection:bg-primary/30">
      <DashboardHeader dataSource={dataSource} onToggleDataSource={handleToggleDataSource} />

      <main className="flex flex-1 min-h-0 relative px-4 pb-4 gap-4">
        {/* Main Observation Area (80% roughly) */}
        <div className="flex-[4] flex flex-col min-w-0 gap-4">
          <div className="flex-1 min-h-0 relative glass rounded-xl overflow-hidden border-white/10">
            {isLoading && (
              <LoadingOverlay
                message={loadProgress < 100 ? "INITIALIZING DATA STREAM…" : "SYNCHRONIZING SENSORS…"}
                progress={loadProgress}
              />
            )}
            {error && <ErrorPanel message={error} onRetry={handleRetry} />}

            {/* Map Frame Rendering */}
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
                        showConfidence={showConfidence}
                        onToggleConfidence={() => setShowConfidence(!showConfidence)}
                        showClouds={showClouds}
                        onToggleClouds={() => setShowClouds(!showClouds)}
                        showVectors={showVectors}
                        onToggleVectors={() => setShowVectors(!showVectors)}
                        currentFrame={currentFrame}
                        comparisonMode="split"
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
                        showConfidence={showConfidence}
                        onToggleConfidence={() => setShowConfidence(!showConfidence)}
                        showClouds={showClouds}
                        onToggleClouds={() => setShowClouds(!showClouds)}
                        showVectors={showVectors}
                        onToggleVectors={() => setShowVectors(!showVectors)}
                        currentFrame={currentFrame}
                        comparisonMode="split"
                      />
                    </div>
                  </div>
                ) : (
                  <MapViewer
                    opacity={opacity}
                    showOverlay={showOverlay}
                    onToggleOverlay={() => setShowOverlay(!showOverlay)}
                    showConfidence={showConfidence}
                    onToggleConfidence={() => setShowConfidence(!showConfidence)}
                    showClouds={showClouds}
                    onToggleClouds={() => setShowClouds(!showClouds)}
                    showVectors={showVectors}
                    onToggleVectors={() => setShowVectors(!showVectors)}
                    currentFrame={currentFrame}
                    comparisonMode={comparisonMode}
                  />
                )}

                {/* No frame fallback */}
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

          {/* Bottom Timeline Control */}
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
              />
            </div>
          </div>
        </div>

        {/* Right Dashboard Sidebar (20% roughly) */}
        <aside className="flex-1 min-w-[320px] flex flex-col gap-4">
          <FrameInfoPanel
            frame={currentFrame}
            frameIndex={currentIndex}
            totalFrames={frames.length}
            comparisonMode={comparisonMode}
            onComparisonModeChange={setComparisonMode}
            toggleView={toggleView}
            onToggleViewChange={setToggleView}
            isDemoMode={dataSource === "demo"}
          />
        </aside>
      </main>
    </div>
  );
};

export default Index;
