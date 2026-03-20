import { Map, Zap, Layers, Wind, CloudDrizzle, RefreshCw } from "lucide-react";

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
    <div className="absolute top-16 right-4 z-40 glass p-2 rounded-xl flex flex-col gap-2 shadow-2xl border border-white/10 md:top-4 md:right-32 md:flex-row md:items-center">
      <ControlButton 
        active={showOverlay} 
        onClick={onToggleOverlay} 
        icon={<Map size={14} />} 
        label="L1B BASE" 
        color="primary"
      />
      <ControlButton 
        active={showRawSensorGaps} 
        onClick={onToggleRawSensorGaps} 
        icon={<Layers size={14} />} 
        label="RAW GAPS" 
        color="gap"
      />
      <div className="h-px w-full bg-white/10 md:w-px md:h-4" />
      <ControlButton 
        active={showConfidence} 
        onClick={onToggleConfidence} 
        icon={<Zap size={14} />} 
        label="CONFIDENCE" 
        color="primary"
      />
      <ControlButton 
        active={showVectors} 
        onClick={onToggleVectors} 
        icon={<Wind size={14} />} 
        label="FLOW" 
        color="yellow"
      />
      <ControlButton 
        active={showClouds} 
        onClick={onToggleClouds} 
        icon={<CloudDrizzle size={14} />} 
        label="CLOUDS" 
        color="blue"
      />
      <div className="h-px w-full bg-white/10 md:w-px md:h-4" />
      <button
        onClick={onResetView}
        title="Reset Viewport"
        className="w-full md:w-auto flex items-center justify-center p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-all border border-transparent active:scale-95 text-foreground hover:text-primary"
      >
        <RefreshCw size={14} />
      </button>
    </div>
  );
};

interface ControlButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  color: 'primary' | 'yellow' | 'blue' | 'gap';
}

const ControlButton = ({ active, onClick, icon, label, color }: ControlButtonProps) => {
  const colorMap = {
    primary: 'bg-primary/20 text-primary border-primary/30',
    yellow: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30',
    blue: 'bg-blue-500/20 text-blue-500 border-blue-500/30',
    gap: 'bg-gap/20 text-gap border-gap/30',
  };

  const defaultStyle = "bg-transparent text-muted-foreground border-transparent hover:bg-white/5 hover:text-foreground";

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold tracking-widest transition-all border outline-none whitespace-nowrap ${
        active ? colorMap[color] : defaultStyle
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
};

export default MapControlsPanel;
