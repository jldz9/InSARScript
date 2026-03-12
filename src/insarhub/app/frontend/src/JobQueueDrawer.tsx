import { useState, useEffect } from 'react'
import type { Theme } from './theme'

const API = 'http://localhost:8000'

interface JobFolder {
  name:     string
  path:     string
  tags:     string[]
  workflow: Record<string, string>
}

interface Props {
  theme:   Theme
  workdir: string
  onClose: () => void
}

// Color per workflow role
const ROLE_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  downloader: { bg: '#0d3b6e', color: '#90caf9', border: '#1565c0' },
  processor:  { bg: '#4a2500', color: '#ffcc80', border: '#e65100' },
  analyzer:   { bg: '#1b3a2a', color: '#a5d6a7', border: '#2e7d32' },
}
const ROLE_FALLBACK = { bg: '#1e1e2e', color: '#aaa', border: '#444' }

// ── L2 Drawer ────────────────────────────────────────────────────────────────

const ROLE_ACTIONS: Record<string, string[]> = {
  downloader: ['Select Pairs', 'Download'],
  processor:  ['Submit', 'Refresh', 'Download Results', 'Watch'],
  analyzer:   ['Run', 'Cleanup'],
}

interface L2Props {
  theme:   Theme
  job:     JobFolder
  role:    string
  cls:     string
  onClose: () => void
}

function JobRoleDrawer({ theme: t, job, role, cls, onClose }: L2Props) {
  const roleColor = ROLE_COLORS[role] ?? ROLE_FALLBACK
  const actions   = ROLE_ACTIONS[role] ?? []

  return (
    <div style={{
      position: 'fixed', top: 48, right: 340, bottom: 0,
      width: 280,
      background: t.bg, borderLeft: `1px solid ${t.border}`,
      display: 'flex', flexDirection: 'column',
      zIndex: 111,
      boxShadow: '-4px 0 20px rgba(0,0,0,0.25)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: `1px solid ${t.border}`,
        background: t.bg2, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 3,
            background: roleColor.bg, color: roleColor.color,
            border: `1px solid ${roleColor.border}`,
            textTransform: 'capitalize',
          }}>
            {role}
          </span>
          <span style={{ color: t.text, fontWeight: 700, fontSize: 13 }}>{cls}</span>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer',
                   color: t.textMuted, fontSize: 20, lineHeight: 1, padding: '0 4px' }}
        >×</button>
      </div>

      {/* Job context */}
      <div style={{
        padding: '8px 16px',
        borderBottom: `1px solid ${t.divider}`,
        background: t.bg2,
        flexShrink: 0,
      }}>
        <span style={{ color: t.textMuted, fontSize: 10 }}>Folder: </span>
        <span style={{ color: t.text, fontSize: 11, fontFamily: 'monospace' }}>{job.name}</span>
      </div>

      {/* Actions */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {actions.map(action => (
          <button
            key={action}
            style={{
              width: '100%', padding: '8px 12px', fontSize: 12, textAlign: 'left',
              background: 'transparent', color: t.text,
              border: `1px solid ${t.border}`, borderRadius: 4,
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = t.bg2 }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: roleColor.color,
            }} />
            {action}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main Drawer ───────────────────────────────────────────────────────────────

export default function JobQueueDrawer({ theme: t, workdir, onClose }: Props) {
  const [jobs,    setJobs]    = useState<JobFolder[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')
  const [l2,      setL2]      = useState<{ job: JobFolder; role: string; cls: string } | null>(null)

  const loadJobs = () => {
    setLoading(true)
    setError('')
    fetch(`${API}/api/job-folders`)
      .then(r => r.json())
      .then(d => { setJobs(d.jobs ?? []); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }

  useEffect(() => { loadJobs() }, [workdir])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={() => { setL2(null); onClose() }}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 110 }}
      />

      {/* L2 drawer */}
      {l2 && (
        <JobRoleDrawer
          theme={t}
          job={l2.job}
          role={l2.role}
          cls={l2.cls}
          onClose={() => setL2(null)}
        />
      )}

      {/* Main drawer */}
      <div style={{
        position: 'fixed', top: 48, right: 0, bottom: 0,
        width: 340,
        background: t.bg, borderLeft: `1px solid ${t.border}`,
        display: 'flex', flexDirection: 'column',
        zIndex: 111,
        boxShadow: '-4px 0 24px rgba(0,0,0,0.3)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: `1px solid ${t.border}`,
          background: t.bg2, flexShrink: 0,
        }}>
          <div>
            <span style={{ color: t.text, fontWeight: 700, fontSize: 14 }}>Job Folders</span>
            <span style={{ color: t.textMuted, fontSize: 11, marginLeft: 8 }}>{workdir}</span>
          </div>
          <button
            onClick={() => { setL2(null); onClose() }}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
                     color: t.textMuted, fontSize: 20, lineHeight: 1, padding: '0 4px' }}
          >×</button>
        </div>

        {/* Content */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '10px 0' }}>
          {loading ? (
            <div style={{ color: t.textMuted, fontSize: 12, textAlign: 'center', padding: '40px 0' }}>
              Loading…
            </div>
          ) : error ? (
            <div style={{ color: '#e53935', fontSize: 12, padding: '16px' }}>{error}</div>
          ) : jobs.length === 0 ? (
            <div style={{ color: t.textMuted, fontSize: 12, textAlign: 'center', padding: '40px 16px' }}>
              No subfolders found in workdir.
            </div>
          ) : jobs.map(job => {
            const wfEntries = Object.entries(job.workflow).filter(([k]) => k !== 'updated_at')
            return (
              <div key={job.path} style={{
                padding: '10px 16px',
                borderBottom: `1px solid ${t.divider}`,
              }}>
                {/* Folder name */}
                <span style={{
                  color: t.text, fontSize: 12, fontFamily: 'monospace',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  display: 'block', marginBottom: wfEntries.length ? 6 : 0,
                }} title={job.path}>
                  {job.name}
                </span>

                {/* Clickable role tags — ordered downloader → processor → analyzer */}
                {wfEntries.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                    {(['downloader', 'processor', 'analyzer'] as const)
                      .filter(role => job.workflow[role])
                      .map((role, idx) => {
                        const cls = job.workflow[role]
                        const rc = ROLE_COLORS[role] ?? ROLE_FALLBACK
                        const isActive = l2?.job.path === job.path && l2?.role === role
                        return (
                          <div key={role} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {idx > 0 && (
                              <span style={{ color: t.textMuted, fontSize: 10, userSelect: 'none' }}>→</span>
                            )}
                            <button
                              onClick={() => setL2(isActive ? null : { job, role, cls })}
                              title={`${role}: ${cls}`}
                              style={{
                                fontSize: 10, fontWeight: 600,
                                padding: '2px 7px', borderRadius: 3,
                                background: isActive ? rc.color : rc.bg,
                                color:      isActive ? rc.bg    : rc.color,
                                border:     `1px solid ${rc.border}`,
                                cursor: 'pointer',
                              }}
                            >
                              {cls}
                            </button>
                          </div>
                        )
                      })}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer — refresh */}
        <div style={{
          padding: '10px 16px', borderTop: `1px solid ${t.border}`,
          background: t.bg2, flexShrink: 0,
        }}>
          <button
            onClick={loadJobs}
            disabled={loading}
            style={{
              width: '100%', padding: '6px 0', fontSize: 12,
              background: 'transparent', color: loading ? t.textMuted : t.accent,
              border: `1px solid ${loading ? t.border : t.btnActiveBorder}`,
              borderRadius: 5, cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>
    </>
  )
}
