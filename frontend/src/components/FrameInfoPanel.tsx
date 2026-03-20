import { ReactNode } from "react";
import {
  CATEGORY_STYLES,
  formatConfidenceValue,
  getConfidenceBreakdown,
  getConfidenceCategory,
  getDisplayFrameType,
  getGapFillDescription,
  getMetricValue,
  getPairGapLabel,
  getRuntimeSummary,
  getWmsSummary,
  isInterpolationFrame,
} from "@/lib/frame-status";
import { SatelliteFrame, ComparisonMode, RuntimeDiagnostics } from "@/lib/types";
import ComparisonControls from "./ComparisonControls";

interface FrameInfoPanelProps {
  frame: SatelliteFrame;
  frameIndex: number;
  totalFrames: number;
  comparisonMode: ComparisonMode;
  onComparisonModeChange: (mode: ComparisonMode) => void;
  toggleView: "original" | "generated";
  onToggleViewChange: (view: "original" | "generated") => void;
  isDemoMode: boolean;
  showRawSensorGaps: boolean;
  runtimeDiagnostics?: RuntimeDiagnostics | null;
  interpolationNotice?: string | null;
}

const ConfidenceIndicator = ({ category }: { category: ReturnType<typeof getConfidenceCategory> }) => {
  const style = CATEGORY_STYLES[category];

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${style.dot}`} />
      <span className="text-xs text-muted-foreground">{category}</span>
    </div>
  );
};

const FrameInfoPanel = ({
  frame,
  frameIndex,
  totalFrames,
  comparisonMode,
  onComparisonModeChange,
  toggleView,
  onToggleViewChange,
  isDemoMode,
  showRawSensorGaps,
  runtimeDiagnostics,
  interpolationNotice,
}: FrameInfoPanelProps) => {
  const confidenceCategory = getConfidenceCategory(frame);
  const frameType = getDisplayFrameType(frame);
  const confidenceBreakdown = getConfidenceBreakdown(frame);
  const modelDiagnostics = runtimeDiagnostics?.interpolation?.model;
  const executionDiagnostics = runtimeDiagnostics?.interpolation?.execution;
  const confidenceProfile = runtimeDiagnostics?.confidence;
  const latestWmsRequest = runtimeDiagnostics?.wms?.lastRequests?.length
    ? runtimeDiagnostics.wms.lastRequests[runtimeDiagnostics.wms.lastRequests.length - 1]
    : null;
  const latestExport = runtimeDiagnostics?.export;
  const latestEvaluation = runtimeDiagnostics?.evaluation;
  const isAIFrame = isInterpolationFrame(frame);
  const gapFillDescription = getGapFillDescription(frame, showRawSensorGaps);
  const pairGapLabel = getPairGapLabel(frame);

  return (
    <div className="w-[340px] glass h-full flex flex-col rounded-xl overflow-hidden border-white/10 shadow-3xl">
      <div className="px-6 py-5 border-b border-white/5 bg-white/5">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
          <h2 className="text-[11px] font-bold font-mono text-primary tracking-[0.2em] uppercase">
            Transparency Panel
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="p-4 bg-primary/5 border-b border-white/5">
          <ComparisonControls
            mode={comparisonMode}
            onModeChange={onComparisonModeChange}
            toggleView={toggleView}
            onToggleViewChange={onToggleViewChange}
          />
        </div>

        <div className="px-6 py-6 space-y-8">
          <div className="grid grid-cols-1 gap-6">
            <AnalyticsRow label="Frame Type" value={frameType} />
            <AnalyticsRow label="Acquisition Time" value={frame.timestamp} />
            <AnalyticsRow
              label="Confidence / State"
              value={
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono font-bold text-foreground">{formatConfidenceValue(frame)}</span>
                  <ConfidenceIndicator category={confidenceCategory} />
                </div>
              }
            />
            {confidenceBreakdown && <AnalyticsRow label="Adaptive Metrics" value={confidenceBreakdown} />}
            {pairGapLabel && <AnalyticsRow label="Pair Gap" value={pairGapLabel} />}
            {frame.metrics?.normalizedSSIM !== undefined && (
              <AnalyticsRow label="Normalized SSIM" value={getMetricValue(frame.metrics.normalizedSSIM)} />
            )}
            {frame.metrics?.normalizedMAD !== undefined && (
              <AnalyticsRow label="Normalized MAD" value={getMetricValue(frame.metrics.normalizedMAD)} />
            )}
            {frame.hasSensorGap && (
              <AnalyticsRow
                label="Gap Coverage"
                value={`${(frame.gapCoveragePct ?? 0).toFixed(2)}%`}
              />
            )}
            {gapFillDescription && <AnalyticsRow label="Gap Mode" value={gapFillDescription} />}
            {frame.placeholderReason && (
              <AnalyticsRow label="Placeholder Reason" value={frame.placeholderReason} highlight />
            )}
            {interpolationNotice && (
              <AnalyticsRow
                label="Guardrail"
                value={interpolationNotice}
                highlight={interpolationNotice.toLowerCase().includes("disabled")}
              />
            )}
            <AnalyticsRow label="Sequence ID" value={`${frameIndex + 1} / ${totalFrames}`} />
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <AnalyticsRow label="Runtime Status" value={getRuntimeSummary(runtimeDiagnostics)} />
            {modelDiagnostics ? (
              <>
                <AnalyticsRow label="Model" value={modelDiagnostics.name} />
                <AnalyticsRow label="Framework" value={modelDiagnostics.framework} />
                <AnalyticsRow
                  label="Weights"
                  value={`${modelDiagnostics.weightsFile} (${modelDiagnostics.weightsSizeMB?.toFixed(2) ?? "?"} MB)`}
                />
                <AnalyticsRow label="Device" value={modelDiagnostics.device ?? "Unavailable"} />
                <AnalyticsRow
                  label="Execution"
                  value={executionDiagnostics?.fallbackActive ? "Fallback interpolation active (OpenCV)" : "Neural inference active"}
                  highlight={Boolean(executionDiagnostics?.fallbackActive)}
                />
                {executionDiagnostics?.lastRun && (
                  <AnalyticsRow label="Last Inference" value={`${executionDiagnostics.lastRun.durationMs.toFixed(2)} ms`} />
                )}
                {executionDiagnostics?.lastBatch && (
                  <>
                    <AnalyticsRow label="Frames Generated" value={`${executionDiagnostics.lastBatch.generatedFrames}`} />
                    <AnalyticsRow label="Strategy" value={executionDiagnostics.lastBatch.strategy ?? "recursive_bisection"} />
                  </>
                )}
                {executionDiagnostics?.performanceExplanation && (
                  <p className="text-[10px] font-mono text-muted-foreground leading-relaxed">
                    {executionDiagnostics.performanceExplanation}
                  </p>
                )}
              </>
            ) : (
              <p className="text-[10px] font-mono text-muted-foreground leading-relaxed">
                Switch to API mode for live model, weights, device, and inference diagnostics.
              </p>
            )}
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <AnalyticsRow label="WMS Summary" value={getWmsSummary(runtimeDiagnostics)} />
            <AnalyticsRow label="WMS Source" value={NASA_SOURCE_LABEL} />
            <AnalyticsRow label="Endpoint" value={frame.wmsUrl ?? latestWmsRequest?.endpoint ?? "Unavailable"} />
            <AnalyticsRow label="Layer" value={frame.wmsLayer ?? "MODIS_Terra_CorrectedReflectance_TrueColor"} />
            <AnalyticsRow label="CRS" value={frame.wmsCrs ?? "EPSG:3857"} />
            <AnalyticsRow label="BBOX" value={(frame.bbox ?? [68.0, 6.0, 98.0, 36.0]).join(", ")} />
            <AnalyticsRow label="Frame Timestamp" value={frame.wmsDate ?? frame.timestamp} />
            {latestWmsRequest && (
              <>
                <AnalyticsRow label="Last WMS Status" value={`${latestWmsRequest.statusCode ?? "?"}`} />
                <AnalyticsRow label="Last WMS URL" value={<UrlValue value={latestWmsRequest.requestedUrl} />} />
              </>
            )}
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <AnalyticsRow label="Confidence Session" value={confidenceProfile ? `${confidenceProfile.sampleCount} observed frames` : "Unavailable"} />
            {confidenceProfile && (
              <>
                <AnalyticsRow label="Baseline Pairs" value={`${confidenceProfile.baselinePairs}`} />
                <AnalyticsRow label="Fallback Defaults" value={confidenceProfile.usedFallbackDefaults ? "Yes" : "No"} />
                <AnalyticsRow label="SSIM Window" value={`${confidenceProfile.ssimFloor.toFixed(3)} → ${confidenceProfile.ssimCeiling.toFixed(3)}`} />
                <AnalyticsRow label="MAD Window" value={`${confidenceProfile.madFloor.toFixed(2)} → ${confidenceProfile.madCeiling.toFixed(2)}`} />
              </>
            )}
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <AnalyticsRow label="Latest Export" value={latestExport ? `${latestExport.frameCount} frames @ ${latestExport.fps} fps` : "Not yet exported"} />
            {latestExport && (
              <div className="flex flex-col gap-2">
                <a className="text-[10px] font-mono text-primary underline underline-offset-4" href={latestExport.mp4Url} target="_blank" rel="noreferrer">
                  Download MP4
                </a>
                <a className="text-[10px] font-mono text-primary underline underline-offset-4" href={latestExport.webmUrl} target="_blank" rel="noreferrer">
                  Download WebM
                </a>
                <a className="text-[10px] font-mono text-primary underline underline-offset-4" href={latestExport.metadataUrl} target="_blank" rel="noreferrer">
                  Download Export Metadata
                </a>
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <AnalyticsRow
              label="Evaluation"
              value={latestEvaluation ? `${latestEvaluation.datasetCount} datasets` : "Not yet evaluated"}
            />
            {latestEvaluation && (
              <>
                <AnalyticsRow label="Average PSNR" value={latestEvaluation.averages.psnr.toFixed(2)} />
                <AnalyticsRow label="Average SSIM" value={latestEvaluation.averages.ssim.toFixed(4)} />
                <a className="text-[10px] font-mono text-primary underline underline-offset-4" href="/data/evaluations/latest_evaluation.json" target="_blank" rel="noreferrer">
                  Download Evaluation Report
                </a>
              </>
            )}
          </div>

          {isAIFrame && (
            <div className="pt-6 border-t border-white/5">
              <div className="rounded-md border border-confidence-low/35 bg-confidence-low/18 px-3 py-2 text-[10px] font-mono text-white">
                AI-GENERATED — NOT OBSERVED DATA
              </div>
            </div>
          )}

          <div className="pt-6 border-t border-white/5 flex items-center justify-between">
            <label className="text-[9px] uppercase tracking-widest text-muted-foreground/60 font-bold">
              Service Status
            </label>
            <div className="flex items-center gap-2 px-2 py-1 rounded bg-white/5 border border-white/5">
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${isDemoMode ? "bg-confidence-medium" : "bg-observed"}`} />
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-foreground">
                {isDemoMode ? "DEMO_MODE" : "LIVE_API"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const AnalyticsRow = ({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: ReactNode;
  highlight?: boolean;
}) => (
  <div className="flex flex-col gap-1 pr-2">
    <label className="text-[9px] uppercase tracking-widest text-muted-foreground/60 font-bold">
      {label}
    </label>
    <div className={`text-xs font-mono font-medium break-all ${highlight ? "text-confidence-low" : "text-foreground/90"}`}>
      {value}
    </div>
  </div>
);

const UrlValue = ({ value }: { value: string }) => (
  <span className="text-[10px] font-mono text-foreground/80 break-all">
    {value}
  </span>
);

const NASA_SOURCE_LABEL = "NASA GIBS";

export default FrameInfoPanel;
