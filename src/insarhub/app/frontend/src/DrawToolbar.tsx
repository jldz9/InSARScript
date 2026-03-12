// Floating draw toolbar — overlays the map on the left side

interface Props {
  drawMode: 'box' | 'polygon' | 'pin' | null
  onModeChange: (mode: 'box' | 'polygon' | 'pin' | null) => void
  onShapefileUpload: (file: File) => void
}

const TOOLS: { mode: 'box' | 'polygon' | 'pin'; label: string; title: string }[] = [
  { mode: 'box',     label: '⬜', title: 'Drag box AOI' },
  { mode: 'polygon', label: '⬡',  title: 'Draw polygon AOI' },
  { mode: 'pin',     label: '📍', title: 'Place point AOI' },
]

export default function DrawToolbar({ drawMode, onModeChange, onShapefileUpload }: Props) {
  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) onShapefileUpload(file)
    e.target.value = ''   // reset so same file can be re-uploaded
  }

  return (
    <div style={{
      position: 'absolute', top: 80, left: 12, zIndex: 10,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      {TOOLS.map(({ mode, label, title }) => (
        <button
          key={mode}
          title={title}
          onClick={() => onModeChange(drawMode === mode ? null : mode)}
          style={btnStyle(drawMode === mode)}
        >
          {label}
        </button>
      ))}

      {/* Shapefile upload */}
      <label title="Upload shapefile (.zip)" style={btnStyle(false)}>
        📂
        <input
          type="file"
          accept=".zip,.shp"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </label>
    </div>
  )
}

function btnStyle(active: boolean): React.CSSProperties {
  return {
    width: 36, height: 36,
    background: active ? '#4fc3f7' : '#1a1a2e',
    color: active ? '#000' : '#e0e0e0',
    border: `1px solid ${active ? '#4fc3f7' : '#444'}`,
    borderRadius: 6,
    fontSize: 16, cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  }
}