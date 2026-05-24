const waveHeights = [
  18, 24, 16, 52, 22, 30, 56, 28, 20, 34, 26, 46, 24, 22, 40, 60, 24,
  18, 36, 30, 20, 52, 24, 38, 28, 18, 44, 26, 34, 50, 20, 30, 24, 36,
]

export default function AnalysisCourtVisual() {
  return (
    <div style={{
      position: 'relative',
      minHeight: 0,
      height: '100%',
      borderRadius: 12,
      overflow: 'hidden',
      background: 'linear-gradient(140deg, rgba(3,54,41,0.98), rgba(3,54,41,0.88)), radial-gradient(520px 280px at 60% 72%, rgba(204,78,14,0.24), transparent 62%), #13251f',
      boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)',
    }}>
      <style>{`
        @keyframes breakpoint-scan {
          from { left: 16%; }
          to { left: 78%; }
        }
        @keyframes breakpoint-wave-pulse {
          0%, 100% { transform: scaleY(0.82); opacity: 0.72; }
          50% { transform: scaleY(1); opacity: 1; }
        }
      `}</style>
      <div style={{ position: 'absolute', inset: 44, border: '2px solid rgba(255,255,255,0.22)' }} />
      <div style={{ position: 'absolute', left: 44, right: 44, top: '50%', height: 2, background: 'rgba(255,255,255,0.2)' }} />
      <div style={{
        position: 'absolute',
        left: '16%',
        top: 42,
        bottom: 42,
        width: 3,
        background: 'var(--color-accent)',
        boxShadow: '0 0 0 10px rgba(204,78,14,0.12)',
        animation: 'breakpoint-scan 2.8s ease-in-out infinite alternate',
      }} />
      <div style={{
        position: 'absolute',
        right: 58,
        top: 58,
        maxWidth: 260,
        padding: '14px 16px',
        border: '1px solid rgba(255,255,255,0.18)',
        borderRadius: 8,
        background: 'rgba(3,54,41,0.82)',
        color: '#fff',
        backdropFilter: 'blur(8px)',
      }}>
        <strong style={{ display: 'block', fontFamily: 'var(--font-display)', fontSize: 13, letterSpacing: '0.06em' }}>正在筛选精彩片段</strong>
        <span style={{ display: 'block', marginTop: 6, opacity: 0.62, fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.05em' }}>片段 1 / 10 · 当前 58%</span>
      </div>
      <div style={{
        position: 'absolute',
        left: 58,
        right: 58,
        bottom: 74,
        zIndex: 2,
        display: 'grid',
        gridTemplateColumns: 'repeat(34, 1fr)',
        alignItems: 'center',
        gap: 5,
      }}>
        {Array.from({ length: 34 }).map((_, index) => (
          <i
            key={index}
            style={{
              display: 'block',
              height: waveHeights[index],
              minHeight: 8,
              borderRadius: 999,
              background: index % 4 === 3 || index % 7 === 6 ? 'var(--color-accent)' : 'rgba(255,255,255,0.34)',
              animation: `breakpoint-wave-pulse ${1.8 + (index % 5) * 0.18}s ease-in-out infinite`,
              animationDelay: `${index * 0.035}s`,
              transformOrigin: 'center',
            }}
          />
        ))}
      </div>
    </div>
  )
}
