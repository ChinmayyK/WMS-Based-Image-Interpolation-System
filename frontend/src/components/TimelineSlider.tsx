import { SatelliteFrame } from "@/lib/types";
import { CATEGORY_STYLES, getTimelineCategory } from "@/lib/frame-status";

interface TimelineSliderProps {
  frames: SatelliteFrame[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
}

const TimelineSlider = ({ frames, currentIndex, onIndexChange }: TimelineSliderProps) => {
  const totalFrames = frames.length;
  const cadenceMinutes = computeCadenceMinutes(frames);
  const visibleLabelStride = totalFrames <= 10 ? 1 : Math.ceil(totalFrames / 6);

  return (
    <div className="w-full flex flex-col gap-3">
      <div className="flex justify-between items-center px-1 gap-4">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
          Observed Timeline
        </span>
        <div className="flex items-center gap-4 text-[10px] font-mono text-muted-foreground">
          <span>{totalFrames} frames</span>
          {cadenceMinutes !== null && <span>cadence ~{cadenceMinutes.toFixed(0)} min</span>}
          <div className="flex gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-observed/80" />
              <span>OBSERVED</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-confidence-high/80" />
              <span>AI</span>
            </div>
          </div>
        </div>
      </div>

      <div className="relative h-12 flex items-center group">
        <div className="absolute w-full h-1 bg-white/5 rounded-full overflow-hidden flex">
          {frames.map((frame, index) => {
            const category = getTimelineCategory(frame);
            const style = CATEGORY_STYLES[category];
            return (
              <div
                key={`${frame.timestamp}-${index}`}
                className={`h-full transition-colors flex-1 ${style.bg}`}
              />
            );
          })}
        </div>

        <div className="absolute w-full flex justify-between px-0.5 pointer-events-none items-center">
          {frames.map((frame, index) => (
            <div
              key={`tick-${index}`}
              className={`transition-all ${
                index === currentIndex 
                  ? "w-1 h-4 bg-primary rounded-full" 
                  : frame.isOriginal 
                    ? "w-[2px] h-2 bg-white/60 rounded-full" 
                    : "w-px h-1.5 border-l-[2px] border-dotted border-white/30 bg-transparent"
              }`}
            />
          ))}
        </div>

        <input
          type="range"
          min="0"
          max={totalFrames > 0 ? totalFrames - 1 : 0}
          value={currentIndex}
          onChange={(event) => onIndexChange(parseInt(event.target.value, 10))}
          className="absolute w-full h-8 opacity-0 cursor-pointer z-30"
        />

        <div
          className="absolute top-1/2 -translate-y-1/2 pointer-events-none transition-all duration-200"
          style={{
            left: `calc(${totalFrames > 1 ? (currentIndex / (totalFrames - 1)) * 100 : 0}%)`,
            transform: "translate(-50%, -50%)",
          }}
        >
          <div className="relative flex flex-col items-center">
            <div className="absolute bottom-6 glass px-2 py-1 rounded border border-primary/30 opacity-0 group-hover:opacity-100 transition-opacity">
              <span className="text-[10px] font-mono text-primary font-bold whitespace-nowrap">
                {frames[currentIndex]?.timestamp}
              </span>
            </div>
            <div className="w-6 h-6 rounded-full border border-primary/50 bg-background/80 flex items-center justify-center shadow-[0_0_15px_rgba(34,211,238,0.4)]">
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            </div>
          </div>
        </div>
      </div>

      <div
        className="grid gap-2 px-1"
        style={{ gridTemplateColumns: `repeat(${Math.max(totalFrames, 1)}, minmax(0, 1fr))` }}
      >
        {frames.map((frame, index) => {
          const showLabel = index % visibleLabelStride === 0 || index === totalFrames - 1;
          return (
            <span
              key={`label-${frame.timestamp}-${index}`}
              className={`text-[10px] font-mono text-muted-foreground ${
                index === currentIndex ? "text-primary" : ""
              }`}
            >
              {showLabel ? formatTickLabel(frame.timestamp) : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
};

function computeCadenceMinutes(frames: SatelliteFrame[]): number | null {
  const observedTimestamps = frames
    .filter((frame) => frame.isOriginal)
    .map((frame) => frame.timestamp);

  const gaps = observedTimestamps
    .slice(1)
    .map((timestamp, index) => {
      const previous = parseTimestamp(observedTimestamps[index]);
      const current = parseTimestamp(timestamp);
      if (previous === null || current === null) {
        return null;
      }
      return Math.abs(current - previous) / 60000;
    })
    .filter((value): value is number => value !== null);

  if (gaps.length === 0) {
    return null;
  }
  const sorted = [...gaps].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

function formatTickLabel(value: string): string {
  const timestamp = parseTimestamp(value);
  if (timestamp === null) {
    return value;
  }
  const date = new Date(timestamp);
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
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

export default TimelineSlider;
