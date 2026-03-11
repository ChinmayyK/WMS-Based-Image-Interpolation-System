import { useEffect, useRef, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import ImageLayer from "ol/layer/Image";
import OSM from "ol/source/OSM";
import Static from "ol/source/ImageStatic";
import { get as getProjection } from "ol/proj";
import "ol/ol.css";
import MapControlsPanel from "./MapControlsPanel";
import LegendPanel from "./LegendPanel";
import { SatelliteFrame } from "@/lib/types";

interface MapViewerProps {
  opacity: number;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
  currentFrame?: SatelliteFrame;
}

// Bounding box for the satellite overlay (EPSG:3857)
// This covers a region roughly over India
const OVERLAY_EXTENT = [8000000, 1800000, 9200000, 3000000];

const DEFAULT_CENTER: [number, number] = [8600000, 2400000];
const DEFAULT_ZOOM = 5;

const MapViewer = ({
  opacity,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
  currentFrame,
}: MapViewerProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);
  const overlayLayerRef = useRef<ImageLayer<Static> | null>(null);

  // Initialize map with OSM base layer
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
        projection: getProjection("EPSG:3857")!,
      }),
    });

    mapInstanceRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  // Update satellite overlay when currentFrame changes
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const map = mapInstanceRef.current;

    // Remove existing overlay
    if (overlayLayerRef.current) {
      map.removeLayer(overlayLayerRef.current);
      overlayLayerRef.current = null;
    }

    // Add new overlay if we have a frame with an imageUrl and overlay is enabled
    if (currentFrame?.imageUrl && showOverlay) {
      const imageLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.imageUrl,
          imageExtent: OVERLAY_EXTENT,
          projection: getProjection("EPSG:3857")!,
        }),
        opacity: opacity,
      });

      map.addLayer(imageLayer);
      overlayLayerRef.current = imageLayer;
    }
  }, [currentFrame, showOverlay]);

  // Update overlay opacity separately for smooth slider interaction
  useEffect(() => {
    if (overlayLayerRef.current) {
      overlayLayerRef.current.setOpacity(opacity);
    }
  }, [opacity]);

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

      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1">
        <div className="bg-card/85 border rounded px-3 py-1.5 text-xs font-mono text-muted-foreground">
          Base Layer: OpenStreetMap
        </div>
        {currentFrame && showOverlay && (
          <div className={`border rounded px-3 py-1.5 text-xs font-mono ${
            currentFrame.isOriginal
              ? "bg-green-500/20 border-green-500/40 text-green-300"
              : "bg-blue-500/20 border-blue-500/40 text-blue-300"
          }`}>
            Overlay: {currentFrame.timestamp} ({currentFrame.isOriginal ? "Original" : "Generated"})
          </div>
        )}
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
