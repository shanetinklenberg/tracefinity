'use client'

import { useState, useEffect, useMemo, useRef, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { QrCode } from '@/components/QrCode'
import { createCaptureSession, getServerInfo, getSession as getSessionApi } from '@/lib/api'
import type { ServerInfo } from '@/lib/api'
import { Loader2, CheckCircle, Wifi, Globe, Pencil, Smartphone } from 'lucide-react'

const URL_MODE_KEY = 'tracefinity.captureUrlMode'
const CUSTOM_URL_KEY = 'tracefinity.captureCustomUrl'

type UrlMode = 'mdns' | 'lan' | 'custom'
type PageState = 'creating' | 'waiting' | 'ready' | 'error'

function loadUrlMode(): UrlMode {
  if (typeof window === 'undefined') return 'mdns'
  try {
    const raw = window.localStorage.getItem(URL_MODE_KEY)
    if (raw === 'mdns' || raw === 'lan' || raw === 'custom') return raw
  } catch { /* ignore */ }
  return 'mdns'
}

function saveUrlMode(mode: UrlMode) {
  try { window.localStorage.setItem(URL_MODE_KEY, mode) } catch { /* ignore */ }
}

function loadCustomUrl(): string {
  if (typeof window === 'undefined') return ''
  try { return window.localStorage.getItem(CUSTOM_URL_KEY) || '' } catch { return '' }
}

function saveCustomUrl(url: string) {
  try { window.localStorage.setItem(CUSTOM_URL_KEY, url) } catch { /* ignore */ }
}

export default function CaptureSetupPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-base flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    }>
      <CaptureSetupPageInner />
    </Suspense>
  )
}

function CaptureSetupPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const preExistingSessionId = searchParams.get('session') || undefined
  const [pageState, setPageState] = useState<PageState>('creating')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)
  const [urlMode, setUrlMode] = useState<UrlMode>('mdns')
  const [customUrl, setCustomUrl] = useState('')
  const [currentOrigin, setCurrentOrigin] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Create session + fetch server info on mount
  useEffect(() => {
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    setCurrentOrigin(origin)

    const savedMode = loadUrlMode()
    setUrlMode(savedMode)
    if (savedMode === 'custom') setCustomUrl(loadCustomUrl())

    // Fetch server info for URL construction
    getServerInfo()
      .then(setServerInfo)
      .catch(() => {})

    // If a pre-existing session was passed (from "Scan Another Tool"), use it directly
    if (preExistingSessionId) {
      setSessionId(preExistingSessionId)
      setPageState('waiting')
      pollRef.current = setInterval(() => {
        getSessionApi(preExistingSessionId).then(session => {
          if (session.original_image_path) {
            setPageState('ready')
            if (pollRef.current) clearInterval(pollRef.current)
          }
        }).catch(() => { /* ignore poll errors */ })
      }, 2000)
      return () => {
        if (pollRef.current) clearInterval(pollRef.current)
      }
    }

    // Create the pending session
    createCaptureSession()
      .then(({ session_id }) => {
        setSessionId(session_id)
        setPageState('waiting')
        // Start polling
        pollRef.current = setInterval(() => {
          getSessionApi(session_id).then(session => {
            if (session.original_image_path) {
              setPageState('ready')
              if (pollRef.current) clearInterval(pollRef.current)
            }
          }).catch(() => { /* ignore poll errors */ })
        }, 2000)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to create session')
        setPageState('error')
      })

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const handleModeChange = useCallback((mode: UrlMode) => {
    setUrlMode(mode)
    saveUrlMode(mode)
  }, [])

  const handleCustomUrlChange = useCallback((url: string) => {
    setCustomUrl(url)
    saveCustomUrl(url)
  }, [])

  // Build the capture URL
  const captureFullUrl = useMemo(() => {
    const sessionPath = sessionId ? `?session=${sessionId}` : ''

    if (urlMode === 'custom') {
      const base = customUrl || currentOrigin
      return base ? `${base}/capture${sessionPath}` : ''
    }

    const port = (() => {
      try { return new URL(currentOrigin || 'http://localhost').port } catch { return '' }
    })()

    const portSuffix = port ? `:${port}` : ''

    if (urlMode === 'mdns' && serverInfo?.hostname) {
      return `http://${serverInfo.hostname}.local${portSuffix}/capture${sessionPath}`
    }

    if (urlMode === 'lan' && serverInfo?.lan_ip) {
      return `http://${serverInfo.lan_ip}${portSuffix}/capture${sessionPath}`
    }

    return ''
  }, [urlMode, customUrl, currentOrigin, serverInfo, sessionId])

  // Display labels
  const mdnsLabel = serverInfo?.hostname
    ? `${serverInfo.hostname}.local`
    : 'mDNS'
  const lanLabel = serverInfo?.lan_ip || 'IP'

  return (
    <div className="min-h-screen bg-base flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between border-b border-border-subtle">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-bold text-text-primary hover:opacity-80 transition-opacity"
        >
          <img src="/favicon.svg" alt="" className="w-5 h-5 rounded-[3px]" />
          Tracefinity
        </Link>
        <span className="text-[11px] text-text-muted">Mobile Capture Setup</span>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="w-full max-w-lg">
          {/* Creating state */}
          {pageState === 'creating' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4">
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <p className="text-sm text-text-secondary">Creating capture session...</p>
            </div>
          )}

          {/* Error state */}
          {pageState === 'error' && (
            <div className="glass-card p-8 flex flex-col items-center gap-4 text-center">
              <p className="text-sm text-red-400">{error}</p>
              <button
                onClick={() => router.push('/')}
                className="btn-secondary px-4 py-2 text-xs"
              >
                Back to Home
              </button>
            </div>
          )}

          {/* Waiting / Ready states */}
          {(pageState === 'waiting' || pageState === 'ready') && (
            <div className="glass-card p-6 md:p-8">
              {/* Status indicator */}
              <div className="flex items-center justify-center gap-2 mb-6">
                {pageState === 'waiting' ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-accent" />
                    <span className="text-sm text-text-secondary">
                      Waiting for phone upload...
                    </span>
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <span className="text-sm font-medium text-green-400">
                      Photo received — ready to trace
                    </span>
                  </>
                )}
              </div>

              {/* QR Code */}
              <div className="flex justify-center mb-4">
                {captureFullUrl ? (
                  <QrCode url={captureFullUrl} size={220} />
                ) : (
                  <div className="w-[244px] h-[244px] glass rounded-[8px] flex items-center justify-center">
                    <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
                  </div>
                )}
              </div>

              {/* URL mode selector */}
              <div className="mb-4">
                <div className="flex gap-0.5 rounded-[7px] bg-elevated p-0.5">
                  {serverInfo?.hostname && (
                    <button
                      onClick={() => handleModeChange('mdns')}
                      className={`flex-1 h-7 px-2 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-colors ${
                        urlMode === 'mdns'
                          ? 'bg-surface text-text-primary shadow-sm'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      <Wifi className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate">{mdnsLabel}</span>
                    </button>
                  )}
                  {serverInfo?.lan_ip && (
                    <button
                      onClick={() => handleModeChange('lan')}
                      className={`flex-1 h-7 px-2 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-colors ${
                        urlMode === 'lan'
                          ? 'bg-surface text-text-primary shadow-sm'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      <Globe className="w-3 h-3 flex-shrink-0" />
                      <span>{lanLabel}</span>
                    </button>
                  )}
                  <button
                    onClick={() => handleModeChange('custom')}
                    className={`flex-1 h-7 px-2 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-colors ${
                      urlMode === 'custom'
                        ? 'bg-surface text-text-primary shadow-sm'
                        : 'text-text-muted hover:text-text-secondary'
                    }`}
                  >
                    <Pencil className="w-3 h-3 flex-shrink-0" />
                    <span>Custom</span>
                  </button>
                </div>
                {urlMode === 'custom' && (
                  <input
                    type="text"
                    value={customUrl}
                    onChange={e => handleCustomUrlChange(e.target.value)}
                    className="mt-1.5 w-full px-3 py-1.5 text-xs bg-elevated border border-border-subtle rounded-[7px] text-text-primary outline-none focus:border-accent font-mono"
                    placeholder={currentOrigin || 'http://192.168.1.x:3000'}
                  />
                )}
              </div>

              {/* Instructions */}
              <div className="space-y-2 text-center">
                <div className="flex items-center justify-center gap-2 text-sm text-text-primary">
                  <Smartphone className="w-4 h-4" />
                  <span>Scan this QR code with your phone</span>
                </div>
                <ol className="text-xs text-text-muted space-y-1 list-decimal list-inside text-left max-w-xs mx-auto">
                  <li>Your phone will open the capture page</li>
                  <li>Take a top-down photo of your tool on paper</li>
                  <li>The photo uploads directly into this session</li>
                </ol>
              </div>

              {/* Proceed button */}
              {pageState === 'ready' && sessionId && (
                <div className="mt-6">
                  <button
                    onClick={() => router.push(`/trace/${sessionId}`)}
                    className="btn-primary px-6 py-3 text-sm w-full touch-target"
                  >
                    Proceed to Trace
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
