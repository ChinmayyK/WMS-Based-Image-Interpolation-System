import { DataSource } from "@/lib/types";

interface DashboardHeaderProps {
  dataSource: DataSource;
  onToggleDataSource: () => void;
}

const DashboardHeader = ({ dataSource, onToggleDataSource }: DashboardHeaderProps) => {
  return (
    <header className="flex items-center justify-between px-6 py-2 border-b border-border/50 bg-background/95 backdrop-blur z-50">
      <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold font-mono tracking-wider text-foreground">
            WMS-BASED IMAGE INTERPOLATION SYSTEM
          </h1>
          <p className="text-[10px] text-muted-foreground font-mono mt-0.5 tracking-widest uppercase">
            Spatio-Temporal Satellite Analysis
          </p>
        </div>
      </div>
      
      <div className="flex items-center gap-6 text-[10px] text-muted-foreground font-mono tracking-wider uppercase">
        <button
          onClick={onToggleDataSource}
          className={`flex items-center gap-2 px-3 py-1.5 border rounded-sm transition-all duration-300 ${
            dataSource === "demo"
              ? "bg-confidence-medium/10 border-confidence-medium/30 text-confidence-medium hover:bg-confidence-medium/20"
              : "bg-confidence-high/10 border-confidence-high/30 text-confidence-high hover:bg-confidence-high/20"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${
            dataSource === "demo" ? "bg-confidence-medium" : "bg-confidence-high"
          }`} />
          {dataSource === "demo" ? "DEMO MODE" : "LIVE SENSOR API"}
        </button>
        
        <div className="flex items-center gap-2 pl-4 border-l border-border/50">
          <span>SYS. REV 2.4</span>
        </div>
        
        <div className="flex items-center gap-2 text-confidence-high">
          <span className="w-1.5 h-1.5 rounded-full bg-confidence-high opacity-80" />
          <span>Telemtry Nominal</span>
        </div>
      </div>
    </header>
  );
};

export default DashboardHeader;
