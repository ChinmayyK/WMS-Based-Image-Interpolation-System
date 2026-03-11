interface MapControlsPanelProps {
  onResetView: () => void;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
  showClouds: boolean;
  onToggleClouds: () => void;
  showVectors: boolean;
  onToggleVectors: () => void;
}

const MapControlsPanel = ({
  onResetView,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
  showClouds,
  onToggleClouds,
  showVectors,
  onToggleVectors,
}: MapControlsPanelProps) => {
  return (
    <div className="absolute top-4 right-4 z-10 bg-panel/80 backdrop-blur-md border border-border/50 rounded-sm p-4 w-52 shadow-2xl transition-all duration-300">
      <h3 className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono mb-3 border-b border-border/50 pb-2">
        Layer Management
      </h3>
      
      <div className="space-y-3 font-mono">
        <button
          onClick={onResetView}
          className="w-full text-left px-2 py-1.5 text-[11px] text-foreground hover:bg-white/5 hover:text-primary rounded-sm transition-colors flex items-center gap-2"
        >
          <div className="w-1 h-1 rounded-full bg-primary/50" />
          Reset Coordinates
        </button>
        
        <div className="border-t border-border/30 my-2" />
        
        <label className="flex items-center justify-between group cursor-pointer px-2 py-1 rounded-sm hover:bg-white/5 transition-colors">
          <span className="text-[11px] text-foreground group-hover:text-primary transition-colors">Satellite Overlay</span>
          <div className="relative">
            <input
              type="checkbox"
              checked={showOverlay}
              onChange={onToggleOverlay}
              className="sr-only"
            />
            <div className={`w-6 h-3 rounded-full transition-colors ${showOverlay ? "bg-primary/50" : "bg-muted"}`}>
              <div className={`absolute top-0.5 left-0.5 w-2 h-2 rounded-full bg-white transition-transform ${showOverlay ? "translate-x-3" : ""}`} />
            </div>
          </div>
        </label>
        
        <label className="flex items-center justify-between group cursor-pointer px-2 py-1 rounded-sm hover:bg-white/5 transition-colors">
          <span className="text-[11px] text-foreground group-hover:text-primary transition-colors">Confidence Mask</span>
          <div className="relative">
            <input
              type="checkbox"
              checked={showConfidence}
              onChange={onToggleConfidence}
              className="sr-only"
            />
            <div className={`w-6 h-3 rounded-full transition-colors ${showConfidence ? "bg-primary/50" : "bg-muted"}`}>
              <div className={`absolute top-0.5 left-0.5 w-2 h-2 rounded-full bg-white transition-transform ${showConfidence ? "translate-x-3" : ""}`} />
            </div>
          </div>
        </label>

        <label className="flex items-center justify-between group cursor-pointer px-2 py-1 rounded-sm hover:bg-white/5 transition-colors">
          <span className="text-[11px] text-yellow-500/80 group-hover:text-yellow-400 transition-colors">Optical Flow (Vectors)</span>
           <div className="relative">
            <input
              type="checkbox"
              checked={showVectors}
              onChange={onToggleVectors}
              className="sr-only"
            />
            <div className={`w-6 h-3 rounded-full transition-colors ${showVectors ? "bg-yellow-500/50" : "bg-muted"}`}>
              <div className={`absolute top-0.5 left-0.5 w-2 h-2 rounded-full bg-white transition-transform ${showVectors ? "translate-x-3" : ""}`} />
            </div>
          </div>
        </label>

        <label className="flex items-center justify-between group cursor-pointer px-2 py-1 rounded-sm hover:bg-white/5 transition-colors">
          <span className="text-[11px] text-blue-400/80 group-hover:text-blue-300 transition-colors">Cloud Segmentation</span>
          <div className="relative">
            <input
              type="checkbox"
              checked={showClouds}
              onChange={onToggleClouds}
              className="sr-only"
            />
            <div className={`w-6 h-3 rounded-full transition-colors ${showClouds ? "bg-blue-400/50" : "bg-muted"}`}>
              <div className={`absolute top-0.5 left-0.5 w-2 h-2 rounded-full bg-white transition-transform ${showClouds ? "translate-x-3" : ""}`} />
            </div>
          </div>
        </label>
      </div>
    </div>
  );
};

export default MapControlsPanel;
