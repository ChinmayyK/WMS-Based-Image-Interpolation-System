import { ComparisonMode } from "@/lib/types";

interface ComparisonControlsProps {
  mode: ComparisonMode;
  onModeChange: (mode: ComparisonMode) => void;
  toggleView: "original" | "generated";
  onToggleViewChange: (view: "original" | "generated") => void;
}

const modes: { value: ComparisonMode; label: string }[] = [
  { value: "off", label: "OFF" },
  { value: "split", label: "SPLIT" },
  { value: "toggle", label: "TOGGLE" },
];

const ComparisonControls = ({
  mode,
  onModeChange,
  toggleView,
  onToggleViewChange,
}: ComparisonControlsProps) => {
  return (
    <div className="px-4 py-3 border-b">
      <h2 className="text-xs font-semibold font-mono text-foreground tracking-wide mb-3">
        Comparison Mode
      </h2>
      <div className="flex items-center gap-0.5 mb-2">
        {modes.map((m) => (
          <button
            key={m.value}
            onClick={() => onModeChange(m.value)}
            className={`px-2.5 py-1 text-[10px] font-mono border rounded transition-colors ${
              mode === m.value
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "toggle" && (
        <div className="flex items-center gap-0.5 mt-2">
          <button
            onClick={() => onToggleViewChange("original")}
            className={`px-2.5 py-1 text-[10px] font-mono border rounded transition-colors ${
              toggleView === "original"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            ORIGINAL
          </button>
          <button
            onClick={() => onToggleViewChange("generated")}
            className={`px-2.5 py-1 text-[10px] font-mono border rounded transition-colors ${
              toggleView === "generated"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            GENERATED
          </button>
        </div>
      )}

      {mode === "split" && (
        <div className="mt-2 flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
          <span className="w-2 h-2 rounded-full bg-primary/60 inline-block" />
          <span>Left: Original</span>
          <span className="mx-1">|</span>
          <span className="w-2 h-2 rounded-full bg-primary inline-block" />
          <span>Right: Generated</span>
        </div>
      )}
    </div>
  );
};

export default ComparisonControls;
