# Uploading Photos

## Paper as a size reference

Tracefinity uses a sheet of paper as a known-size reference to scale outlines to real-world dimensions. Place tools flat on A4, Letter, A3, or Tabloid paper.

The paper is for scale only. Tools can overflow the paper edges. The full visible area beyond the paper is included in the corrected image.

## Desktop upload

From the home page, drag and drop your photo onto the uploader or click to browse. JPG, PNG, WebP, and HEIC are accepted.

After upload, the app detects paper corners automatically. Drag the four corner handles onto the paper edges, select the paper size, and tracing begins.

## Mobile capture

You can use your phone's camera to capture a tool photo that feeds directly into a desktop trace session:

1. On desktop, click **"Start Mobile Capture Session"** next to the upload area. A QR code appears.
2. Scan the QR code with your phone. It opens the mobile capture page at `/capture`.
3. On your phone, tap **"Take Photo"** — this opens the rear camera. Take a top-down photo of your tool on paper.
4. The photo uploads directly into the session. The desktop page detects the upload and shows a **"Proceed to Trace"** button.

The QR code URL supports three modes (selectable on the setup page):
- **mDNS** — `http://<hostname>.local:<port>/capture` (Bonjour, works on macOS/Linux LAN)
- **LAN IP** — `http://<ip>:<port>/capture`
- **Custom** — enter your own base URL

In Docker, use the `docker-up.sh` script which automatically detects and passes
the host's LAN IP and hostname to the container so the QR code generates correct,
phone-reachable URLs.

## Tips for good results

- **Contrasting background** -- use a dark surface under white paper (or vice versa). The AI needs to distinguish paper edges from the background.
- **Even lighting** -- avoid harsh shadows across the tools. Diffused overhead light works best.
- **Flat tools** -- tools should lie flat on the paper. Raised handles or 3D shapes confuse the mask generation.
- **No overlap** -- leave a small gap between tools so the AI can separate them.
- **Shoot from above** -- aim for directly overhead. Perspective correction handles some angle, but straight-down gives the most accurate scale.

## Supported formats

JPG, PNG, WebP, and HEIC. There is no hard file size limit, but large photos take longer to upload and process.

Images are automatically downscaled to a maximum of 2048px on the longest edge. Original uploads are deleted after perspective correction; only the corrected image is retained.

## Paper size

After uploading, select A4, Letter, A3, or Tabloid. Pick whichever you actually used. This determines the scale of everything downstream: tool outlines, bin dimensions, and exported STL geometry.

## Webhooks (API only)

If you're using the API directly, you can provide a `webhook_url` and optional `webhook_metadata` as form fields with the upload. Tracefinity will POST the generation result to that URL when a bin is successfully generated. See [the API docs](../api.md#webhooks) for the payload format and behaviour.
