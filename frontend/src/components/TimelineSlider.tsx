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
                  className="relative group"
                >
                  <div
                    className={`w-2.5 h-2.5 rounded-full border-2 transition-all ${
                      i === currentIndex
                        ? "bg-primary border-primary scale-125"
                        : frame.isOriginal
                        ? "bg-card border-primary/60 hover:border-primary"
                        : "bg-card border-border hover:border-muted-foreground"
                    }`}
                  />
                  <span className="absolute top-4 left-1/2 -translate-x-1/2 text-[10px] font-mono text-muted-foreground whitespace-nowrap">
                    {frame.timestamp}
                  </span>
                </button>
              ))}
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
