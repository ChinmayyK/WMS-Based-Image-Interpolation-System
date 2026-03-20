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
    <div className="flex items-center gap-8 w-full flex-wrap">
      {/* Playback controls */}
      <div className="flex items-center gap-2">
        <div className="flex bg-white/5 border border-white/10 rounded-lg p-1">
          <ControlButton onClick={onPrev} title="Step Reverse">
            <div className="w-1.5 h-1.5 border-l-2 border-b-2 border-foreground rotate-45 ml-0.5" />
          </ControlButton>
          
          <button
            onClick={onPlayPause}
            className={`flex items-center justify-center h-8 px-6 rounded-md transition-all duration-300 font-mono text-[10px] font-bold tracking-[0.2em] relative overflow-hidden group ${
              isPlaying
                ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(34,211,238,0.4)]"
                : "bg-white/5 text-foreground hover:bg-white/10"
            }`}
          >
            <div className="relative z-10">{isPlaying ? "STOP_LINK" : "ESTABLISH_LINK"}</div>
            {!isPlaying && <div className="absolute inset-0 bg-primary/20 translate-x-[-100%] group-hover:translate-x-0 transition-transform duration-500" />}
          </button>

          <ControlButton onClick={onNext} title="Step Forward">
            <div className="w-1.5 h-1.5 border-r-2 border-t-2 border-foreground rotate-45 mr-0.5" />
          </ControlButton>
        </div>
      </div>

      <div className="h-4 w-px bg-white/10 hidden md:block" />

      {/* Speed selector */}
      <div className="flex items-center gap-4">
        <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60 font-bold hidden lg:block">Time Compression</span>
        <div className="flex bg-white/5 rounded-lg border border-white/10 p-1">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`px-3 py-1 text-[10px] font-mono font-bold rounded-md transition-all ${
                s === speed
                  ? "bg-primary/20 text-primary border border-primary/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      <div className="h-4 w-px bg-white/10 hidden xl:block" />

      <div className="flex items-center gap-3 flex-wrap">
        <ActionButton onClick={onInterpolate} disabled={interpolationDisabled}>
          Generate AI Frames
        </ActionButton>
        <ActionButton onClick={onExportVideo} disabled={exportDisabled || exportInProgress}>
          {exportInProgress ? "Exporting…" : "Export Video"}
        </ActionButton>
        <ActionButton onClick={onRunEvaluation} disabled={evaluationInProgress}>
          {evaluationInProgress ? "Evaluating…" : "Run Evaluation"}
        </ActionButton>
      </div>

      {/* Opacity control */}
      <div className="flex items-center gap-4 ml-auto">
        <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60 font-bold hidden xl:block">Sensor Translucency</span>
        <div className="flex items-center gap-3 bg-white/5 border border-white/10 px-4 py-2 rounded-lg">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
            className="w-32 h-1 accent-primary bg-white/10 rounded-full appearance-none cursor-pointer"
          />
          <span className="text-[10px] font-mono text-primary font-bold w-10 text-right tracking-widest">
            {Math.round(opacity * 100)}%
          </span>
        </div>
      </div>

      {interpolationNotice && (
        <div className={`w-full text-[10px] font-mono ${interpolationDisabled ? "text-gap" : "text-muted-foreground"}`}>
          {interpolationNotice}
        </div>
      )}
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
    className={`px-3 py-2 rounded-md text-[10px] font-mono font-bold tracking-[0.16em] uppercase border transition-all ${
      disabled
        ? "bg-white/5 text-muted-foreground/50 border-white/10 cursor-not-allowed"
        : "bg-white/5 text-foreground border-white/10 hover:border-primary/30 hover:text-primary"
    }`}
  >
    {children}
  </button>
);

export default AnimationControls;
