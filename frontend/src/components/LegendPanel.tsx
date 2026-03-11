const LegendPanel = () => {
  const items = [
    { color: "bg-primary", label: "Satellite Frame" },
    { color: "bg-confidence-high", label: "High Confidence" },
    { color: "bg-confidence-medium", label: "Medium Confidence" },
    { color: "bg-confidence-low", label: "Low Confidence" },
  ];

  return (
    <div className="absolute bottom-3 left-3 z-10 bg-card/90 border rounded p-3 min-w-[150px]">
      <h3 className="text-[10px] uppercase tracking-wider text-muted-foreground font-sans mb-2">
        Legend
      </h3>
      <div className="space-y-1.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <div className={`w-3 h-2 rounded-sm ${item.color}`} />
            <span className="text-[11px] text-foreground">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LegendPanel;
