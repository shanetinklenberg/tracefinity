'use client'

import { useState, useRef, useEffect, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { Camera, Upload, Loader2, CheckCircle, AlertTriangle } from 'lucide-react'
import { uploadImage, getSession as getSessionApi } from '@/lib/api'

type CaptureState =
  | { status: 'idle' }
  | { status: 'preview'; file: File; previewUrl: string }
  | { status: 'uploading'; file: File; previewUrl: string }
  | { status: 'waiting_for_trace'; sessionId: string }
  | { status: 'complete'; sessionId: string }
  | { status: 'error'; message: string; file?: File; previewUrl?: string }

function CapturePageInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [sessionId, setSessionId] = useState<string | undefined>(
    searchParams.get('session') || undefined
  )
  const inputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [state, setState] = useState<CaptureState>({ status: 'idle' })

  // Keep URL in sync with sessionId so page refresh restores context
  useEffect(() => {
    if (sessionId) {
      const params = new URLSearchParams(searchParams)
      params.set('session', sessionId)
      router.replace(`/capture?${params.toString()}`, { scroll: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // On mount with an existing session, recover state (handles page refresh)
  useEffect(() => {
    if (!sessionId) return
    getSessionApi(sessionId)
      .then(session => {
        // Desktop chained to a new session — follow it
        if (session.next_session_id) {
          setSessionId(session.next_session_id)
          setState({ status: 'idle' })
          return
        }
        if (session.tools_saved_at) {
          setState({ status: 'complete', sessionId: sessionId! })
        } else if (session.original_image_path) {
          setState({ status: 'waiting_for_trace', sessionId: sessionId! })
        }
        // else: fresh session, stay idle
      })
      .catch(() => { /* session not found, stay idle */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      const url = getPreviewUrl(state)
      if (url) URL.revokeObjectURL(url)
      if (pollRef.current) clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Derived: the session id we're currently waiting on (null when not waiting)
  const waitingSessionId =
    state.status === 'waiting_for_trace' ? state.sessionId : null

  // Poll for completion when waiting_for_trace.
  // If the desktop creates a follow-up session we redirect; otherwise we
  // show "complete" once tools are saved.
  useEffect(() => {
    if (!waitingSessionId) return

    pollRef.current = setInterval(() => {
      getSessionApi(waitingSessionId)
        .then(session => {
          // Desktop started a new session — follow it
          if (session.next_session_id) {
            if (pollRef.current) clearInterval(pollRef.current)
            setSessionId(session.next_session_id)
            setState({ status: 'idle' })
            return
          }
          // Desktop finished and did NOT start another — show complete
          if (session.tools_saved_at) {
            if (pollRef.current) clearInterval(pollRef.current)
            setState({ status: 'complete', sessionId: waitingSessionId })
          }
        })
        .catch(() => { /* ignore poll errors */ })
    }, 2000)

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [waitingSessionId])

  function getPreviewUrl(s: CaptureState): string | undefined {
    if ('previewUrl' in s) return (s as { previewUrl?: string }).previewUrl
    return undefined
  }

  function handleReset() {
    const url = getPreviewUrl(state)
    if (url) URL.revokeObjectURL(url)
    if (inputRef.current) inputRef.current.value = ''
    setState({ status: 'idle' })
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      setState({ status: 'error', message: 'Please select an image file.' })
      return
    }

    const previewUrl = URL.createObjectURL(file)
    setState({ status: 'preview', file, previewUrl })
  }

  async function handleUpload(file: File, previewUrl: string) {
    setState({ status: 'uploading', file, previewUrl })

    try {
      const result = await uploadImage(file, sessionId)
      URL.revokeObjectURL(previewUrl)
      if (result.session_id !== sessionId) {
        setSessionId(result.session_id)
      }
      setState({ status: 'waiting_for_trace', sessionId: result.session_id })
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Upload failed. Please try again.'
      setState({ status: 'error', message, file, previewUrl })
    }
  }

  function handleRetry() {
    if (state.status === 'error' && state.file && state.previewUrl) {
      handleUpload(state.file, state.previewUrl)
    }
  }

  return (
    <div className="min-h-screen bg-base flex flex-col">
      {/* Minimal header */}
      <div className="px-4 py-3 flex items-center justify-between border-b border-border-subtle">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-bold text-text-primary hover:opacity-80 transition-opacity"
        >
          <img src="/favicon.svg" alt="" className="w-5 h-5 rounded-[3px]" />
          Tracefinity
        </Link>
        <span className="text-[11px] text-text-muted">Tool Capture</span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {state.status === 'idle' && (
            <div className="glass-card p-8 flex flex-col items-center gap-6">
              <div className="w-16 h-16 rounded-full bg-accent-muted flex items-center justify-center">
                <Camera className="w-7 h-7 text-accent" />
              </div>
              <div className="text-center space-y-2">
                <h1 className="text-lg font-bold text-text-primary">
                  Capture Tool Photo
                </h1>
                <p className="text-sm text-text-secondary">
                  Take a top-down photo of your tool on a sheet of paper.
                  Make sure all four paper corners are visible.
                </p>
              </div>
              <button
                onClick={() => inputRef.current?.click()}
                className="btn-primary px-8 py-4 text-base font-semibold w-full touch-target"
              >
                <Camera className="w-5 h-5 inline-block mr-2" />
                Take Photo
              </button>
              <p className="text-[11px] text-text-muted text-center">
                Uses your device camera. Photos are uploaded securely.
              </p>
              <input
                ref={inputRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
          )}

          {state.status === 'preview' && (
            <div className="glass-card p-6 flex flex-col gap-4">
              <div className="relative aspect-[4/3] bg-inset rounded-[8px] overflow-hidden">
                <img
                  src={state.previewUrl}
                  alt="Preview of tool photo"
                  className="absolute inset-0 w-full h-full object-contain"
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleReset}
                  className="btn-secondary px-4 py-3 text-sm flex-1 touch-target"
                >
                  Retake
                </button>
                <button
                  onClick={() => handleUpload(state.file, state.previewUrl)}
                  className="btn-primary px-4 py-3 text-sm flex-1 touch-target"
                >
                  <Upload className="w-4 h-4 inline-block mr-2" />
                  Upload
                </button>
              </div>
            </div>
          )}

          {state.status === 'uploading' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4">
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <p className="text-sm text-text-secondary">
                Uploading tool photo...
              </p>
            </div>
          )}

          {state.status === 'waiting_for_trace' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4 text-center">
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <div>
                <h2 className="text-lg font-bold text-text-primary">
                  Waiting for tool scan...
                </h2>
                <p className="text-sm text-text-secondary mt-1">
                  Photo uploaded. The desktop is now tracing your tool.
                  This page will update when the trace is complete.
                </p>
              </div>
            </div>
          )}

          {state.status === 'complete' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4 text-center">
              <div className="w-16 h-16 rounded-full bg-green-900/20 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-text-primary">
                  Tool scan session complete
                </h2>
                <p className="text-sm text-text-secondary mt-1">
                  Your tool has been traced and saved to the library. You can
                  close this page or scan a new QR code for another tool.
                </p>
              </div>
            </div>
          )}

          {state.status === 'error' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-red-900/20 flex items-center justify-center">
                <AlertTriangle className="w-8 h-8 text-red-400" />
              </div>
              <div className="text-center">
                <h2 className="text-lg font-bold text-text-primary">
                  Upload Failed
                </h2>
                <p className="text-sm text-text-secondary mt-1">
                  {state.message}
                </p>
              </div>
              <div className="flex gap-3 w-full">
                {state.file && state.previewUrl ? (
                  <>
                    <button
                      onClick={handleRetry}
                      className="btn-primary px-4 py-3 text-sm flex-1 touch-target"
                    >
                      Retry
                    </button>
                    <button
                      onClick={handleReset}
                      className="btn-secondary px-4 py-3 text-sm flex-1 touch-target"
                    >
                      New Photo
                    </button>
                  </>
                ) : (
                  <button
                    onClick={handleReset}
                    className="btn-primary px-4 py-3 text-sm w-full touch-target"
                  >
                    Try Again
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CapturePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-base flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    }>
      <CapturePageInner />
    </Suspense>
  )
}
