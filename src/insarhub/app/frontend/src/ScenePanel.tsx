import { useState, useRef } from 'react'
import type { Theme } from './theme'

export function parseStack(s: string): { path: number; frame: number } | null {
  const m = s.match(/\(\s*(\d+)\s*,\s*(\d+)\s*\)/)
  if (!m) return null
  return { path: parseInt(m[1]), frame: parseInt(m[2]) }
}

const API = 'http://localhost:8000'

interface Props {
  feature:      GeoJSON.Feature
  theme:        Theme
  stackStart?: string
  stackEnd?:   string
  stackCount:   number | null
  stackUrls:    string[]
  workdir:      string
  stackOpen:    boolean
  onClose:      () => void
  onStackClick: () => void
}

const row = (t: Theme, label: string, value: React.ReactNode) => (
  <div key={label} style={{ display: 'flex', gap: 8, padding: '4px 0',
                borderBottom: `1px solid ${t.divider}` }}>
    <span style={{ width: 106, flexShrink: 0, color: t.textMuted, fontSize: 11,
                   textTransform: 'uppercase', letterSpacing: '0.04em', paddingTop: 1 }}>
      {label}
    </span>
    <span style={{ color: t.text, fontSize: 13, wordBreak: 'break-all' }}>{value}</span>
  </div>
)

export default function ScenePanel({
  feature, theme: t, stackStart, stackEnd,
  stackCount, stackUrls, workdir, stackOpen, onClose, onStackClick,
}: Props) {
  const p     = feature.properties ?? {}
  const stack = parseStack(p._stack ?? '')

  const [dlStatus,  setDlStatus]  = useState<'idle'|'downloading'|'done'|'error'>('idle')
  const [dlMessage, setDlMessage] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function handleDownloadStack() {
    if (!stackUrls.length) return
    setDlStatus('downloading')
    setDlMessage(`Queuing ${stackUrls.length} scenes…`)
    try {
      const res      = await fetch(`${API}/api/download-stack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: stackUrls, workdir }),
      })
      const { job_id } = await res.json()
      pollRef.current = setInterval(async () => {
        const r   = await fetch(`${API}/api/jobs/${job_id}`)
        const job = await r.json()
        setDlMessage(job.message)
        if (job.status === 'done') {
          clearInterval(pollRef.current!)
          setDlStatus('done')
        } else if (job.status === 'error') {
          clearInterval(pollRef.current!)
          setDlStatus('error')
        }
      }, 1500)
    } catch (e) {
      setDlStatus('error')
      setDlMessage(String(e))
    }
  }

  const dlStatusColor = dlStatus === 'done' ? '#4caf50' : dlStatus === 'error' ? '#e53935' : t.textMuted

  return (
    <div style={{
      width: 280, height: '100%',
      background: t.bg,
      borderLeft: `1px solid ${t.border}`,
      display: 'flex', flexDirection: 'column',
      boxShadow: '-4px 0 16px rgba(0,0,0,0.25)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px',
        borderBottom: `1px solid ${t.border}`,
        background: t.bg2, flexShrink: 0,
      }}>
        <span style={{ color: t.text, fontWeight: 600, fontSize: 13 }}>Stack Info</span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: t.textMuted, fontSize: 18, lineHeight: 1, padding: '0 2px',
        }}>×</button>
      </div>

      {/* Stack badge */}
      {stack && (
        <div style={{
          padding: '8px 14px', background: t.bg2,
          borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <span style={{
            background: t.btnActiveBg, color: t.accent,
            borderRadius: 4, padding: '2px 8px', fontSize: 12, fontWeight: 600,
          }}>
            Path {stack.path} · Frame {stack.frame}
          </span>
        </div>
      )}

      {/* Properties */}
      <div style={{ overflowY: 'auto', padding: '8px 14px', flex: 1 }}>
        <div>
          {/* SCENES — clickable to open stack list */}
          <div style={{ display: 'flex', gap: 8, padding: '4px 0',
                        borderBottom: `1px solid ${t.divider}` }}>
            <span style={{ width: 106, flexShrink: 0, color: t.textMuted, fontSize: 11,
                           textTransform: 'uppercase', letterSpacing: '0.04em', paddingTop: 1 }}>
              Scenes
            </span>
            <button onClick={onStackClick} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              color: stackOpen ? t.accent : t.btnActiveFg,
              fontSize: 13, fontWeight: 600, textDecoration: 'underline',
            }}>
              {stackCount ?? '…'}
            </button>
          </div>

          {row(t, 'Start', stackStart ?? '—')}
          {row(t, 'End',   stackEnd   ?? '—')}
          {row(t, 'Direction',    p.flightDirection ?? '—')}
          {row(t, 'Platform',     p.platform        ?? '—')}
          {row(t, 'Beam Mode',    p.beamModeType    ?? p.beamMode ?? '—')}
          {row(t, 'Polarization', p.polarization    ?? '—')}
          {p.processingLevel && row(t, 'Level', p.processingLevel)}
        </div>

        {/* Download Stack */}
        <div style={{ marginTop: 14 }}>
          <button
            onClick={handleDownloadStack}
            disabled={dlStatus === 'downloading' || !stackUrls.length}
            style={{
              display: 'block', width: '100%', padding: '8px 0', textAlign: 'center',
              background: dlStatus === 'done'   ? '#1b5e20'
                        : dlStatus === 'error'  ? '#b71c1c'
                        : t.btnActiveBg,
              color: dlStatus === 'done'   ? '#a5d6a7'
                   : dlStatus === 'error'  ? '#ef9a9a'
                   : t.accent,
              border: `1px solid ${t.btnActiveBorder}`,
              borderRadius: 6, fontSize: 12, fontWeight: 600,
              cursor: dlStatus === 'downloading' ? 'wait' : 'pointer',
            }}
          >
            {dlStatus === 'downloading' ? `⟳ Downloading…`
            : dlStatus === 'done'       ? '✓ Stack Downloaded'
            : dlStatus === 'error'      ? '✕ Retry'
            : `↓ Download Stack (${stackUrls.length})`}
          </button>
          {dlMessage && (
            <div style={{ color: dlStatusColor, fontSize: 11, marginTop: 5 }}>{dlMessage}</div>
          )}
        </div>
      </div>
    </div>
  )
}
