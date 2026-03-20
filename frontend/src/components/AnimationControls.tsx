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
  onInterpolate: () => void;
  interpolationDisabled: boolean;
  interpolationNotice?: string | null;
  onExportVideo: () => void;
  exportDisabled?: boolean;
  exportInProgress?: boolean;
  onRunEvaluation: () => void;
  evaluationInProgress?: boolean;
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
  onInterpolate,
  interpolationDisabled,
  interpolationNotice,
  onExportVideo,
  exportDisabled = false,
  exportInProgress = false,
  onRunEvaluation,
  evaluationInProgress = false,
}: AnimationControlsProps) => {
  return (
    <div className="flex items-center justify-between w-full h-10 px-2 lg:px-4">
      {/* Left section: Export & Evaluate */}
      <div className="flex items-center gap-2 flex-1">
        <ActionButton onClick={onInterpolate} disabled={interpolationDisabled}>
          {interpolationDisabled ? "NO GAP" : "INTERPOLATE"}
        </ActionButton>
        <div className="h-4 w-px bg-white/10 mx-2 hidden sm:block" />
        <ActionButton onClick={onExportVideo} disabled={exportDisabled || exportInProgress}>
          {exportInProgress ? "EXPORTING" : "EXPORT"}
        </ActionButton>
        <ActionButton onClick={onRunEvaluation} disabled={evaluationInProgress}>
          {evaluationInProgress ? "EVALUATING" : "EVALUATE"}
        </ActionButton>
      </div>

      {/* Center section: Playback */}
      <div className="flex items-center justify-center gap-3 flex-[2]">
        <ControlButton onClick={onPrev} title="Step Reverse">
          <div className="w-1.5 h-1.5 border-l-2 border-b-2 border-foreground rotate-45 ml-0.5" />
        </ControlButton>
        
        <button
          onClick={onPlayPause}
          className={`flex items-center justify-center h-8 px-8 rounded-full transition-all duration-300 font-mono text-[11px] font-bold tracking-[0.2em] shadow-lg ${
            isPlaying
              ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(34,211,238,0.4)]"
              : "bg-white/10 text-foreground hover:bg-white/20"
          }`}
        >
          {isPlaying ? "PAUSE" : "PLAY"}
        </button>

        <ControlButton onClick={onNext} title="Step Forward">
          <div className="w-1.5 h-1.5 border-r-2 border-t-2 border-foreground rotate-45 mr-0.5" />
        </ControlButton>
      </div>

      {/* Right section: Speed and Opacity */}
      <div className="flex items-center justify-end gap-6 flex-1">
        {/* Speed */}
        <div className="flex items-center gap-1 bg-white/5 rounded-full p-1 border border-white/10">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`px-2.5 py-1 text-[10px] font-mono font-bold rounded-full transition-all ${
                s === speed
                  ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(34,211,238,0.3)]"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Opacity control */}
        <div className="hidden lg:flex items-center gap-3">
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground/60 font-bold">L1B OPACITY</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
            className="w-20 h-1 accent-primary bg-white/10 rounded-full appearance-none flex-shrink-0"
          />
        </div>
      </div>
    </div>
  );
};

const ControlButton = ({ onClick, children, title }: { onClick: () => void, children: React.ReactNode, title: string }) => (
  <button
    onClick={onClick}
    title={title}
    className="w-8 h-8 flex items-center justify-center bg-transparent hover:bg-white/5 rounded-md transition-colors text-foreground"
  >
    {children}
  </button>
);

const ActionButton = ({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`px-3 py-1.5 rounded-full text-[10px] font-mono font-bold tracking-[0.1em] transition-all whitespace-nowrap ${
      disabled
        ? "text-muted-foreground/50 cursor-not-allowed"
        : "text-foreground hover:bg-white/5"
    }`}
  >
    {children}
  </button>
);

export default AnimationControls;
