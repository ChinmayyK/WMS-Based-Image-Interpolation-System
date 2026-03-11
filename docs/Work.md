# Work Distribution and Module Assignment

The project is divided into modular components so that development can proceed in parallel while ensuring integration across the system. Each team member is responsible for specific modules based on system requirements and available hardware resources.

The system retrieves satellite images from a **Web Map Service (WMS)**, processes them for spatial consistency, generates intermediate frames using **RIFE**, and visualizes the results on a WebGIS interface built using **OpenLayers**.

---

# Team Members

* Chinmay
* Hrishikesh
* Tejas

---

# Module Allocation

## 1. WMS Data Acquisition Module

**Assigned to: Hrishikesh**

### Objective

Retrieve satellite images from a WMS server using time-based requests.

### Responsibilities

* Configure WMS request parameters (BBOX, CRS, resolution, time).
* Develop a script to download satellite images at fixed intervals.
* Store images with timestamp metadata.
* Maintain a structured dataset of retrieved frames.

### Expected Output

A local dataset containing time-sequenced satellite images.

Example dataset:

```
raw_frames/
frame_10_00.png
frame_10_30.png
frame_11_00.png
```

---

# 2. Geospatial Preprocessing Module

**Assigned to: Hrishikesh**

### Objective

Ensure spatial consistency of satellite images before AI processing.

### Responsibilities

* Normalize image resolution.
* Align geographic projections.
* Remove invalid pixels or missing data.
* Prepare images for AI interpolation.

### Tools Used

* **GDAL**
* **Rasterio**
* **OpenCV**

### Output

Preprocessed images stored in a structured dataset.

---

# 3. AI Frame Interpolation Module

**Assigned to: Tejas**

### Objective

Generate intermediate frames between satellite images using AI.

### Responsibilities

* Install and configure PyTorch with GPU acceleration.
* Implement the RIFE interpolation model.
* Generate intermediate frames between two satellite images.
* Optimize GPU inference for faster processing.

### Example

Input frames

```
10:00
10:30
```

Generated frames

```
10:05
10:10
10:15
10:20
10:25
```

### Output

Interpolated frame dataset.

```
interpolated_frames/
frame_10_05.png
frame_10_10.png
frame_10_15.png
```

---

# 4. Metadata and Confidence Module

**Assigned to: Tejas**

### Objective

Store interpolation metadata and confidence scores.

### Responsibilities

* Record timestamps for generated frames.
* Track source frames used for interpolation.
* Compute confidence values indicating reliability of generated frames.
* Store metadata in structured format.

Example metadata:

```
{
"time": "10:10",
"generated": true,
"confidence": 0.87,
"source_frames": ["10:00","10:30"]
}
```

---

# 5. Backend API and Frame Management Module

**Assigned to: Chinmay**

### Objective

Provide backend services for retrieving frames and metadata.

### Responsibilities

* Develop REST APIs using FastAPI.
* Serve satellite frames and interpolated frames.
* Provide endpoints for retrieving animation sequences.
* Manage metadata retrieval.

Example API endpoints:

```
GET /frames
GET /frame?timestamp=10:10
GET /animation
```

---

# 6. WebGIS Visualization Module

**Assigned to: Chinmay**

### Objective

Display satellite imagery as an animated sequence on a map interface.

### Responsibilities

* Build a WebGIS interface using OpenLayers.
* Implement frame animation controls.
* Overlay satellite images on the map.
* Integrate backend API with frontend interface.

### Features

* Play/pause animation
* Timeline navigation
* Frame overlay visualization
* Confidence display

---

# Collaborative Responsibilities

All team members will collaborate on:

* System architecture design
* Integration testing
* Documentation and report writing
* Final system deployment
* Project presentation preparation

---

# Mid-Term Checkpoint

At the mid-term review, the system should demonstrate the basic functionality of each module.

### 1. Data Acquisition Completed

Satellite frames can be retrieved from the WMS server and stored locally.

Example frames:

```
10:00
10:30
11:00
```

---

### 2. Image Preprocessing Pipeline Working

Retrieved images are successfully:

* resized
* normalized
* spatially aligned

Dataset is ready for AI processing.

---

### 3. AI Interpolation Prototype Running

The interpolation module generates at least one intermediate frame between two images.

Example:

```
10:00 → 10:15 → 10:30
```

---

### 4. WebGIS Viewer Prototype

A basic WebGIS interface can display satellite frames on a map.

Features required for mid-term demo:

* map loads successfully
* frames appear as overlays
* frames can be switched sequentially

---

# Mid-Term Demonstration Workflow

The system demonstration should follow this sequence:

1. Fetch satellite images from WMS server.
2. Preprocess and align the images.
3. Run AI interpolation to generate intermediate frames.
4. Display the frames on the WebGIS map.

This demonstration will confirm that all system modules are functioning and integrated at a basic level.

---

# Module Overview

| Module                             | Description                                                                                                                     | Assigned To | Technologies Used      | Expected Deliverable                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------- | ---------------------- | ----------------------------------------------------------------------------- |
| **WMS Data Acquisition**           | Retrieve satellite images from a Web Map Service (WMS) using time-based queries and geographic parameters such as BBOX and CRS. | Hrishikesh  | Python, requests       | Automated script to download satellite frames and store them with timestamps. |
| **Geospatial Preprocessing**       | Align and normalize satellite images to ensure consistent resolution, projection, and pixel format before AI processing.        | Hrishikesh  | GDAL, Rasterio, OpenCV | Preprocessed dataset of aligned satellite images ready for interpolation.     |
| **AI Frame Interpolation**         | Generate intermediate frames between two satellite images to reconstruct continuous temporal sequences.                         | Tejas       | PyTorch, RIFE Model    | Interpolated frames representing intermediate timestamps.                     |
| **Metadata & Confidence Module**   | Store interpolation metadata including timestamps, source frames, and confidence scores for generated frames.                   | Tejas       | Python, JSON           | Metadata files describing each generated frame.                               |
| **Backend API & Frame Management** | Develop backend services to serve satellite frames and metadata to the frontend application.                                    | Chinmay     | Python, FastAPI        | REST API providing endpoints for frames and animation sequences.              |
| **WebGIS Visualization**           | Display satellite imagery as a time-based animation overlay on a web map interface.                                             | Chinmay     | React, OpenLayers      | Interactive WebGIS interface with animation controls.                         |

---

# Technology Stack summary

| Layer                 | Technology            |
| --------------------- | --------------------- |
| Programming Language  | Python                |
| Geospatial Processing | GDAL, Rasterio        |
| Image Processing      | OpenCV                |
| AI Framework          | PyTorch               |
| Frame Interpolation   | RIFE Model            |
| Backend API           | FastAPI               |
| Frontend Framework    | React                 |
| WebGIS Visualization  | OpenLayers            |
| Data Source           | Web Map Service (WMS) |

---

# Mid-Term Targets

| Module                   | Responsible Member | Mid-Term Target                                                             |
| ------------------------ | ------------------ | --------------------------------------------------------------------------- |
| WMS Data Acquisition     | Hrishikesh         | Successfully fetch satellite images from WMS server and store them locally. |
| Geospatial Preprocessing | Hrishikesh         | Images resized, aligned, and normalized for AI processing.                  |
| AI Frame Interpolation   | Tejas              | Generate at least one intermediate frame between two satellite images.      |
| Metadata Generation      | Tejas              | Metadata structure created and attached to generated frames.                |
| Backend API              | Chinmay            | API endpoints implemented to retrieve frames and metadata.                  |
| WebGIS Viewer            | Chinmay            | Basic map interface displaying satellite frames sequentially.               |

