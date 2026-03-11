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
    <div className="w-72 bg-card border-l flex flex-col h-full">
      <div className="px-4 py-3 border-b">
        <h2 className="text-xs font-semibold font-mono text-foreground tracking-wide">
          Frame Information
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

        <div className="px-4 py-4 space-y-5">
          {/* Timestamp */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Timestamp
            </label>
            <p className="text-sm font-mono text-foreground mt-1">{frame.timestamp}</p>
          </div>

          {/* Frame Type */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Frame Type
            </label>
            <p
              className={`text-sm font-mono mt-1 ${
                frame.isOriginal ? "text-foreground font-semibold" : "text-primary"
              }`}
            >
              {frame.isOriginal ? "Original" : "Generated"}
            </p>
          </div>

          {/* Confidence */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Confidence Score
            </label>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-sm font-mono text-foreground">
                {frame.confidence.toFixed(2)}
              </span>
              <ConfidenceIndicator confidence={frame.confidence} />
            </div>
            <div className="mt-2 h-1 w-full bg-border rounded overflow-hidden">
              <div
                className="h-full bg-primary rounded transition-all duration-300"
                style={{ width: `${frame.confidence * 100}%` }}
              />
            </div>
          </div>

          {/* Source Frames */}
          {frame.sourceFrames && (
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
                Source Frames
              </label>
              <p className="text-sm font-mono text-foreground mt-1">
                {frame.sourceFrames[0]} → {frame.sourceFrames[1]}
              </p>
            </div>
          )}

          {/* Frame Index */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Frame Index
            </label>
            <p className="text-sm font-mono text-foreground mt-1">
              {frameIndex + 1} / {totalFrames}
            </p>
          </div>

          <div className="border-t pt-4">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Interpolation Method
            </label>
            <p className="text-sm font-mono text-foreground mt-1">
              {frame.isOriginal ? "N/A" : "WMS-Based AI"}
            </p>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Resolution
            </label>
            <p className="text-sm font-mono text-foreground mt-1">256 × 256 px</p>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Coordinate System
            </label>
            <p className="text-sm font-mono text-foreground mt-1">EPSG:3857</p>
          </div>

          {/* Data source indicator */}
          <div className="border-t pt-4">
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
              Data Source
            </label>
            <div className="flex items-center gap-2 mt-1">
              <div className={`w-2 h-2 rounded-full ${isDemoMode ? "bg-confidence-medium" : "bg-confidence-high"}`} />
              <span className="text-sm font-mono text-foreground">
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
