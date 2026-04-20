// Scene 2 — traces-not-why transition + Scene 3 — logo reveal
// 5.5 – 13.5s
const { Sprite, useSprite, Easing, interpolate, animate, clamp } = window;

function Scene2TraceDust() {
  // Short breath — dark hold between the final opening line and the logo reveal.
  return (
    <Sprite start={9.0} end={10.0}>
      {({ localTime }) => {
        const opacity = interpolate([0, 0.3, 0.7, 1.0], [0, 1, 1, 0], Easing.easeInOutCubic)(localTime);
        return (
          <div style={{ position: 'absolute', inset: 0, background: '#04060a', opacity }} />
        );
      }}
    </Sprite>
  );
}

function LogoMark({ size = 220, glow = 1 }) {
  // A crystalline pinwheel — 6 iridescent blades
  const blades = [];
  const colors = ['#36f3ff', '#8bff8b', '#ffe45e', '#ff9d42', '#ff63f8', '#36f3ff'];
  for (let i = 0; i < 6; i++) {
    const rot = i * 60;
    blades.push(
      <polygon key={i}
        points="0,0 30,-90 0,-110 -30,-90"
        fill={`url(#grad-${i})`}
        transform={`rotate(${rot})`}
        opacity="0.9"
      />
    );
  }
  return (
    <svg width={size} height={size} viewBox="-140 -140 280 280" style={{
      filter: `drop-shadow(0 0 ${30 * glow}px rgba(54,243,255,${0.6 * glow})) drop-shadow(0 0 ${80 * glow}px rgba(54,243,255,${0.3 * glow}))`,
    }}>
      <defs>
        {colors.map((c, i) => (
          <linearGradient key={i} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="-110" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor={c} stopOpacity="0.4"/>
            <stop offset="70%" stopColor={c} stopOpacity="0.95"/>
            <stop offset="100%" stopColor="#ffffff" stopOpacity="1"/>
          </linearGradient>
        ))}
        <radialGradient id="coreGlow">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1"/>
          <stop offset="40%" stopColor="#36f3ff" stopOpacity="0.8"/>
          <stop offset="100%" stopColor="#36f3ff" stopOpacity="0"/>
        </radialGradient>
      </defs>
      <circle cx="0" cy="0" r="90" fill="url(#coreGlow)" opacity="0.5"/>
      {blades}
      <circle cx="0" cy="0" r="14" fill="#ffffff" opacity="0.95"/>
    </svg>
  );
}

function Scene3Logo() {
  return (
    <Sprite start={10.0} end={13.5}>
      {({ localTime, progress }) => {
        // logo: scales from 0.4→1, rotates slowly, glow pulses
        const logoIn = Easing.easeOutCubic(clamp(localTime / 1.2, 0, 1));
        const logoOut = Easing.easeInCubic(clamp((localTime - 3.6) / 0.9, 0, 1));
        const logoOp = logoIn * (1 - logoOut);
        const scale = 0.5 + 0.55 * logoIn;
        const rot = localTime * 14;
        const glow = 0.6 + 0.4 * Math.sin(localTime * 1.8);

        // wordmark types in after 1.0s
        const typeT = clamp((localTime - 1.2) / 1.4, 0, 1);
        const wordmark = 'AgentRewind';
        const visibleChars = Math.floor(typeT * wordmark.length);
        const wordmarkOut = logoOut;

        // eyebrow
        const eyeT = clamp((localTime - 2.2) / 0.5, 0, 1);

        return (
          <div style={{ position: 'absolute', inset: 0, background: '#04060a', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
            {/* ambient beam from center */}
            <div style={{
              position: 'absolute', left: '50%', top: '50%',
              width: 1600, height: 1600,
              transform: `translate(-50%, -50%) scale(${logoIn})`,
              background: 'radial-gradient(circle, rgba(54,243,255,0.18) 0%, transparent 55%)',
              pointerEvents: 'none',
              opacity: logoOp,
            }}/>
            <div style={{
              opacity: logoOp,
              transform: `scale(${scale}) rotate(${rot}deg)`,
              marginBottom: 40,
            }}>
              <LogoMark size={240} glow={glow} />
            </div>
            <div style={{
              opacity: (1 - wordmarkOut),
              fontSize: 88, fontWeight: 700,
              letterSpacing: '-0.05em',
              color: '#f2f7ff',
              textShadow: '0 0 30px rgba(54,243,255,0.5)',
              fontFamily: "'JetBrains Mono', monospace",
              minHeight: 100,
            }}>
              {wordmark.slice(0, visibleChars)}
              {typeT < 1 && <span style={{ color: '#36f3ff', animation: 'none' }}>▌</span>}
            </div>
            <div style={{
              opacity: eyeT * (1 - wordmarkOut),
              marginTop: 24,
              fontSize: 14, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#5d718f', fontWeight: 600,
            }}>Multi-agent system debugging</div>
          </div>
        );
      }}
    </Sprite>
  );
}

window.Scene2TraceDust = Scene2TraceDust;
window.Scene3Logo = Scene3Logo;
window.LogoMark = LogoMark;
