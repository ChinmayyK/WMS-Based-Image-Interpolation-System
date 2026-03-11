# WMS-Based Image Interpolation System - Frontend

This is the frontend client for the **WMS-Based Image Interpolation System**. It provides a WebGIS dashboard built with **React**, **Vite**, and **OpenLayers** to visualize satellite imagery and AI-interpolated sequences.

## Features

- **Map Viewer:** Renders an OpenStreetMap base layer with dynamically generated satellite image overlays (`OpenLayers`).
- **Interactive Timeline:** A specialized timeline slider to scrub through real and AI-generated frames.
- **Animation Controls:** Play, pause, and speed adjustments for observing image interpolation over time.
- **Comparison View:** Toggle or split views to compare original satellite imagery with AI-interpolated output.
- **Metadata Panel:** Real-time information, confidence scores, and origin details for the currently active frame.

## Technologies Used

- **React 18** (Vite + TypeScript)
- **OpenLayers** (`ol`) for mapping
- **Tailwind CSS** + **Shadcn UI** for styling and components
- **TanStack Query** for API state management

## Getting Started

1. Ensure the Python FastAPI backend is running on port 8000.
2. Install dependencies:
   ```sh
   npm install
   ```
3. Start the development server:
   ```sh
   npm run dev
   ```
   The site will open at `http://localhost:8080`.

## Architecture Note

The frontend uses Vite's proxy feature to automatically route requests falling under `/api` and `/data` to the FastAPI backend running on `localhost:8000`. This circumvents CORS issues during local development.
