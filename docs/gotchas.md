# Gotchas

Hard-won lessons. Read before making changes to coordinate mapping, 3D preview, or Docker.

## Y-axis inversion

SVG/layout/bin-space is Y-down (0 = top edge). build123d is Y-up. Always negate Y when mapping: `-(y + offset_y)`.

- Flipping Y reverses polygon winding -- remove any `reversed()` calls if adding a Y-flip
- Text labels use a flipped Plane (z_dir down) so they negate Y separately
- BinPreview3D.tsx: rotation `[-PI/2, 0, 0]` converts Z-up to Y-up. Do NOT add `scale [1, -1, 1]` -- that was a compensating hack for un-flipped Y
- All three must match: layout editor, 3D preview, downloaded STL in slicer

## Cutout pipeline order

Smoothing/simplification runs BEFORE clearance (`prepare_for_generation`), never after -- vertex reduction erodes the outline by up to its tolerance and must not eat the clearance. The printed pocket is the previewed shape grown by exactly the clearance. The smoothing epsilon is absolute mm (`smooth_epsilon`), duplicated in `lib/svg.ts smoothEpsilon` -- change both together or preview and print diverge.

## EXIF orientation

cv2 ignores EXIF orientation, browsers apply it. `ingest_image` bakes orientation into the pixels at upload -- without it, corner coordinates from the UI land in a different frame than the backend warps. All image ingest (upload, corrected downscale, mask upload) must go through it.

## Three.js memory leaks

Every `BufferGeometry` and `EdgesGeometry` must be `.dispose()`d on React unmount. STL regeneration creates new geometries each time -- if the old ones aren't disposed, the browser will OOM. Same applies to `Image` objects created in useEffect (use a `cancelled` flag in cleanup).

## Docker

Single container runs both frontend and backend via supervisor. Key details:

- CORS origins in `backend/.env` override the Python defaults -- if you change the frontend port, update `.env` too
- `NEXT_TELEMETRY_DISABLED=1` is set in the Dockerfile build stage
- `.dockerignore` excludes `docs/`, `node_modules/`, `venv/`, `storage/`, `.claude/`
- Container runs as non-root user `tracefinity` (UID 1000) by default. Supports `--user "$(id -u):$(id -g)"` for arbitrary UIDs. Runtime-writable dirs (`/app/storage`, `/app/.u2net`, `/app/.next`, `/tmp/nginx`, `/tmp/supervisor`, `/var/lib/nginx`) are world-writable. `U2NET_HOME` and `HOME` are set to `/app` paths so model downloads and nginx/supervisor state work without root.

### Supervisor environment variables

Supervisor's `environment=` setting **replaces** the process environment — it does
not merge with the Docker `ENV` values. Any env var the backend needs must be
explicitly listed. Currently required:

```
environment=STORAGE_PATH="/app/storage",HOME="/app",NUMBA_CACHE_DIR="/tmp/numba_cache"
```

Without `HOME` and `NUMBA_CACHE_DIR`, Numba JIT compilation fails with
`RuntimeError: cannot cache function: no locator available` because it can't
write cache files to the Python site-packages directory (`pymatting`) when
running as non-root.

The `pymatting` site-packages directory must also be world-writable at build
time (`chmod -R a+w` in the Dockerfile), since Numba writes JIT cache files
alongside the source files.

### nginx non-root

nginx needs writable directories for its pid file and client body temp files:
- `/tmp/nginx/` for the pid file
- `/var/lib/nginx/body/` for client body temp files

Both must be pre-created with `mkdir -p` and `chmod 777` at build time.

## mDNS and LAN IP detection

The QR code capture page needs a phone-reachable URL. Detection is layered:

1. **`docker-up.sh` auto-detection** — detects the host's LAN IP (via `ip`,
   `ifconfig`, or Python UDP fallback) and hostname, passes them as
   `TRACEFINITY_HOST` and `TRACEFINITY_HOSTNAME` env vars to the container.

2. **`GET /api/server-info` backend** — reads env vars first, then falls back to
   the request `Host` header, then OS-level detection. Strips `.local` suffix
   from hostnames (the frontend appends it).

3. **Frontend URL mode selector** — persisted to `localStorage`. Defaults to
   mDNS, with LAN IP and custom URL as alternatives.

### Docker caveats

- Docker containers cannot detect the host's LAN IP from inside. The host must
  pass it via `TRACEFINITY_HOST` env var (done automatically by `docker-up.sh`).
- Docker bridge IPs (`172.x.x.x`) are detected and replaced with the Docker
  host gateway IP (read from `/proc/net/route`) when available.
- macOS hostnames automatically get a `.local` suffix from Bonjour/mDNS.
  `docker-up.sh` strips this so the frontend can add it consistently.

## OCCT / build123d performance

Boolean operations (add, subtract) are single-threaded in OCCT. More cores don't help. Polygon cutouts are batched into a single sketch + single extrude to minimise the number of booleans. Apple Silicon is ~7x faster single-thread than EPYC 7402 for these operations.

## Frontend patterns

- Shared constants (`DISPLAY_SCALE`, `SNAP_GRID`, `GRID_UNIT`, etc.) live in `lib/constants.ts`
- `DISPLAY_SCALE = 8` converts mm to SVG units in the bin editor
- Config is spread into the API request body: `{ ...config, polygons }` in `generateStl`
- Text labels live on BinConfig (not Polygon) since they're free-placed
- PolygonEditor uses refs (`polygonsRef`, `onPolygonsChangeRef`) to avoid stale closures during drag -- do not add `polygons` or `onPolygonsChange` to the `handleMouseMove` dependency array
- Auto-save uses the `useDebouncedSave` hook (debounce + `beforeunload` flush). Pass `skipInitial: true` to avoid saving on first load.
- Undo/redo uses the `useHistory` hook (deep-clone, Cmd+Z handling). The `set()` method pushes to history; `undo()`/`redo()` call the `onChange` callback.
- ToolEditor and BinEditor are split into orchestrator + toolbar + canvas sub-components. `CutoutOverlay` renders finger holes in both.

## Paper corner detection

Uses a two-stage approach: U2-Net Portable generates a rough tool mask (~0.17s), tool pixels are blacked out, then OpenCV brightness thresholding finds the paper rectangle in the cleaned image. This prevents tools (especially dark ones on white paper) from fragmenting the paper region during detection.

The brightness detection tries multiple thresholds (200, 190, 180), picks the largest valid candidate, and validates against aspect ratio (0.55-0.85, covering A-series, Letter, and Tabloid) and fill ratio (>35% of the bounding rectangle is bright). A convex hull merge step handles cases where the paper is split into fragments.

Difficult cases: hands in the frame, sticks/rods crossing the paper, very heavy tool overflow with minimal visible paper. These may need manual corner adjustment.

## Gemini mask quirks

- Masks come back at different dimensions AND aspect ratio than requested. `_trace_mask()` resizes with `INTER_NEAREST`, then `_align_mask()` uses template matching to correct the positional offset.
- `_align_mask()` extracts the tool region from the resized mask, searches for it in the inverted corrected image via `cv2.matchTemplate(TM_CCOEFF_NORMED)`, and applies a translation. Runs at 0.25x resolution (~20ms). Skipped if score < 0.15 or shift > 10% of image dimension.
- `_trace_mask()` handles both alpha-channel PNGs (tool=opaque, bg=transparent) and RGB PNGs (tool=black, bg=white).
- The prompt asks for a "stencil" -- flat black shapes on flat white. This works better than asking for a "mask" with `gemini-2.5-flash-image`.
