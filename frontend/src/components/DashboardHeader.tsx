import { DataSource } from "@/lib/types";

interface DashboardHeaderProps {
  dataSource: DataSource;
  onToggleDataSource: () => void;
}

const DashboardHeader = ({ dataSource, onToggleDataSource }: DashboardHeaderProps) => {
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b bg-secondary">
      <div>
        <h1 className="text-sm font-semibold font-mono tracking-wide text-foreground">
          WMS-Based Image Interpolation System
        </h1>
        <p className="text-xs text-muted-foreground font-sans mt-0.5">
          Spatio-Temporal Satellite Visualization
        </p>
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
        <button
          onClick={onToggleDataSource}
          className={`px-3 py-1 border rounded transition-colors ${
            dataSource === "demo"
              ? "bg-confidence-medium/20 border-confidence-medium/40 text-foreground"
              : "bg-confidence-high/20 border-confidence-high/40 text-foreground"
          }`}
        >
          {dataSource === "demo" ? "DEMO MODE" : "LIVE API"}
        </button>
        <span>GRATICULE v1.0</span>
        <span className="w-2 h-2 rounded-full bg-confidence-high inline-block" />
        <span>System Online</span>
      </div>
    </header>
  );
};

export default DashboardHeader;
