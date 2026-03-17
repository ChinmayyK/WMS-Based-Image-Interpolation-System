import { SatelliteFrame } from "@/lib/types";

interface TimelineSliderProps {
  frames: SatelliteFrame[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
}

const TimelineSlider = ({ frames, currentIndex, onIndexChange }: TimelineSliderProps) => {
  const totalFrames = frames.length;
  
  return (
    <div className="w-full flex flex-col gap-2">
      <div className="flex justify-between items-center px-1">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">Temporal Analysis Timeline</span>
        <div className="flex gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-green-500/50" />
            <span className="text-[10px] font-mono text-muted-foreground">SENSOR</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-blue-500/50" />
            <span className="text-[10px] font-mono text-muted-foreground">AI PREDICTED</span>
          </div>
        </div>
      </div>

      <div className="relative h-12 flex items-center group">
        {/* Progress Track Background */}
        <div className="absolute w-full h-1 bg-white/5 rounded-full overflow-hidden flex">
          {frames.map((frame, i) => (
            <div 
              key={`${frame.timestamp}-${i}`}
              className={`h-full transition-colors flex-1 ${
                frame.isOriginal ? 'bg-green-500/20' : 'bg-blue-500/30'
              }`}
            />
          ))}
        </div>

        {/* Highlighted Visual Ticks */}
        <div className="absolute w-full flex justify-between px-0.5 pointer-events-none">
          {frames.map((frame, i) => (
            <div 
              key={`tick-${i}`}
              className={`w-px h-2 rounded-full transition-all ${
                i === currentIndex ? 'h-4 bg-primary' : 'bg-white/10'
              }`}
            />
          ))}
        </div>

        {/* Range Slider for Smooth Scrubbing */}
        <input
          type="range"
          min="0"
          max={totalFrames > 0 ? totalFrames - 1 : 0}
          value={currentIndex}
          onChange={(e) => onIndexChange(parseInt(e.target.value))}
          className="absolute w-full h-8 opacity-0 cursor-pointer z-30"
        />

        {/* Visual Handle / Thumb */}
        <div 
          className="absolute top-1/2 -translate-y-1/2 pointer-events-none transition-all duration-200"
          style={{ 
            left: `calc(${(currentIndex / (totalFrames - 1)) * 100}%)`,
            transform: `translate(-50%, -50%)`
          }}
        >
          <div className="relative flex flex-col items-center">
            {/* Tooltip */}
            <div className="absolute bottom-6 glass px-2 py-1 rounded border border-primary/30 opacity-0 group-hover:opacity-100 transition-opacity">
              <span className="text-[10px] font-mono text-primary font-bold whitespace-nowrap">
                {frames[currentIndex]?.timestamp}
              </span>
            </div>
            {/* The Outer Ring */}
            <div className="w-6 h-6 rounded-full border border-primary/50 bg-background/80 flex items-center justify-center shadow-[0_0_15px_rgba(34,211,238,0.4)]">
              {/* The Inner Dot */}
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            </div>
          </div>
        </div>
      </div>

      {/* Start/End Timestamps */}
      <div className="flex justify-between px-1">
        <span className="text-[10px] font-mono text-muted-foreground">{frames[0]?.timestamp}</span>
        <span className="text-[10px] font-mono text-muted-foreground">{frames[totalFrames-1]?.timestamp}</span>
      </div>
    </div>
  );
};

export default TimelineSlider;
