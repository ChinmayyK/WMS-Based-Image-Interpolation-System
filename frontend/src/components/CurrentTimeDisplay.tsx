import { SatelliteFrame } from "@/lib/types";

interface CurrentTimeDisplayProps {
  frame: SatelliteFrame;
}

const CurrentTimeDisplay = ({ frame }: CurrentTimeDisplayProps) => {
  return (
    <div className="flex items-center gap-4 border rounded bg-card px-4 py-2">
      <div>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
          Current Time
        </span>
        <p className="text-sm font-mono text-foreground">{frame.timestamp}</p>
      </div>
      <div className="w-px h-6 bg-border" />
      <div>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans">
          Frame Type
        </span>
        <p
          className={`text-sm font-mono ${
            frame.isOriginal ? "text-foreground font-semibold" : "text-primary"
          }`}
        >
          {frame.isOriginal ? "Original" : "Interpolated"}
        </p>
      </div>
    </div>
  );
};

export default CurrentTimeDisplay;
