interface MapControlsPanelProps {
  onResetView: () => void;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
}

const MapControlsPanel = ({
  onResetView,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
}: MapControlsPanelProps) => {
  return (
    <div className="absolute top-3 right-3 z-10 bg-card/90 border rounded p-3 space-y-2 min-w-[160px]">
      <h3 className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans mb-2">
        Map Controls
      </h3>
      <button
        onClick={onResetView}
        className="w-full text-left px-2 py-1.5 text-xs font-mono text-foreground hover:bg-muted rounded transition-colors"
      >
        Reset View
      </button>
      <div className="border-t" />
      <label className="flex items-center gap-2 px-2 py-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showOverlay}
          onChange={onToggleOverlay}
          className="w-3 h-3 accent-primary"
        />
        <span className="text-xs text-foreground">Satellite Overlay</span>
      </label>
      <label className="flex items-center gap-2 px-2 py-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showConfidence}
          onChange={onToggleConfidence}
          className="w-3 h-3 accent-primary"
        />
        <span className="text-xs text-foreground">Confidence Layer</span>
      </label>
    </div>
  );
};

export default MapControlsPanel;
