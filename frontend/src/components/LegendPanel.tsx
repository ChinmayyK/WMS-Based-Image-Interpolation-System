const LegendPanel = () => {
  const items = [
    { color: "bg-primary", label: "Acquisition Frame", desc: "Native WMS Sensor Data" },
    { color: "bg-confidence-high", label: "High Confidence", desc: "> 90% Structural Similarity" },
    { color: "bg-confidence-medium", label: "Nominal Confidence", desc: "70-90% Similarity" },
    { color: "bg-confidence-low", label: "Low Confidence", desc: "< 70% Stability" },
  ];

  return (
    <div className="absolute bottom-6 left-6 z-10 glass p-5 min-w-[200px] rounded-xl flex flex-col gap-4 shadow-2xl transition-all hover:scale-[1.02]">
      <div className="flex flex-col gap-1">
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-primary/70 font-bold">Key Indicator</h3>
        <p className="text-[9px] text-muted-foreground/60 italic font-mono">Data Validation Legend</p>
      </div>

      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div key={item.label} className="flex flex-col gap-0.5 group">
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${item.color} shadow-[0_0_8px_rgba(255,255,255,0.1)] group-hover:scale-110 transition-transform`} />
              <span className="text-[11px] font-bold text-foreground/90 tracking-wide">{item.label}</span>
            </div>
            <span className="ml-5 text-[9px] text-muted-foreground/40 font-mono">{item.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LegendPanel;
