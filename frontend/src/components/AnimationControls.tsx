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
    <div className="flex items-center gap-6">
      {/* Playback controls */}
      <div className="flex items-center gap-1">
        <button
          onClick={onPrev}
          className="px-3 py-1.5 text-xs font-mono text-foreground bg-card border rounded hover:bg-muted transition-colors"
        >
          PREV
        </button>
        <button
          onClick={onPlayPause}
          className={`px-4 py-1.5 text-xs font-mono border rounded transition-colors ${
            isPlaying
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-card text-foreground hover:bg-muted"
          }`}
        >
          {isPlaying ? "PAUSE" : "PLAY"}
        </button>
        <button
          onClick={onNext}
          className="px-3 py-1.5 text-xs font-mono text-foreground bg-card border rounded hover:bg-muted transition-colors"
        >
          NEXT
        </button>
      </div>

      {/* Speed selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Speed</span>
        <div className="flex items-center gap-0.5">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`px-2 py-1 text-xs font-mono border rounded transition-colors ${
                s === speed
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Opacity control */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Overlay Opacity</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
          className="w-24 h-1 accent-primary"
        />
        <span className="text-xs font-mono text-muted-foreground w-8">
          {Math.round(opacity * 100)}%
        </span>
      </div>
    </div>
  );
};

export default AnimationControls;
