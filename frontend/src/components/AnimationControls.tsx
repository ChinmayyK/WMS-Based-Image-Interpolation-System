import { PlaybackSpeed } from "@/lib/types";

interface AnimationControlsProps {
  isPlaying: boolean;
  onPlayPause: () => void;
  onNext: () => void;
  onPrev: () => void;
  speed: PlaybackSpeed;
  onSpeedChange: (speed: PlaybackSpeed) => void;
  opacity: number;
  onOpacityChange: (val: number) => void;
}

const speeds: PlaybackSpeed[] = [0.5, 1.0, 1.5, 2.0];

const AnimationControls = ({
  isPlaying,
  onPlayPause,
  onNext,
  onPrev,
  speed,
  onSpeedChange,
  opacity,
  onOpacityChange,
}: AnimationControlsProps) => {
  return (
    <div className="flex items-center gap-8">
      {/* Playback controls */}
      <div className="flex items-center gap-1.5 bg-background/50 p-1 rounded-sm border border-border/50">
        <button
          onClick={onPrev}
          className="px-3 py-1 text-[11px] font-mono text-foreground hover:bg-white/10 rounded-sm transition-colors"
        >
          STEP -
        </button>
        <button
          onClick={onPlayPause}
          className={`w-16 py-1 text-[11px] font-mono font-semibold rounded-sm transition-all duration-300 ${
            isPlaying
              ? "bg-primary/20 text-primary border border-primary/50 shadow-[0_0_10px_rgba(59,130,246,0.3)]"
              : "bg-white/5 text-foreground hover:bg-white/10 border border-transparent"
          }`}
        >
          {isPlaying ? "PAUSE" : "PLAY"}
        </button>
        <button
          onClick={onNext}
          className="px-3 py-1 text-[11px] font-mono text-foreground hover:bg-white/10 rounded-sm transition-colors"
        >
          STEP +
        </button>
      </div>

      {/* Speed selector */}
      <div className="flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">Playback Rate</span>
        <div className="flex items-center gap-1 bg-background/50 p-0.5 rounded-sm border border-border/50">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`px-2 py-0.5 text-[10px] font-mono rounded-sm transition-colors ${
                s === speed
                  ? "bg-white/20 text-white font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/5"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Opacity control */}
      <div className="flex items-center gap-3 ml-auto">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono">Base Opacity</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
          className="w-32 h-1 accent-primary bg-background/50 rounded-full appearance-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        />
        <span className="text-[10px] font-mono text-primary w-8 tracking-wider">
          {Math.round(opacity * 100)}%
        </span>
      </div>
    </div>
  );
};

export default AnimationControls;
