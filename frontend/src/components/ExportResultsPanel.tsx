interface ExportResultsPanelProps {
  exportData: {
    outputs: {
      original_mp4?: string;
      original_webm?: string;
      interpolated_mp4?: string;
      interpolated_webm?: string;
      hls?: string;
      metadata?: string;
    };
    validation?: Record<string, { valid: boolean; duration?: number; codec?: string; nb_frames?: string }>;
    resolution?: string;
    observedFrameCount?: number;
    totalFrameCount?: number;
  } | null;
  isExporting: boolean;
  onExport: () => void;
  jobCompleted: boolean;
}

const ExportResultsPanel = ({ exportData, isExporting, onExport, jobCompleted }: ExportResultsPanelProps) => {
  if (!jobCompleted) return null;

  return (
    <div className="glass rounded-xl p-4 shadow-2xl border border-white/10">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] font-bold font-mono text-primary tracking-[0.2em] uppercase">
          Export Results
        </h3>
        <button
          onClick={onExport}
          disabled={isExporting}
          className="bg-primary/20 hover:bg-primary/30 text-primary text-xs font-bold uppercase tracking-wider px-4 py-2 rounded transition-colors disabled:opacity-50 flex items-center gap-2 border border-primary/30"
        >
          {isExporting ? (
            <>
              <div className="w-3 h-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              Exporting...
            </>
          ) : exportData ? (
            "Re-Export"
          ) : (
            "Export Results"
          )}
        </button>
      </div>

      {exportData && (
        <div className="space-y-3">
          {/* Stats */}
          <div className="flex gap-4 text-[10px] font-mono text-muted-foreground">
            <span>{exportData.resolution}</span>
            <span>{exportData.observedFrameCount} observed</span>
            <span>{exportData.totalFrameCount} total</span>
          </div>

          {/* Download Links */}
          <div className="grid grid-cols-2 gap-2">
            <DownloadLink
              label="Original MP4"
              url={exportData.outputs.original_mp4}
              badge="H.264"
              color="text-observed"
            />
            <DownloadLink
              label="Original WebM"
              url={exportData.outputs.original_webm}
              badge="VP9"
              color="text-observed"
            />
            <DownloadLink
              label="Interpolated MP4"
              url={exportData.outputs.interpolated_mp4}
              badge="H.264"
              color="text-confidence-high"
            />
            <DownloadLink
              label="Interpolated WebM"
              url={exportData.outputs.interpolated_webm}
              badge="VP9"
              color="text-confidence-high"
            />
          </div>

          {/* Extra links */}
          <div className="flex gap-3 pt-2 border-t border-white/5">
            {exportData.outputs.hls && (
              <a
                href={exportData.outputs.hls}
                target="_blank"
                rel="noreferrer"
                className="text-[10px] font-mono text-primary hover:underline"
              >
                HLS Stream ↗
              </a>
            )}
            {exportData.outputs.metadata && (
              <a
                href={exportData.outputs.metadata}
                target="_blank"
                rel="noreferrer"
                className="text-[10px] font-mono text-muted-foreground hover:text-foreground"
              >
                Metadata JSON ↗
              </a>
            )}
          </div>

          {/* Validation */}
          {exportData.validation && (
            <div className="pt-2 border-t border-white/5">
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">ffprobe validation</span>
              <div className="mt-1 grid grid-cols-2 gap-1">
                {Object.entries(exportData.validation).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-1.5 text-[10px] font-mono">
                    <div className={`w-1.5 h-1.5 rounded-full ${val.valid ? 'bg-confidence-high' : 'bg-destructive'}`} />
                    <span className="text-muted-foreground">{key.replace('_', ' ')}</span>
                    {val.valid && val.codec && (
                      <span className="text-foreground/60">{val.codec}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

function DownloadLink({ label, url, badge, color }: { label: string; url?: string; badge: string; color: string }) {
  if (!url) return null;
  return (
    <a
      href={url}
      download
      className="flex items-center justify-between gap-2 bg-background/50 hover:bg-background/80 border border-white/5 rounded px-3 py-2 transition-colors group"
    >
      <div className="flex items-center gap-2">
        <svg className={`w-3.5 h-3.5 ${color} opacity-70 group-hover:opacity-100 transition-opacity`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        <span className="text-[11px] font-mono text-foreground/80 group-hover:text-foreground">{label}</span>
      </div>
      <span className="text-[9px] font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded">{badge}</span>
    </a>
  );
}

export default ExportResultsPanel;
