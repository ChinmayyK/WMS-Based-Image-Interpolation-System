import { SatelliteFrame } from "@/lib/types";

interface TimelineSliderProps {
  frames: SatelliteFrame[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
}

const TimelineSlider = ({ frames, currentIndex, onIndexChange }: TimelineSliderProps) => {
  return (
    <div className="w-full">
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-muted-foreground w-12 text-right">
          {frames[0]?.timestamp}
        </span>

        <div className="flex-1 relative">
          {/* Track */}
          <div className="relative h-8 flex items-center">
            <div className="absolute w-full h-0.5 bg-border rounded" />
            {/* Active portion */}
            <div
              className="absolute h-0.5 bg-primary rounded"
              style={{ width: `${(currentIndex / (frames.length - 1)) * 100}%` }}
            />

            {/* Tick marks */}
            <div className="absolute w-full flex justify-between">
              {frames.map((frame, i) => (
                <button
                  key={frame.timestamp}
                  onClick={() => onIndexChange(i)}
                  className="relative group z-10"
                >
                  <div
                    className={`w-2 h-2 rounded-full transition-all ${
                      frame.isOriginal
                        ? "bg-muted-foreground/50 hover:bg-muted-foreground"
                        : "bg-border hover:bg-muted-foreground/50"
                    }`}
                  />
                  <span className="absolute top-4 left-1/2 -translate-x-1/2 text-[10px] font-mono text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                    {frame.timestamp}
                  </span>
                </button>
              ))}
            </div>

            {/* Glowing animated marker */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-primary shadow-[0_0_10px_rgba(255,255,255,0.5)] rounded-full border-2 border-primary transition-all duration-300 pointer-events-none z-20 flex items-center justify-center"
              style={{
                left: `calc(${(currentIndex / (frames.length - 1)) * 100}% - 8px)`,
              }}
            >
              <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
            </div>
          </div>
        </div>

        <span className="text-xs font-mono text-muted-foreground w-12">
          {frames[frames.length - 1]?.timestamp}
        </span>
      </div>
    </div>
  );
};

export default TimelineSlider;
