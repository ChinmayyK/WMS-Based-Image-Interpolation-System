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
    <div className="w-[320px] glass h-full flex flex-col rounded-xl overflow-hidden border-white/10 shadow-3xl">
      <div className="px-6 py-5 border-b border-white/5 bg-white/5">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
          <h2 className="text-[11px] font-bold font-mono text-primary tracking-[0.2em] uppercase">
            Live Telemetry
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* Comparison controls */}
        <div className="p-4 bg-primary/5 border-b border-white/5">
          <ComparisonControls
            mode={comparisonMode}
            onModeChange={onComparisonModeChange}
            toggleView={toggleView}
            onToggleViewChange={onToggleViewChange}
          />
        </div>

        <div className="px-6 py-6 space-y-8">
          {/* Scientific Metadata Grid */}
          <div className="grid grid-cols-1 gap-6">
            <AnalyticsRow label="Acquisition Time" value={frame.timestamp} />
            <AnalyticsRow 
              label="Source Identity" 
              value={frame.isOriginal ? "NASA GIBS SENSOR" : "AI VIRTUAL SENSOR"} 
              highlight={!frame.isOriginal} 
            />
            
            {/* Confidence Gauge */}
            <div className="space-y-3">
              <div className="flex justify-between items-end">
                <label className="text-[9px] uppercase tracking-widest text-muted-foreground/60 font-bold">
                  Stability Index (SSIM)
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-bold text-foreground">
                    {(frame.confidence * 100).toFixed(1)}%
                  </span>
                  <ConfidenceIndicator confidence={frame.confidence} />
                </div>
              </div>
              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden p-[1px] border border-white/5">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-1000 ease-out relative"
                  style={{ width: `${frame.confidence * 100}%` }}
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
                </div>
              </div>
            </div>

            {frame.sourceFrames && (
              <AnalyticsRow 
                label="Interpolation Base" 
                value={`${frame.sourceFrames[0]} ↔ ${frame.sourceFrames[1]}`} 
              />
            )}
            
            <AnalyticsRow label="Sequence ID" value={`${frameIndex + 1} / ${totalFrames}`} />
            
            <div className="pt-4 border-t border-white/5 space-y-4">
              <AnalyticsRow label="Processing Engine" value={frame.isOriginal ? "Raw Telemetry" : "RIFE-v4.6.1"} />
              <AnalyticsRow label="Imagery Resolution" value="1024 × 1024 PX" />
              <AnalyticsRow label="Coordinate Sys" value="EPSG:3857 (Web Mercator)" />
            </div>
          </div>

          {/* Data source indicator */}
          <div className="pt-6 border-t border-white/5 flex items-center justify-between">
            <label className="text-[9px] uppercase tracking-widest text-muted-foreground/60 font-bold">
              Service Status
            </label>
            <div className="flex items-center gap-2 px-2 py-1 rounded bg-white/5 border border-white/5">
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${isDemoMode ? "bg-yellow-500" : "bg-green-500"}`} />
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-foreground">
                {isDemoMode ? "DEMO_SIMULATION" : "LIVE_UPLINK"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const AnalyticsRow = ({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) => (
  <div className="flex flex-col gap-1 pr-2">
    <label className="text-[9px] uppercase tracking-widest text-muted-foreground/60 font-bold">
      {label}
    </label>
    <p className={`text-xs font-mono font-medium ${highlight ? 'text-primary' : 'text-foreground/90'}`}>
      {value}
    </p>
  </div>
);

export default FrameInfoPanel;
