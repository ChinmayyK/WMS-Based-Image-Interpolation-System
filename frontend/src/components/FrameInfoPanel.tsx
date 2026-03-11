import { SatelliteFrame, ComparisonMode } from "@/lib/types";
import ComparisonControls from "./ComparisonControls";

interface FrameInfoPanelProps {
  frame: SatelliteFrame;
  frameIndex: number;
  totalFrames: number;
  comparisonMode: ComparisonMode;
  onComparisonModeChange: (mode: ComparisonMode) => void;
  toggleView: "original" | "generated";
  onToggleViewChange: (view: "original" | "generated") => void;
  isDemoMode: boolean;
}

const ConfidenceIndicator = ({ confidence }: { confidence: number }) => {
  let colorClass = "bg-confidence-high";
  let label = "High";
  if (confidence < 0.7) {
    colorClass = "bg-confidence-low";
    label = "Low";
  } else if (confidence < 0.85) {
    colorClass = "bg-confidence-medium";
    label = "Medium";
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${colorClass}`} />
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
};

const FrameInfoPanel = ({
  frame,
  frameIndex,
  totalFrames,
  comparisonMode,
  onComparisonModeChange,
  toggleView,
  onToggleViewChange,
  isDemoMode,
}: FrameInfoPanelProps) => {
  return (
    <div className="w-80 bg-panel/95 backdrop-blur border-l border-border/50 flex flex-col h-full shadow-2xl z-20">
      <div className="px-5 py-4 border-b border-border/50 bg-white/5">
        <h2 className="text-[11px] font-semibold font-mono text-muted-foreground tracking-widest uppercase">
          Frame Analytics
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Comparison controls */}
        <ComparisonControls
          mode={comparisonMode}
          onModeChange={onComparisonModeChange}
          toggleView={toggleView}
          onToggleViewChange={onToggleViewChange}
        />

        <div className="px-5 py-5 space-y-6">
          {/* Timestamp */}
          <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Timestamp
            </label>
            <p className="text-sm font-mono text-foreground">{frame.timestamp}</p>
          </div>

          {/* Frame Type */}
          <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Frame Type
            </label>
            <p
              className={`text-sm font-mono ${
                frame.isOriginal ? "text-foreground" : "text-primary"
              }`}
            >
              {frame.isOriginal ? "Original" : "Generated"}
            </p>
          </div>

          {/* Confidence */}
          <div>
            <div className="flex justify-between items-baseline mb-2">
              <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
                Confidence Score
              </label>
              <div className="flex items-center gap-3">
                <span className="text-sm font-mono text-foreground">
                  {frame.confidence.toFixed(2)}
                </span>
                <ConfidenceIndicator confidence={frame.confidence} />
              </div>
            </div>
            <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden border border-white/5">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500 ease-out relative"
                style={{ width: `${frame.confidence * 100}%` }}
              >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent to-white/30" />
              </div>
            </div>
          </div>

          {/* Source Frames */}
          {frame.sourceFrames && (
            <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
              <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
                Source Frames
              </label>
              <p className="text-sm font-mono text-foreground">
                {frame.sourceFrames[0]} → {frame.sourceFrames[1]}
              </p>
            </div>
          )}

          {/* Frame Index */}
          <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Sequence Position
            </label>
            <p className="text-sm font-mono text-foreground">
              {frameIndex + 1} / {totalFrames}
            </p>
          </div>

          <div className="flex justify-between items-baseline border-b border-border/30 pb-2 pt-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Model
            </label>
            <p className="text-[11px] font-mono text-foreground">
              {frame.isOriginal ? "N/A" : "WMS-AI Interpolator"}
            </p>
          </div>

          <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Resolution
            </label>
            <p className="text-[11px] font-mono text-foreground">256 × 256 px</p>
          </div>

          <div className="flex justify-between items-baseline border-b border-border/30 pb-2">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Projection Coordinates
            </label>
            <p className="text-[11px] font-mono text-foreground">EPSG:3857</p>
          </div>

          {/* Data source indicator */}
          <div className="pt-4 flex items-center justify-between">
            <label className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">
              Data Pipeline
            </label>
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${isDemoMode ? "bg-confidence-medium" : "bg-confidence-high"}`} />
              <span className="text-[11px] font-mono text-foreground">
                {isDemoMode ? "Demo Dataset" : "Live API"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FrameInfoPanel;
