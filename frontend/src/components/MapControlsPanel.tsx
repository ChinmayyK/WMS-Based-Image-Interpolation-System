interface MapControlsPanelProps {
  onResetView: () => void;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showRawSensorGaps: boolean;
  onToggleRawSensorGaps: () => void;
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
  showRawSensorGaps,
  onToggleRawSensorGaps,
  showConfidence,
  onToggleConfidence,
  showClouds,
  onToggleClouds,
  showVectors,
  onToggleVectors,
}: MapControlsPanelProps) => {
  return (
    <div className="absolute top-6 right-6 z-10 glass p-5 w-64 rounded-xl flex flex-col gap-6 shadow-2xl">
      {/* Category: Scene Controls */}
      <div>
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-primary/70 font-bold mb-3">System Controls</h3>
        <button
          onClick={onResetView}
          className="w-full h-9 flex items-center justify-between px-3 rounded-lg bg-white/5 hover:bg-white/10 transition-all border border-white/5 active:scale-95 group"
        >
          <span className="text-[11px] font-medium text-foreground group-hover:text-primary transition-colors">Reset Viewport</span>
          <div className="w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(34,211,238,0.6)] animate-pulse" />
        </button>
      </div>

      {/* Category: Satellite Data */}
      <div className="flex flex-col gap-3">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-primary/70 font-bold mb-1">Observation Data</h3>
        <div className="flex flex-col gap-1">
          <LayerToggle 
            label="Satellite Imagery" 
            description="L1B Corrected Reflectance"
            checked={showOverlay} 
            onChange={onToggleOverlay} 
            color="primary" 
          />
          <LayerToggle
            label="Show Sensor Gaps"
            description="Scientific raw NoData wedges"
            checked={showRawSensorGaps}
            onChange={onToggleRawSensorGaps}
            color="gap"
          />
          <LayerToggle 
            label="Confidence Matrix" 
            description="Statistical Uncertainty"
            checked={showConfidence} 
            onChange={onToggleConfidence} 
            color="primary" 
          />
        </div>
      </div>

      {/* Category: AI Analytics */}
      <div className="flex flex-col gap-3">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-primary/70 font-bold mb-1">AI Deep Analytics</h3>
        <div className="flex flex-col gap-1">
          <LayerToggle 
            label="Optical Flow" 
            description="Motion Vector Analysis"
            checked={showVectors} 
            onChange={onToggleVectors} 
            color="yellow" 
          />
          <LayerToggle 
            label="Cloud Segments" 
            description="Neural Classification"
            checked={showClouds} 
            onChange={onToggleClouds} 
            color="blue" 
          />
        </div>
      </div>
    </div>
  );
};

interface LayerToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
  color: 'primary' | 'yellow' | 'blue' | 'gap';
}

const LayerToggle = ({ label, description, checked, onChange, color }: LayerToggleProps) => {
  const colorMap = {
    primary: 'bg-primary shadow-[0_0_8px_rgba(34,211,238,0.4)]',
    yellow: 'bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.4)]',
    blue: 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.4)]',
    gap: 'bg-gap shadow-[0_0_8px_rgba(117,117,117,0.4)]',
  };

  return (
    <label className="flex items-center justify-between group cursor-pointer p-2 rounded-lg hover:bg-white/5 transition-all outline-none focus-within:bg-white/5">
      <div className="flex flex-col">
        <span className={`text-[11px] font-bold transition-colors ${checked ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground/80'}`}>
          {label}
        </span>
        <span className="text-[9px] text-muted-foreground/60 group-hover:text-muted-foreground/80 lowercase italic font-mono">
          {description}
        </span>
      </div>
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          className="sr-only"
        />
        <div className={`w-8 h-4 rounded-full transition-all border border-white/10 ${checked ? 'bg-white/10' : 'bg-black/40'}`}>
          <div className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full transition-all duration-300 shadow-lg ${checked ? `translate-x-4 ${colorMap[color]}` : 'bg-white/20'}`} />
        </div>
      </div>
    </label>
  );
};

export default MapControlsPanel;
