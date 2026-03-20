import { useEffect, useState } from "react";

type JobRequest = {
  bbox: [number, number, number, number];
  start_time: string;
  end_time: string;
  layers: string;
  interpolation_steps: number;
};

type LayerInfo = {
  latestAvailableTime: string | null;
  source: string;
};

interface JobSubmissionPanelProps {
  onSubmit: (jobReq: JobRequest) => void;
  isSubmitting: boolean;
}

const SOURCE_LAYER_OPTIONS = {
  "GOES-East": [
    { value: "GOES-East_ABI_Band2_Red_Visible_1km", label: "Band 2 (Red Visible)" },
    { value: "GOES-East_ABI_Band13_Clean_Infrared", label: "Band 13 (Clean IR)" },
  ],
  "GOES-West": [
    { value: "GOES-West_ABI_Band2_Red_Visible_1km", label: "Band 2 (Red Visible)" },
    { value: "GOES-West_ABI_Band13_Clean_Infrared", label: "Band 13 (Clean IR)" },
  ],
} as const;

const DEFAULT_SOURCE = "GOES-East";
const DEFAULT_WINDOW_MINUTES = 90;

const pad = (n: number) => n.toString().padStart(2, "0");
const formatDt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

const JobSubmissionPanel = ({ onSubmit, isSubmitting }: JobSubmissionPanelProps) => {
  const [source, setSource] = useState<keyof typeof SOURCE_LAYER_OPTIONS>(DEFAULT_SOURCE);
  const [layer, setLayer] = useState(SOURCE_LAYER_OPTIONS[DEFAULT_SOURCE][0].value);
  const [bboxMinX, setBboxMinX] = useState("-10575351.63");
  const [bboxMinY, setBboxMinY] = useState("1345708.41");
  const [bboxMaxX, setBboxMaxX] = useState("-6679169.45");
  const [bboxMaxY, setBboxMaxY] = useState("4865942.28");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [depth, setDepth] = useState(1);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [layerInfo, setLayerInfo] = useState<LayerInfo | null>(null);
  const [availabilityMessage, setAvailabilityMessage] = useState<string | null>(null);

  useEffect(() => {
    const availableLayers = SOURCE_LAYER_OPTIONS[source];
    if (!availableLayers.some((option) => option.value === layer)) {
      setLayer(availableLayers[0].value);
    }
  }, [source, layer]);

  useEffect(() => {
    let cancelled = false;

    const applyFallbackWindow = () => {
      const fallbackEnd = new Date();
      const fallbackStart = new Date(fallbackEnd.getTime() - DEFAULT_WINDOW_MINUTES * 60 * 1000);
      if (!cancelled) {
        setEndTime(formatDt(fallbackEnd));
        setStartTime(formatDt(fallbackStart));
      }
    };

    const loadLayerInfo = async () => {
      try {
        const response = await fetch(`/api/wms/layer-info?layer=${encodeURIComponent(layer)}&crs=EPSG%3A3857&provider=auto`);
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `Layer lookup failed (${response.status})`);
        }
        if (cancelled) return;
        setLayerInfo({
          latestAvailableTime: payload.latestAvailableTime,
          source: payload.source,
        });
        if (payload.latestAvailableTime) {
          const latest = new Date(payload.latestAvailableTime);
          const windowEnd = new Date(latest.getTime());
          const windowStart = new Date(windowEnd.getTime() - DEFAULT_WINDOW_MINUTES * 60 * 1000);
          setEndTime(formatDt(windowEnd));
          setStartTime(formatDt(windowStart));
          setAvailabilityMessage(`Using latest available ${payload.source} time: ${payload.latestAvailableTime}`);
        } else {
          applyFallbackWindow();
          setAvailabilityMessage("Could not determine latest available layer time. Falling back to local time.");
        }
      } catch (error) {
        applyFallbackWindow();
        if (!cancelled) {
          setLayerInfo(null);
          setAvailabilityMessage(
            error instanceof Error
              ? `Layer availability lookup failed: ${error.message}`
              : "Layer availability lookup failed.",
          );
        }
      }
    };

    void loadLayerInfo();
    return () => {
      cancelled = true;
    };
  }, [layer]);

  const bbox = [Number(bboxMinX), Number(bboxMinY), Number(bboxMaxX), Number(bboxMaxY)] as [number, number, number, number];
  const startDate = startTime ? new Date(startTime) : null;
  const endDate = endTime ? new Date(endTime) : null;
  const validationErrors: string[] = [];

  if (!bbox.every((value) => Number.isFinite(value))) {
    validationErrors.push("Bounding box must contain valid numeric coordinates.");
  } else {
    if (bbox[0] >= bbox[2]) validationErrors.push("Bounding box min X must be less than max X.");
    if (bbox[1] >= bbox[3]) validationErrors.push("Bounding box min Y must be less than max Y.");
  }

  if (!startDate || Number.isNaN(startDate.getTime())) {
    validationErrors.push("Start time is required.");
  }
  if (!endDate || Number.isNaN(endDate.getTime())) {
    validationErrors.push("End time is required.");
  }
  if (startDate && endDate && startDate >= endDate) {
    validationErrors.push("Start time must be earlier than end time.");
  }
  if (startDate && endDate) {
    const spanMinutes = (endDate.getTime() - startDate.getTime()) / 60000;
    if (spanMinutes > 24 * 60) {
      validationErrors.push("Requested time range must be 24 hours or less for a single job.");
    }
  }

  if (!SOURCE_LAYER_OPTIONS[source].some((option) => option.value === layer)) {
    validationErrors.push("Selected layer does not match the chosen GOES source.");
  }
  if (layerInfo?.latestAvailableTime && endDate) {
    const latestAvailable = new Date(layerInfo.latestAvailableTime);
    if (endDate > latestAvailable) {
      validationErrors.push(`End time is after the latest available frame (${layerInfo.latestAvailableTime}).`);
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (validationErrors.length > 0 || !startDate || !endDate) {
      return;
    }
    onSubmit({
      bbox,
      start_time: startDate.toISOString().replace(".000Z", "Z"),
      end_time: endDate.toISOString().replace(".000Z", "Z"),
      layers: layer,
      interpolation_steps: depth,
    });
  };

  return (
    <div className="glass rounded-xl p-4 md:p-6 shadow-2xl border border-white/10 w-full max-w-md mx-auto">
      <h2 className="text-lg font-mono font-bold text-primary mb-4 tracking-widest uppercase">
        Create Job
      </h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold">Source</label>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as keyof typeof SOURCE_LAYER_OPTIONS)}
            className="bg-background border border-border rounded px-2 py-1.5 text-sm outline-none focus:border-primary transition-colors text-foreground"
          >
            {Object.keys(SOURCE_LAYER_OPTIONS).map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold">Layer</label>
          <select
            value={layer}
            onChange={(e) => setLayer(e.target.value)}
            className="bg-background border border-border rounded px-2 py-1.5 text-sm outline-none focus:border-primary transition-colors text-foreground"
          >
            {SOURCE_LAYER_OPTIONS[source].map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold">Bounding Box (EPSG:3857)</label>
          <div className="grid grid-cols-2 gap-2">
            <input type="number" step="any" placeholder="Min X" value={bboxMinX} onChange={(e) => setBboxMinX(e.target.value)} className="bg-background border border-border rounded px-2 py-1 text-sm text-foreground focus:border-primary outline-none" required />
            <input type="number" step="any" placeholder="Min Y" value={bboxMinY} onChange={(e) => setBboxMinY(e.target.value)} className="bg-background border border-border rounded px-2 py-1 text-sm text-foreground focus:border-primary outline-none" required />
            <input type="number" step="any" placeholder="Max X" value={bboxMaxX} onChange={(e) => setBboxMaxX(e.target.value)} className="bg-background border border-border rounded px-2 py-1 text-sm text-foreground focus:border-primary outline-none" required />
            <input type="number" step="any" placeholder="Max Y" value={bboxMaxY} onChange={(e) => setBboxMaxY(e.target.value)} className="bg-background border border-border rounded px-2 py-1 text-sm text-foreground focus:border-primary outline-none" required />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Use a GOES-visible EPSG:3857 extent. The default covers the Gulf and western Atlantic.</p>
        </div>

        <div className="flex gap-4">
          <div className="flex flex-col gap-1 flex-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold">Start Time</label>
            <input type="datetime-local" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="bg-background border border-border rounded px-2 py-1.5 text-sm text-foreground outline-none focus:border-primary w-full" required />
          </div>
          <div className="flex flex-col gap-1 flex-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold">End Time</label>
            <input type="datetime-local" value={endTime} onChange={(e) => setEndTime(e.target.value)} className="bg-background border border-border rounded px-2 py-1.5 text-sm text-foreground outline-none focus:border-primary w-full" required />
          </div>
        </div>
        {availabilityMessage && (
          <div className="rounded-lg border border-primary/20 bg-primary/10 p-3 text-xs text-muted-foreground">
            {availabilityMessage}
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground uppercase tracking-wider font-bold flex justify-between">
            <span>Interpolation Depth</span>
            <span className="text-primary">{depth} recursion step{depth === 1 ? "" : "s"}</span>
          </label>
          <input
            type="range"
            min="1"
            max="7"
            value={depth}
            onChange={(e) => setDepth(parseInt(e.target.value, 10))}
            className="w-full accent-primary"
          />
        </div>

        {submitAttempted && validationErrors.length > 0 && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive space-y-1">
            {validationErrors.map((error) => (
              <div key={error}>{error}</div>
            ))}
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting || validationErrors.length > 0}
          className="mt-4 bg-primary text-primary-foreground hover:bg-primary/90 font-bold uppercase tracking-widest py-3 rounded transition-colors disabled:opacity-50 flex justify-center items-center gap-2"
        >
          {isSubmitting ? (
            <>
              <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" />
              Submitting...
            </>
          ) : (
            "Submit Job"
          )}
        </button>
      </form>
    </div>
  );
};

export default JobSubmissionPanel;
