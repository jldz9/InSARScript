interface Props {
  message: string
  progress: number   // 0-100, -1 = hide
}

export default function StatusBar({ message, progress }: Props) {
  if (!message) return null

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 10,
      background: '#1a1a2e', borderTop: '1px solid #333',
      padding: '6px 16px', fontSize: 13, color: '#ccc',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <span>{message}</span>
      {progress >= 0 && progress < 100 && (
        <div style={{ flex: 1, maxWidth: 300, height: 6, background: '#333', borderRadius: 3 }}>
          <div style={{
            width: `${progress}%`, height: '100%',
            background: '#4fc3f7', borderRadius: 3,
            transition: 'width 0.3s',
          }} />
        </div>
      )}
    </div>
  )
}