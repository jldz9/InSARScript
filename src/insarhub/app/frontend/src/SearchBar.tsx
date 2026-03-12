import { useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'

interface Props {
  aoi:        { west: number; south: number; east: number; north: number }
  onAoiChange: (aoi: { west: number; south: number; east: number; north: number }) => void
  onSearch:   (start: string, end: string) => void
  searching:  boolean
}

export default function SearchBar({ aoi, onAoiChange, onSearch, searching }: Props) {
  const [start, setStart] = useState<Date | null>(new Date('2021-01-01'))
  const [end,   setEnd]   = useState<Date | null>(new Date('2022-01-01'))

  function fmt(d: Date | null) {
    return d ? d.toISOString().slice(0, 10) : ''
  }

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10,
      background: '#1a1a2e', borderBottom: '1px solid #333',
      display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px',
    }}>
      <span style={{ fontWeight: 700, fontSize: 18, color: '#4fc3f7', marginRight: 8 }}>
        InSARHub
      </span>

      {/* AOI bbox inputs — updated by typing or by drawing on map */}
      {(['west','south','east','north'] as const).map(k => (
        <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <label style={labelStyle}>{k[0].toUpperCase()}</label>
          <input
            style={inputStyle}
            type="number"
            value={aoi[k]}
            onChange={e => onAoiChange({ ...aoi, [k]: +e.target.value })}
          />
        </span>
      ))}

      <div style={{ width: 1, height: 24, background: '#444' }} />

      <label style={labelStyle}>Start</label>
      <DatePicker
        selected={start} onChange={setStart} dateFormat="yyyy-MM-dd"
        customInput={<input style={inputStyle} />}
      />
      <label style={labelStyle}>End</label>
      <DatePicker
        selected={end} onChange={setEnd} dateFormat="yyyy-MM-dd"
        customInput={<input style={inputStyle} />}
      />

      <button onClick={() => onSearch(fmt(start), fmt(end))} disabled={searching} style={btnStyle}>
        {searching ? 'Searching…' : 'Search'}
      </button>
    </div>
  )
}

const labelStyle: React.CSSProperties = { color: '#aaa', fontSize: 12, whiteSpace: 'nowrap' }
const inputStyle: React.CSSProperties = {
  width: 80, background: '#2a2a3e', border: '1px solid #444',
  color: '#e0e0e0', borderRadius: 4, padding: '4px 6px', fontSize: 13,
}
const btnStyle: React.CSSProperties = {
  marginLeft: 8, padding: '6px 20px', background: '#4fc3f7',
  color: '#000', border: 'none', borderRadius: 4,
  fontWeight: 600, cursor: 'pointer', fontSize: 14,
}