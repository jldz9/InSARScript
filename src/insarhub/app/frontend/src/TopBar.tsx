import { useState, useEffect } from 'react'
import type { Theme } from './theme'
import { Icons } from './assets/icons'

interface Props {
  downloaderType:          string
  downloaderOptions:       string[]
  onDownloaderTypeChange:  (type: string) => void
  aoiWkt:                  string | null
  onAoiWktChange:   (wkt: string) => void
  startDate:        string
  endDate:          string
  onDatesChange:    (start: string, end: string) => void
  onSearch:         () => void
  searching:        boolean
  theme:            Theme
  onThemeToggle:    () => void
  onFiltersOpen:    () => void
  hasActiveFilters: boolean
  onJobsOpen:       () => void
  jobsOpen:         boolean
  onSettingsOpen:   () => void
}

export default function TopBar({
  downloaderType, downloaderOptions, onDownloaderTypeChange,
  aoiWkt, onAoiWktChange, startDate, endDate, onDatesChange,
  onSearch, searching,
  theme: t, onThemeToggle, onFiltersOpen, hasActiveFilters, onJobsOpen, jobsOpen, onSettingsOpen,
}: Props) {
  const [wktInput, setWktInput] = useState(aoiWkt ?? '')

  useEffect(() => { setWktInput(aoiWkt ?? '') }, [aoiWkt])

  function handleWktBlur() {
    if (wktInput.trim()) onAoiWktChange(wktInput.trim())
  }

  const inputStyle: React.CSSProperties = {
    background: t.inputBg, border: `1px solid ${t.inputBorder}`,
    color: t.text, borderRadius: 3, padding: '3px 6px', fontSize: 12,
    colorScheme: t.isDark ? 'dark' : 'light',
  }
  const dividerStyle: React.CSSProperties = {
    width: 1, height: 24, background: t.divider, margin: '0 2px', flexShrink: 0,
  }
  const labelStyle: React.CSSProperties = {
    color: t.textMuted, fontSize: 11, whiteSpace: 'nowrap',
  }

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, zIndex: 20,
      background: t.bg, borderBottom: `1px solid ${t.border}`,
      display: 'flex', alignItems: 'center', gap: 10, padding: '6px 14px',
      height: 48,
    }}>
      {/* Brand */}
      <span style={{ fontWeight: 800, fontSize: 17, color: t.accent, marginRight: 6, whiteSpace: 'nowrap' }}>
        InSARHub
      </span>

      <div style={dividerStyle} />

      {/* Downloader */}
      <span style={labelStyle}>Downloader</span>
      <select
        value={downloaderType}
        onChange={e => onDownloaderTypeChange(e.target.value)}
        style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 11, cursor: 'pointer',
                 colorScheme: t.isDark ? 'dark' : 'light', width: 90 }}
      >
        {downloaderOptions.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      <div style={dividerStyle} />

      {/* AOI WKT */}
      <span style={labelStyle}>Area of Interest</span>
      <input
        style={{ ...inputStyle, width: 120, fontFamily: 'monospace', fontSize: 11 }}
        placeholder="Draw or paste WKT…"
        value={wktInput}
        onChange={e => setWktInput(e.target.value)}
        onBlur={handleWktBlur}
        title={wktInput}
      />

      <div style={dividerStyle} />

      {/* Dates — shared with Filters panel */}
      <span style={labelStyle}>Start</span>
      <input type="date" style={{ ...inputStyle, width: 112 }}
        value={startDate}
        onChange={e => onDatesChange(e.target.value, endDate)} />

      <span style={labelStyle}>End</span>
      <input type="date" style={{ ...inputStyle, width: 112 }}
        value={endDate}
        onChange={e => onDatesChange(startDate, e.target.value)} />

      <div style={dividerStyle} />

      {/* Search */}
      <button
        onClick={onSearch}
        disabled={searching}
        style={{
          padding: '5px 18px', background: t.btnActiveBg,
          color: t.isDark ? '#e0f0ff' : t.btnActiveFg,
          border: `1px solid ${t.btnActiveBorder}`, borderRadius: 3,
          fontWeight: 700, fontSize: 13, cursor: 'pointer', letterSpacing: 1,
          whiteSpace: 'nowrap',
        }}
      >
        {searching ? 'Searching…' : 'SEARCH'}
      </button>

      {/* Filters button */}
      <button
        onClick={onFiltersOpen}
        title="Search filters"
        style={{
          padding: '4px 12px',
          background: hasActiveFilters ? t.btnActiveBg : 'transparent',
          color: hasActiveFilters ? (t.isDark ? '#e0f0ff' : t.btnActiveFg) : t.text,
          border: `1px solid ${hasActiveFilters ? t.btnActiveBorder : t.border}`,
          borderRadius: 3, cursor: 'pointer', fontSize: 12,
          display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap',
        }}
      >
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M2 4h12M4 8h8M6 12h4" />
        </svg>
        Filters{hasActiveFilters ? ' •' : ''}
      </button>

      {/* Jobs button */}
      <button
        onClick={onJobsOpen}
        title="Job folders"
        style={{
          padding: '4px 12px',
          background: jobsOpen ? t.btnActiveBg : 'transparent',
          color: jobsOpen ? (t.isDark ? '#e0f0ff' : t.btnActiveFg) : t.text,
          border: `1px solid ${jobsOpen ? t.btnActiveBorder : t.border}`,
          borderRadius: 3, cursor: 'pointer', fontSize: 12,
          display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap',
        }}
      >
        <svg xmlns="http://www.w3.org/2000/svg" height="14" viewBox="0 -960 960 960" width="14" fill="currentColor">
          <path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h168q13-36 43.5-58t68.5-22q38 0 68.5 22t43.5 58h168q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm0-80h560v-560H200v560Zm80-80h280v-80H280v80Zm0-160h400v-80H280v80Zm0-160h400v-80H280v80Zm221.5-198.5Q510-807 510-820t-8.5-21.5Q493-850 480-850t-21.5 8.5Q450-833 450-820t8.5 21.5Q467-790 480-790t21.5-8.5ZM200-200v-560 560Z"/>
        </svg>
        Jobs
      </button>


      {/* Settings — right-aligned */}
      <button
        onClick={onSettingsOpen}
        title="Settings"
        style={{
          marginLeft: 'auto',
          display: 'flex', alignItems: 'center',
          padding: '4px 8px',
          background: 'transparent',
          border: `1px solid ${t.border}`,
          borderRadius: 20,
          cursor: 'pointer',
          color: t.textMuted,
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33
                   1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33
                   l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4
                   h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06
                   A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51
                   a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9
                   a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {/* Theme toggle — icon only */}
      <button
        onClick={onThemeToggle}
        title={t.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        style={{
          display: 'flex', alignItems: 'center',
          padding: '4px 8px',
          background: 'transparent',
          border: `1px solid ${t.border}`,
          borderRadius: 20,
          cursor: 'pointer',
          color: t.textMuted,
        }}
      >
        {t.isDark
          ? <Icons.Dark  size={16} className="text-yellow-500" />
          : <Icons.Light size={16} className="text-indigo-600" />}
      </button>
    </div>
  )
}