import { useState, useEffect, useCallback, useRef } from "react";
import DashboardHeader from "@/components/DashboardHeader";
import MapViewer from "@/components/MapViewer";
import TimelineSlider from "@/components/TimelineSlider";
import AnimationControls from "@/components/AnimationControls";
import FrameInfoPanel from "@/components/FrameInfoPanel";
import CurrentTimeDisplay from "@/components/CurrentTimeDisplay";
import LoadingOverlay from "@/components/LoadingOverlay";
import ErrorPanel from "@/components/ErrorPanel";
import { MOCK_FRAMES } from "@/lib/mock-data";
import { PlaybackSpeed, ComparisonMode, DataSource } from "@/lib/types";

const Index = () => {
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
  const intervalRef = useRef<number | null>(null);

  const frames = MOCK_FRAMES;
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

  const handleToggleDataSource = useCallback(() => {
    const next = dataSource === "demo" ? "api" : "demo";
    setDataSource(next);
    if (next === "api") {
      setIsLoading(true);
      setLoadProgress(0);
      // Simulate API failure for demo
      setTimeout(() => {
        setIsLoading(false);
        setError("Unable to fetch frames. Check backend connection.");
      }, 2000);
    } else {
      setError(null);
      setIsLoading(true);
      setLoadProgress(0);
      setTimeout(() => {
        setLoadProgress(100);
        setTimeout(() => setIsLoading(false), 200);
      }, 800);
    }
  }, [dataSource]);

  const handleRetry = useCallback(() => {
    setError(null);
    setIsLoading(true);
    setLoadProgress(0);
    setTimeout(() => {
      setIsLoading(false);
      setError("Unable to fetch frames. Check backend connection.");
    }, 2000);
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <DashboardHeader dataSource={dataSource} onToggleDataSource={handleToggleDataSource} />

      <div className="flex flex-1 min-h-0">
        {/* Map area */}
        <div className="flex-1 p-3 relative">
          {isLoading && (
            <LoadingOverlay
              message={loadProgress < 100 ? "Loading frames…" : "Generating animation…"}
              progress={loadProgress}
            />
          )}
          {error && <ErrorPanel message={error} onRetry={handleRetry} />}

          {/* Split view */}
          {comparisonMode === "split" && !error && !isLoading ? (
            <div className="flex w-full h-full gap-1">
              <div className="flex-1 relative">
                <div className="absolute top-1 left-1 z-10 bg-card/85 border rounded px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
                  Original Frame
                </div>
                <MapViewer
                  opacity={opacity}
                  showOverlay={showOverlay}
                  onToggleOverlay={() => setShowOverlay(!showOverlay)}
                  showConfidence={showConfidence}
                  onToggleConfidence={() => setShowConfidence(!showConfidence)}
                />
              </div>
              <div className="flex-1 relative">
                <div className="absolute top-1 left-1 z-10 bg-card/85 border rounded px-2 py-0.5 text-[10px] font-mono text-primary">
                  Generated Frame
                </div>
                <MapViewer
                  opacity={opacity}
                  showOverlay={showOverlay}
                  onToggleOverlay={() => setShowOverlay(!showOverlay)}
                  showConfidence={showConfidence}
                  onToggleConfidence={() => setShowConfidence(!showConfidence)}
                />
              </div>
            </div>
          ) : (
            !error &&
            !isLoading && (
              <div className="w-full h-full relative">
                {comparisonMode === "toggle" && (
                  <div className="absolute top-1 left-14 z-10 bg-card/85 border rounded px-2 py-0.5 text-[10px] font-mono text-primary">
                    Viewing: {toggleView === "original" ? "Original" : "Generated"}
                  </div>
                )}
                <MapViewer
                  opacity={opacity}
                  showOverlay={showOverlay}
                  onToggleOverlay={() => setShowOverlay(!showOverlay)}
                  showConfidence={showConfidence}
                  onToggleConfidence={() => setShowConfidence(!showConfidence)}
                />
              </div>
            )
          )}

          {/* No frame fallback */}
          {!isLoading && !error && !currentFrame && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
              <p className="text-xs font-mono text-muted-foreground">No frame available</p>
            </div>
          )}
        </div>

        {/* Frame info panel */}
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
      </div>

      {/* Bottom controls */}
      <div className="border-t bg-secondary px-6 py-3 space-y-3">
        <TimelineSlider
          frames={frames}
          currentIndex={currentIndex}
          onIndexChange={setCurrentIndex}
        />
        <div className="flex items-center justify-between">
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
          <CurrentTimeDisplay frame={currentFrame} />
        </div>
      </div>
    </div>
  );
};

export default Index;
