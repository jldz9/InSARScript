import { useState } from 'react'
import type { Theme } from './theme'

export interface Filters {
  startDate:       string
  endDate:         string
  flightDirection: string   // '' | 'ASCENDING' | 'DESCENDING'
  pathStart:       string
  pathEnd:         string
  frameStart:      string
  frameEnd:        string
  maxResults:      string
}

export const DEFAULT_FILTERS: Filters = {
  startDate:       '',
  endDate:         '',
  flightDirection: '',
  pathStart:       '',
  pathEnd:         '',
  frameStart:      '',
  frameEnd:        '',
  maxResults:      '2000',
}

export function hasActiveFilters(f: Filters): boolean {
  return !!(f.flightDirection || f.pathStart || f.pathEnd ||
            f.frameStart || f.frameEnd ||
            (f.maxResults && f.maxResults !== '2000'))
}

interface Props {
  open:    boolean
  filters: Filters
  theme:   Theme
  onClose: () => void
  onApply: (f: Filters) => void
}

export default function SearchFilters({ open, filters, theme: t, onClose, onApply }: Props) {
  const [draft, setDraft] = useState<Filters>(filters)

  if (!open) return null

  const sectionHead: React.CSSProperties = {
    background: t.isDark ? '#252540' : '#c8cdd4',
    color: t.text, padding: '7px 16px',
    fontWeight: 700, fontSize: 12, letterSpacing: '0.05em',
    borderTop: `1px solid ${t.border}`, borderBottom: `1px solid ${t.border}`,
  }
  const label: React.CSSProperties = {
    color: t.textMuted, fontSize: 11, marginBottom: 5, display: 'block',
  }
  const input: React.CSSProperties = {
    background: t.inputBg, border: `1px solid ${t.inputBorder}`,
    color: t.text, borderRadius: 4, padding: '5px 8px',
    fontSize: 12, width: '100%', boxSizing: 'border-box',
    colorScheme: t.isDark ? 'dark' : 'light',
  }

  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.45)',
      }} />

      {/* Modal */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%', zIndex: 101,
        transform: 'translate(-50%, -50%)',
        background: t.bg2, border: `1px solid ${t.border}`,
        borderRadius: 8, width: 480,
        boxShadow: '0 8px 40px rgba(0,0,0,0.45)',
        overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>

        {/* Header */}
        <div style={{
          background: t.isDark ? '#1a1a2e' : '#d4dae3',
          padding: '11px 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: `1px solid ${t.border}`,
        }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: t.text }}>Search Filters</span>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none',
            color: t.textMuted, cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 0,
          }}>×</button>
        </div>

        {/* ── Date Filters ── */}
        <div style={sectionHead}>Date Filters</div>
        <div style={{ padding: '14px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <label style={label}>Start Date</label>
            <input type="date" style={input}
              value={draft.startDate}
              onChange={e => setDraft(d => ({ ...d, startDate: e.target.value }))} />
          </div>
          <div>
            <label style={label}>End Date</label>
            <input type="date" style={input}
              value={draft.endDate}
              onChange={e => setDraft(d => ({ ...d, endDate: e.target.value }))} />
          </div>
        </div>

        {/* ── Additional Filters ── */}
        <div style={sectionHead}>Additional Filters</div>
        <div style={{ padding: '14px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div>
            <label style={label}>Flight Direction</label>
            <select style={{ ...input, cursor: 'pointer' }}
              value={draft.flightDirection}
              onChange={e => setDraft(d => ({ ...d, flightDirection: e.target.value }))}>
              <option value="">Any</option>
              <option value="ASCENDING">Ascending</option>
              <option value="DESCENDING">Descending</option>
            </select>
          </div>
          <div>
            <label style={label}>Max Results</label>
            <input type="number" style={input} min={1} max={10000}
              value={draft.maxResults}
              onChange={e => setDraft(d => ({ ...d, maxResults: e.target.value }))} />
          </div>
        </div>

        {/* ── Path and Frame Filters ── */}
        <div style={sectionHead}>Path and Frame Filters</div>
        <div style={{ padding: '14px 16px 18px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 14 }}>
          <div>
            <label style={label}>Path Start</label>
            <input type="number" style={input} placeholder="—"
              value={draft.pathStart}
              onChange={e => setDraft(d => ({ ...d, pathStart: e.target.value }))} />
          </div>
          <div>
            <label style={label}>Path End</label>
            <input type="number" style={input} placeholder="—"
              value={draft.pathEnd}
              onChange={e => setDraft(d => ({ ...d, pathEnd: e.target.value }))} />
          </div>
          <div>
            <label style={label}>Frame Start</label>
            <input type="number" style={input} placeholder="—"
              value={draft.frameStart}
              onChange={e => setDraft(d => ({ ...d, frameStart: e.target.value }))} />
          </div>
          <div>
            <label style={label}>Frame End</label>
            <input type="number" style={input} placeholder="—"
              value={draft.frameEnd}
              onChange={e => setDraft(d => ({ ...d, frameEnd: e.target.value }))} />
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 16px',
          borderTop: `1px solid ${t.border}`,
          background: t.isDark ? '#1a1a2e' : '#d4dae3',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <button onClick={() => setDraft(DEFAULT_FILTERS)} style={{
            background: 'transparent', border: `1px solid ${t.border}`,
            color: t.textMuted, borderRadius: 4, padding: '5px 14px',
            cursor: 'pointer', fontSize: 12,
          }}>Clear All</button>

          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onClose} style={{
              background: 'transparent', border: `1px solid ${t.border}`,
              color: t.text, borderRadius: 4, padding: '5px 14px',
              cursor: 'pointer', fontSize: 12,
            }}>Cancel</button>
            <button onClick={() => { onApply(draft); onClose() }} style={{
              background: t.btnActiveBg, border: `1px solid ${t.btnActiveBorder}`,
              color: t.isDark ? '#e0f0ff' : t.btnActiveFg,
              borderRadius: 4, padding: '5px 18px',
              cursor: 'pointer', fontSize: 12, fontWeight: 700,
            }}>Update</button>
          </div>
        </div>
      </div>
    </>
  )
}