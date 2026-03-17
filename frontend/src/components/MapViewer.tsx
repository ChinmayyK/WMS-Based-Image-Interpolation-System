import { useEffect, useRef, useCallback, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import Static from "ol/source/ImageStatic";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Style, Stroke } from "ol/style";
import { get as getProjection, transformExtent } from "ol/proj";
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
  showClouds: boolean;
  onToggleClouds: () => void;
  showVectors: boolean;
  onToggleVectors: () => void;
  currentFrame?: SatelliteFrame;
  comparisonMode?: "off" | "split" | "toggle";
}

// Fallback bounding box for the satellite overlay (EPSG:3857)
const FALLBACK_EXTENT = [7500000, 700000, 11000000, 4300000];
const DEFAULT_CENTER: [number, number] = [9250000, 2500000];
const DEFAULT_ZOOM = 4.5;

const vectorStyle = new Style({
  stroke: new Stroke({
    color: "rgba(255, 255, 0, 0.8)",
    width: 2,
  }),
});

const MapViewer = ({
  opacity,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
  showClouds,
  onToggleClouds,
  showVectors,
  onToggleVectors,
  currentFrame,
  comparisonMode = "off",
}: MapViewerProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);

  // Layer Refs for Dual-Layer Crossfade
  const layer1Ref = useRef<ImageLayer<Static> | null>(null);
  const layer2Ref = useRef<ImageLayer<Static> | null>(null);
  const activeLayerSlot = useRef<1 | 2>(1);
  
  const cloudLayerRef = useRef<ImageLayer<Static> | null>(null);
  const vectorLayerRef = useRef<VectorLayer<VectorSource> | null>(null);

  const [mapExtent, setMapExtent] = useState<number[] | null>(null);

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({
          source: new OSM(),
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

  // Frame update with Georeferencing and Cross-fading
  useEffect(() => {
    if (!mapInstanceRef.current || !currentFrame || !showOverlay) {
      // Cleanup layers if overlay is off
      if (!showOverlay && mapInstanceRef.current) {
        if (layer1Ref.current) mapInstanceRef.current.removeLayer(layer1Ref.current);
        if (layer2Ref.current) mapInstanceRef.current.removeLayer(layer2Ref.current);
        layer1Ref.current = null;
        layer2Ref.current = null;
      }
      return;
    }
    
    const map = mapInstanceRef.current;
    
    // 1. Calculate Georeferenced Extent
    let extent = FALLBACK_EXTENT;
    if (currentFrame.bbox) {
      extent = transformExtent(currentFrame.bbox, "EPSG:4326", "EPSG:3857");
    }

    // 2. Dual Layer Crossfade Logic
    const nextSlot = activeLayerSlot.current === 1 ? 2 : 1;
    const newLayer = new ImageLayer({
      source: new Static({
        url: currentFrame.imageUrl,
        imageExtent: extent,
        projection: getProjection("EPSG:3857")!,
      }),
      opacity: 0,
    });

    map.addLayer(newLayer);

    // Swap Layers
    const oldLayer = activeLayerSlot.current === 1 ? layer1Ref.current : layer2Ref.current;
    
    // Animate New Layer In
    setTimeout(() => {
      newLayer.setOpacity(opacity);
    }, 50);

    // Animate Old Layer Out
    if (oldLayer) {
      oldLayer.setOpacity(0);
      setTimeout(() => {
        map.removeLayer(oldLayer);
      }, 500);
    }

    // Update Refs
    if (nextSlot === 1) layer1Ref.current = newLayer;
    else layer2Ref.current = newLayer;
    activeLayerSlot.current = nextSlot;

    // 3. Auto-fit logic (once per new extent)
    if (extent && JSON.stringify(extent) !== JSON.stringify(mapExtent)) {
      map.getView().fit(extent, { padding: [50, 50, 50, 50], duration: 1000 });
      setMapExtent(extent);
    }

    // 4. Cloud Mask Handling (simplified for brevity, stays on top)
    if (cloudLayerRef.current) map.removeLayer(cloudLayerRef.current);
    if (showClouds && currentFrame.cloudMaskUrl) {
      const cLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.cloudMaskUrl,
          imageExtent: extent,
          projection: getProjection("EPSG:3857")!,
        }),
        opacity: 0.6,
      });
      map.addLayer(cLayer);
      cloudLayerRef.current = cLayer;
    }

    // 5. Vectors Handling
    if (vectorLayerRef.current) map.removeLayer(vectorLayerRef.current);
    if (showVectors && currentFrame.vectorsUrl) {
      const vLayer = new VectorLayer({
        source: new VectorSource({ url: currentFrame.vectorsUrl, format: new GeoJSON() }),
        style: vectorStyle,
      });
      map.addLayer(vLayer);
      vectorLayerRef.current = vLayer;
    }

  }, [currentFrame, showOverlay, showClouds, showVectors, opacity]);

  const handleResetView = useCallback(() => {
    if (!mapInstanceRef.current) return;
    mapInstanceRef.current.getView().animate({ center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM, duration: 500 });
  }, []);


  return (
    <div className="relative w-full h-full bg-map-bg rounded overflow-hidden border">
      <div ref={mapRef} className="w-full h-full" />

      {/* Map Overlay HUD */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="bg-background/90 backdrop-blur-md border border-primary/20 rounded-lg p-4 shadow-xl min-w-[200px]">
          <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground mb-1">Satellite Sequence</div>
          <div className="text-lg font-mono font-bold text-primary flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            {currentFrame?.timestamp}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${currentFrame?.isOriginal ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'}`}>
              {currentFrame?.isOriginal ? "SENSOR DATA" : "AI INTERPOLATED"}
            </span>
            {!currentFrame?.isOriginal && showConfidence && (
              <span className="text-[10px] bg-primary/20 text-primary-foreground px-1.5 py-0.5 rounded font-bold">
                CONF: {Math.round((currentFrame?.confidence || 0) * 100)}%
              </span>
            )}
          </div>
        </div>
      </div>

      <MapControlsPanel
        onResetView={handleResetView}
        showOverlay={showOverlay}
        onToggleOverlay={onToggleOverlay}
        showConfidence={showConfidence}
        onToggleConfidence={onToggleConfidence}
        showClouds={showClouds}
        onToggleClouds={onToggleClouds}
        showVectors={showVectors}
        onToggleVectors={onToggleVectors}
      />

      <LegendPanel />
    </div>
  );
};

export default MapViewer;
