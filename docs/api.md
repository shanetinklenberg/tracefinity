# API Endpoints

## Sessions (trace workflow)
- `POST /api/upload` - upload image, auto-detect corners. Accepts optional `session_id` to fill a pre-created session.
- `POST /api/sessions` - create a pending session (no image). Used by mobile capture flow. Returns `session_id`.
- `POST /api/sessions/{id}/corners` - set corners, apply perspective correction
- `POST /api/sessions/{id}/trace` - AI trace tool outlines
- `POST /api/sessions/{id}/trace-mask` - trace from uploaded mask
- `PUT /api/sessions/{id}/polygons` - save polygon edits
- `POST /api/sessions/{id}/save-tools` - convert traced polygons to library tools
- `GET /api/sessions` - list sessions
- `GET /api/sessions/{id}` - get session state
- `PATCH /api/sessions/{id}` - update session metadata
- `DELETE /api/sessions/{id}` - delete session

## Tools (library)
- `GET /api/tools` - list tools
- `GET /api/tools/{id}` - get tool
- `PUT /api/tools/{id}` - update tool (name, points, finger_holes)
- `POST /api/tools/{id}/auto-rotate` - compute optimal rotation angle (degrees) to minimise bounding box
- `DELETE /api/tools/{id}` - delete tool

## Bins
- `GET /api/bins` - list bins
- `GET /api/bins/{id}` - get bin (syncs placed tools with library versions)
- `POST /api/bins` - create bin (optionally with tool_ids for auto-sizing and bin_config defaults)
- `PUT /api/bins/{id}` - update bin
- `DELETE /api/bins/{id}` - delete bin + output files
- `POST /api/bins/{id}/generate` - generate STL/3MF from bin

## Bin projects
- `GET /api/bin-projects` - list project summaries with tool/bin/placement counts
- `POST /api/bin-projects` - create a project, optionally seeded with tool ids
- `GET /api/bin-projects/{id}` - get project detail with derived placed/unplaced tool ids
- `PATCH /api/bin-projects/{id}` - update project metadata and status
- `DELETE /api/bin-projects/{id}` - delete project metadata; tools and bins are retained
- `POST /api/bin-projects/{id}/tools` - add tools to a project
- `DELETE /api/bin-projects/{id}/tools/{tool_id}` - remove a tool from a project
- `POST /api/bin-projects/{id}/bins` - link existing bins to a project
- `DELETE /api/bin-projects/{id}/bins/{bin_id}` - detach a bin from a project
- `POST /api/bin-projects/{id}/create-bin` - create a new bin from selected project tools, using project or request bin defaults
- `GET /api/bin-projects/{id}/health` - report project/tool/bin link mismatches
- `POST /api/bin-projects/{id}/repair` - repair safe project/tool/bin link mismatches

## Server info
- `GET /api/server-info` - returns hostname and LAN IP for QR code URL construction

## API Keys and tracer status
- `GET /api-keys` - returns current provider and available tracers

Response fields:
- `google` (bool): true when the server can trace without a user-supplied key (cloud env key, local, or remote).
- `provider` (string|null): one of `gemini` | `local` | `remote`.
- `provider_label` (string|null): human label for the primary tracer, e.g. `Replicate`.
- `tracers` (array): `{id, label}` entries. Remote tracers include `{"id":"replicate","label":"Replicate"}` and `{"id":"fal","label":"fal.ai"}` when the respective tokens are configured.

## File serving
- `GET /api/files/{session_id}/bin.stl` - session STL
- `GET /api/files/{session_id}/bin.3mf` - session 3MF
- `GET /api/files/{session_id}/bin_parts.zip` - session split parts
- `GET /api/files/bins/{bin_id}/bin.stl` - bin STL
- `GET /api/files/bins/{bin_id}/bin.3mf` - bin 3MF
- `GET /api/files/bins/{bin_id}/bin_parts.zip` - bin split parts

## Mobile capture flow

The mobile capture feature uses a two-step API flow to let a phone camera feed
into a desktop trace session.

### Creating a pending session

```
POST /api/sessions
Content-Type: multipart/form-data

(no fields required)
```

Returns `{"session_id": "<uuid>"}`. The session has no image yet; it waits for
a mobile upload to fill it in.

### Filling the session with a mobile upload

```
POST /api/upload
Content-Type: multipart/form-data

image: <file>
session_id: <uuid from POST /api/sessions>
```

Validates that the session exists and has no image yet (404 if not found, 409
if already filled). Preserves the session's `created_at`.

### Polling for the upload

The desktop setup page polls `GET /api/sessions/{id}` until
`original_image_path` is non-null:

```
GET /api/sessions/{id}
```

When the field becomes non-null, the phone has completed its upload and the
desktop can proceed to the trace/corners page.

### Server info for QR code URLs

```
GET /api/server-info
```

Returns:
```json
{
  "hostname": "tracefinity",
  "lan_ip": "192.168.0.144"
}
```

Hostname is returned without the `.local` suffix. The frontend constructs the
capture URL as `http://<hostname>.local:<port>/capture?session=<id>`.

Resolution order:
1. `TRACEFINITY_HOST` / `TRACEFINITY_HOSTNAME` env vars (set by `docker-up.sh`)
2. Request `Host` header
3. OS hostname via `socket.gethostname()` and LAN IP detection

In Docker, the container cannot detect the host's LAN IP. Use the env vars or
the `docker-up.sh` script which auto-detects and passes them.
