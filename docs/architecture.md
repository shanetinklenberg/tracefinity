# Architecture

## Backend (Python/FastAPI)
- Image upload with model-assisted paper corner detection (U2-Net Portable + OpenCV)
- Perspective correction using user-adjusted corners (portrait + landscape)
- Tool tracing via local models (BiRefNet Lite, IS-Net, InSPyReNet) or Gemini API
- Manual mask upload as alternative
- Session persistence (JSON files)
- Tool library, bin, and bin project persistence (JSON files)
- STL/3MF generation with manifold3d

## Frontend (Next.js 16/React/TypeScript)
- Dashboard with project, tool library, and bin management
- Paper corner editor with draggable handles
- Polygon editor with vertex editing, undo/redo
- Tool editor for editing saved tools (vertices, finger holes)
- Bin editor for positioning tools in bins, adding text labels
- Project screen for planning a group of tools/bins and tracking placed vs unplaced tools
- 3D STL preview (react-three-fiber)
- Shows user what prompts are sent to Gemini
- Mobile capture: QR code session setup on desktop, camera capture page on phone
- PWA manifest for "Add to Home Screen" mobile experience

## Project Structure

```
tracefinity/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── constants.py             # GF_GRID etc.
│   │   ├── api/routes.py
│   │   └── services/
│   │       ├── ai_tracer.py              # Gemini mask + contour tracing
│   │       ├── image_processor.py         # paper detection + perspective
│   │       ├── polygon_scaler.py          # px-to-mm, clearance, smoothing
│   │       ├── stl_generator_manifold.py  # gridfinity STL + bin splitting
│   │       ├── bin_service.py             # placed-tool sync logic
│   │       ├── image_service.py           # tool thumbnail generation
│   │       ├── session_store.py
│   │       ├── tool_store.py              # tool library persistence
│   │       ├── bin_store.py               # bin persistence
│   │       ├── project_store.py           # bin project persistence
│   │       └── project_service.py         # project summaries, health, repair
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx               # dashboard (projects + tools + bins)
│   │   │   ├── trace/[id]/            # corner + polygon editing
│   │   │   ├── tools/[id]/            # tool vertex/hole editor
│   │   │   ├── projects/[id]/         # project planning workflow
│   │   │   ├── bins/[id]/             # bin builder + 3D preview
│   │   │   ├── capture/
│   │   │   │   ├── page.tsx           # mobile camera capture (reads ?session=)
│   │   │   │   └── setup/
│   │   │   │       └── page.tsx       # desktop QR code session setup
│   │   ├── components/
│   │   │   ├── BinEditor.tsx          # bin layout orchestrator
│   │   │   ├── BinEditorToolbar.tsx   # bin toolbar (mode, snap, actions)
│   │   │   ├── BinEditorCanvas.tsx    # bin SVG canvas
│   │   │   ├── BinConfigurator.tsx    # bin settings panel
│   │   │   ├── BinPreview3D.tsx       # three.js STL viewer
│   │   │   ├── ToolEditor.tsx         # tool editor orchestrator
│   │   │   ├── ToolEditorToolbar.tsx  # tool toolbar (mode, smooth, undo)
│   │   │   ├── ToolEditorCanvas.tsx   # tool SVG canvas
│   │   │   ├── ToolBrowser.tsx        # sidebar tool picker for bins
│   │   │   ├── PolygonEditor.tsx      # trace-time polygon editor
│   │   │   ├── CutoutOverlay.tsx      # finger hole SVG rendering
│   │   │   ├── QrCode.tsx             # reusable QR code (SSR-safe, qrcode.react)
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   ├── useDebouncedSave.ts    # debounced auto-save
│   │   │   └── useHistory.ts          # undo/redo state management
│   │   └── lib/
│   │       ├── api.ts                 # API client
│   │       ├── constants.ts           # shared constants
│   │       └── svg.ts                 # polygon path, smoothing, snap
│   └── package.json
├── .github/workflows/
│   ├── docker-dev.yml      # build on push to main
│   └── docker-release.yml  # build on release
├── Dockerfile              # single container (frontend + backend)
├── .env.example
└── README.md
```

## Data Model

- **Tool**: a single traced polygon + finger holes, stored in mm, centred at origin. Lives in a persistent library (`tools.json`).
- **PlacedTool**: a positioned copy of a tool in a bin. Points/holes in bin-space mm. Has `tool_id` linking back to source.
- **Bin**: bin config + placed tools + text labels. Used for STL generation (`bins.json`).
- **BinProject**: a planning group of tool ids and linked bin ids. Placement status is derived from linked bins (`projects.json`). Projects can carry default bin settings used when creating project bins.
- **Session**: ephemeral, used only for upload/trace workflow. Output is tools saved to library via `save-tools`.

PlacedTools sync with their library source on bin load (`GET /bins/{id}`) via `bin_service.sync_placed_tools()`. Edits to a tool's points, finger holes, or name propagate to all bins that use it. The position offset is preserved.

Projects do not own tools or bins. Tools keep `project_ids`, bins keep `project_id`, and project health/repair endpoints keep those links consistent when records are renamed, deleted, or manually edited.

### Upload and mobile capture flow

Two paths to create a trace session:

1. **Direct upload** — user drops a file on the home page. `POST /api/upload` creates a session with the image attached immediately.

2. **Mobile capture** — a two-step flow for capturing photos from a phone:
   - Desktop clicks "Start Mobile Capture Session" → calls `POST /api/sessions` to create a pending session (no image). A QR code is displayed containing the URL `<host>.local:<port>/capture?session=<id>`.
   - Phone scans QR → opens the mobile-optimized `/capture` page. Camera `capture="environment"` opens the rear camera. Photo is uploaded via `POST /api/upload` with the `session_id` form field, which fills in the pre-created session.
   - Desktop polls `GET /api/sessions/{id}` every 2 seconds until `original_image_path` becomes non-null, then enables the "Proceed to Trace" button.

The capture page supports three URL modes (persisted to localStorage):
- **mDNS** — `http://<hostname>.local:<port>/capture?session=<id>` (Bonjour, works on macOS/Linux LAN)
- **LAN IP** — `http://<ip>:<port>/capture?session=<id>` (works everywhere but IP can change)
- **Custom** — user-provided base URL

### Server info endpoint

`GET /api/server-info` resolves the server's hostname and LAN IP for QR code URL construction. Resolution order:
1. `TRACEFINITY_HOST` / `TRACEFINITY_HOSTNAME` env vars (set by `docker-up.sh` for Docker)
2. Request `Host` header (when already accessing via LAN)
3. OS hostname + LAN IP detection (bare-metal / local dev)

Hostnames are returned without the `.local` suffix; the frontend appends it.

### PWA

The `/capture` page is a Progressive Web App with `manifest.json`, service worker icons, and `apple-mobile-web-app-capable` meta tags. This lets users "Add to Home Screen" on iOS/Android for a native-like camera capture experience.

## Backend route helpers

- `_run_generate()` -- cache check, STL generation, split, zip, response. Used by both session and bin generation endpoints.
- `_translate_points()` / `_translate_finger_holes()` -- offset points/holes by (dx, dy). Used when placing tools in bins.
- `BinParams` base model in `schemas.py` -- shared fields and validators inherited by `BinConfig` and `GenerateRequest`.
