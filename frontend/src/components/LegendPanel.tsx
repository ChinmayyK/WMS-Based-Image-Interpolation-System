const LegendPanel = () => {
  const items = [
    { color: "bg-primary", label: "Satellite Frame" },
    { color: "bg-confidence-high", label: "High Confidence" },
    { color: "bg-confidence-medium", label: "Medium Confidence" },
    { color: "bg-confidence-low", label: "Low Confidence" },
  ];

  return (
    <div className="absolute bottom-4 left-4 z-10 bg-panel/80 backdrop-blur-md border border-border/50 rounded-sm p-3 min-w-[160px] shadow-2xl">
      <h3 className="text-[10px] uppercase tracking-widest text-muted-foreground font-mono mb-2 border-b border-border/50 pb-1.5">
        Map Legend
      </h3>
      <div className="space-y-2 mt-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <div className={`w-3 h-1.5 rounded-sm ${item.color} shadow-sm`} />
            <span className="text-[10px] font-mono text-foreground tracking-wide">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LegendPanel;
