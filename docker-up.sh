#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------------------------
# Tracefinity — build and run the latest source in Docker.
#
# Usage:
#   ./docker-up.sh                          # build + run on port 3000
#   ./docker-up.sh --build-only             # build the image, don't run
#   ./docker-up.sh --no-build               # run the last built image
#   ./docker-up.sh -p 8080                  # run on port 8080
#   ./docker-up.sh -k YOUR_GOOGLE_API_KEY   # pass a Gemini API key
#
# Options:
#   -p, --port PORT         Host port to bind (default: 3000)
#   -d, --data DIR          Host directory for storage (default: ./data)
#   -k, --api-key KEY       Google API key for Gemini tracing
#   --name NAME             Container name (default: tracefinity)
#   --no-build              Skip build, run existing image
#   --build-only            Build only, don't run
#   --rm                    Remove container on stop (default: true)
#   -h, --help              Show this message
# --------------------------------------------------------------------------

IMAGE="tracefinity:latest"
PORT="3000"
DATA_DIR="$(pwd)/data"
API_KEY="${GOOGLE_API_KEY:-}"
CONTAINER_NAME="tracefinity"
DO_BUILD=true
DO_RUN=true
AUTO_RM=true

usage() {
  sed -n '/^#/{/^#!/d;/^# --/d;p;}' "$0" | sed 's/^# \?//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)       PORT="$2"; shift 2 ;;
    -d|--data)       DATA_DIR="$2"; shift 2 ;;
    -k|--api-key)    API_KEY="$2"; shift 2 ;;
    --name)          CONTAINER_NAME="$2"; shift 2 ;;
    --no-build)      DO_BUILD=false; shift ;;
    --build-only)    DO_RUN=false; shift ;;
    --rm)            AUTO_RM=true; shift ;;
    -h|--help)       usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
if $DO_BUILD; then
  echo "==> Building Docker image: $IMAGE"
  docker build -t "$IMAGE" .
  echo "==> Build complete"
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if $DO_RUN; then
  # Stop + remove any existing container with this name
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "==> Removing existing container: $CONTAINER_NAME"
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  fi

  # Check if port is already in use (by another tracefinity container)
  if lsof -ti ":$PORT" 2>/dev/null | grep -q .; then
    echo "==> Warning: port $PORT is in use — stopping existing listener"
    if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
      docker stop "$CONTAINER_NAME" 2>/dev/null || true
      sleep 0.5
    fi
    # If still in use after stopping our container, warn — don't force kill
    if lsof -ti ":$PORT" 2>/dev/null | grep -q .; then
      echo "==> ERROR: port $PORT is still in use by another process."
      echo "    Run: lsof -i :$PORT"
      echo "    Then stop that process or choose a different port with -p"
      exit 1
    fi
  fi

  # Ensure data directory exists with correct permissions
  mkdir -p "$DATA_DIR"/{uploads,processed,outputs}

  # Detect host LAN IP for QR code capture page
  HOST_IP=""
  if command -v ip &>/dev/null; then
    HOST_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '^172\.' | head -1)
  fi
  if [[ -z "$HOST_IP" ]] && command -v ifconfig &>/dev/null; then
    HOST_IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127\.' | grep -v '^172\.' | head -1)
  fi
  # macOS fallback
  if [[ -z "$HOST_IP" ]]; then
    HOST_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(0.05)
try:
    s.connect(('10.255.255.255', 1))
    print(s.getsockname()[0])
except:
    pass
finally:
    s.close()
" 2>/dev/null)
  fi

  # Detect hostname for mDNS (Bonjour)
  HOST_HOSTNAME="tracefinity"
  # Optionally use the machine's real hostname if available
  if command -v hostname &>/dev/null; then
    REAL_HOSTNAME=$(hostname 2>/dev/null | sed 's/\.local$//')
    [[ -n "$REAL_HOSTNAME" ]] && HOST_HOSTNAME="$REAL_HOSTNAME"
  fi

  RUN_FLAGS=(
    -d
    -p "$PORT:3000"
    -v "$DATA_DIR:/app/storage"
    --name "$CONTAINER_NAME"
  )

  $AUTO_RM && RUN_FLAGS+=(--rm)

  # Pass API key if set
  [[ -n "$API_KEY" ]] && RUN_FLAGS+=(-e "GOOGLE_API_KEY=$API_KEY")

  # Pass host network info for QR code capture page
  if [[ -n "$HOST_IP" ]]; then
    RUN_FLAGS+=(-e "TRACEFINITY_HOST=$HOST_IP")
    echo "==> Detected host IP: $HOST_IP"
  fi
  RUN_FLAGS+=(-e "TRACEFINITY_HOSTNAME=$HOST_HOSTNAME")
  echo "==> mDNS name: $HOST_HOSTNAME.local"

  # Run as host user so storage files are owned correctly
  RUN_FLAGS+=(--user "$(id -u):$(id -g)")

  echo "==> Starting container: $CONTAINER_NAME on port $PORT"
  docker run "${RUN_FLAGS[@]}" "$IMAGE"

  echo ""
  echo "Tracefinity is running at http://localhost:$PORT"
  if [[ -n "$HOST_IP" ]]; then
    echo "             or at http://${HOST_IP}:${PORT}"
  fi
  echo "   Capture: http://${HOST_HOSTNAME}.local:${PORT}/capture"
  echo ""
  echo "  Logs:   docker logs -f $CONTAINER_NAME"
  echo "  Stop:   docker stop $CONTAINER_NAME"
  echo "  Shell:  docker exec -it $CONTAINER_NAME sh"
fi
