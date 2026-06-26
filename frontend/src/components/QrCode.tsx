'use client'

import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'

interface Props {
  url: string
  size?: number
}

export function QrCode({ url, size = 200 }: Props) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!url) {
    return (
      <div className="flex flex-col items-center gap-3">
        <div
          className="glass rounded-[8px] flex items-center justify-center"
          style={{ width: size + 24, height: size + 24 }}
        >
          <p className="text-xs text-text-muted text-center px-4">
            URL not configured
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3">
      {mounted ? (
        <div className="bg-white rounded-[8px] p-3 inline-block">
          <QRCodeSVG
            value={url}
            size={size}
            bgColor="#ffffff"
            fgColor="#000000"
            level="M"
          />
        </div>
      ) : (
        <div
          className="glass rounded-[8px]"
          style={{ width: size + 24, height: size + 24 }}
        />
      )}
      <p className="text-xs text-text-muted text-center break-all select-all max-w-[248px]">
        {url}
      </p>
    </div>
  )
}
