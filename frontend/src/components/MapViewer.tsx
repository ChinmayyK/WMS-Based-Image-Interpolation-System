import { useEffect, useRef, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import OSM from "ol/source/OSM";
import "ol/ol.css";
import MapControlsPanel from "./MapControlsPanel";
import LegendPanel from "./LegendPanel";

interface MapViewerProps {
  opacity: number;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
}

const DEFAULT_CENTER: [number, number] = [8600000, 2400000];
const DEFAULT_ZOOM = 5;

const MapViewer = ({
  opacity,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
}: MapViewerProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({
          source: new OSM(),
          opacity: 1,
        }),
      ],
      view: new View({
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
      }),
    });

    mapInstanceRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const layers = mapInstanceRef.current.getLayers().getArray();
    if (layers.length > 0) {
      layers[0].setOpacity(showOverlay ? opacity : 1);
    }
  }, [opacity, showOverlay]);

  const handleResetView = useCallback(() => {
    if (!mapInstanceRef.current) return;
    const view = mapInstanceRef.current.getView();
    view.animate({
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      duration: 500,
    });
  }, []);

  return (
    <div className="relative w-full h-full bg-map-bg rounded overflow-hidden border">
      <div ref={mapRef} className="w-full h-full" />

      <div className="absolute top-3 left-3 z-10 bg-card/85 border rounded px-3 py-1.5 text-xs font-mono text-muted-foreground">
        Base Layer: OpenStreetMap
      </div>

      <MapControlsPanel
        onResetView={handleResetView}
        showOverlay={showOverlay}
        onToggleOverlay={onToggleOverlay}
        showConfidence={showConfidence}
        onToggleConfidence={onToggleConfidence}
      />

      <LegendPanel />
    </div>
  );
};

export default MapViewer;
