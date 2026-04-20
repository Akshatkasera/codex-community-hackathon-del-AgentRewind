// Scene 6 — Contradictions + memory carryover
// Scene 7 — Step edit
// 24.5 – 35.5s
const { Sprite, useSprite, Easing, interpolate, animate, clamp } = window;

function Scene6Contradictions() {
  return (
    <Sprite start={24.5} end={30.0}>
      {({ localTime }) => {
        const fadeIn = clamp(localTime / 0.4, 0, 1);
        const fadeOut = clamp((localTime - 4.9) / 0.6, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        // card A appears at 0.2s, card B at 0.6s
        const aT = clamp((localTime - 0.2) / 0.55, 0, 1);
        const bT = clamp((localTime - 0.7) / 0.55, 0, 1);

        // contradiction line draws between them at 1.3s
        const lineT = clamp((localTime - 1.4) / 0.7, 0, 1);

        // memory graph lights up trailing steps at 2.5s
        const memStart = 2.8;
        const eyeT = clamp((localTime - 0.1) / 0.4, 0, 1);

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity }}>
            <div style={{
              position: 'absolute', top: 140, left: '50%', transform: 'translateX(-50%)',
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#36f3ff', opacity: eyeT, fontWeight: 600,
            }}>Inspect contradictions · Trace memory</div>

            {/* Two contradicting cards */}
            <div style={{ position: 'relative', width: 1200, height: 560 }}>
              {/* Card A — s2 output */}
              <div style={{
                position: 'absolute', left: 60, top: 110,
                width: 420, padding: '18px 20px',
                borderRadius: 18,
                border: '1px solid rgba(139,255,139,0.45)',
                background: 'linear-gradient(180deg, rgba(14,24,18,0.92), rgba(8,14,12,0.92))',
                boxShadow: '0 0 0 1px rgba(139,255,139,0.3), 0 0 32px rgba(139,255,139,0.15)',
                opacity: aT, transform: `translateX(${(1 - aT) * -30}px) scale(${0.96 + 0.04 * aT})`,
                fontFamily: "'JetBrains Mono', monospace",
                backdropFilter: 'blur(14px)',
              }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 999, background: '#8bff8b', boxShadow: '0 0 10px #8bff8b' }}/>
                  <span style={{ color: '#8bff8b', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Coder · s2 output</span>
                </div>
                <div style={{ fontSize: 13, color: '#a7b8d1', lineHeight: 1.6 }}>
                  "Using <span style={{ color: '#f2f7ff' }}>redis.memorize()</span> to persist intermediate state between agents."
                </div>
              </div>

              {/* Card B — repository truth */}
              <div style={{
                position: 'absolute', right: 60, top: 320,
                width: 420, padding: '18px 20px',
                borderRadius: 18,
                border: '1px solid rgba(255,228,94,0.55)',
                background: 'linear-gradient(180deg, rgba(28,24,10,0.92), rgba(14,12,6,0.92))',
                boxShadow: '0 0 0 1px rgba(255,228,94,0.3), 0 0 32px rgba(255,228,94,0.15)',
                opacity: bT, transform: `translateX(${(1 - bT) * 30}px) scale(${0.96 + 0.04 * bT})`,
                fontFamily: "'JetBrains Mono', monospace",
                backdropFilter: 'blur(14px)',
              }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 999, background: '#ffe45e', boxShadow: '0 0 10px #ffe45e' }}/>
                  <span style={{ color: '#ffe45e', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Repository · ground truth</span>
                </div>
                <div style={{ fontSize: 13, color: '#a7b8d1', lineHeight: 1.6 }}>
                  redis client exposes <span style={{ color: '#f2f7ff' }}>.set() .get() .expire()</span><br/>
                  <span style={{ color: '#ff7070' }}>no method named memorize</span>
                </div>
              </div>

              {/* contradiction line SVG */}
              <svg style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} width="1200" height="560">
                <defs>
                  <linearGradient id="contrGrad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#8bff8b"/>
                    <stop offset="50%" stopColor="#ff7070"/>
                    <stop offset="100%" stopColor="#ffe45e"/>
                  </linearGradient>
                </defs>
                <path
                  d="M 480 160 C 650 160, 550 360, 720 370"
                  stroke="url(#contrGrad)"
                  strokeWidth="2.5"
                  fill="none"
                  strokeDasharray="600"
                  strokeDashoffset={(1 - lineT) * 600}
                  style={{ filter: 'drop-shadow(0 0 8px rgba(255,112,112,0.6))' }}
                />
                {lineT > 0.8 && (
                  <g transform="translate(600, 260)" opacity={(lineT - 0.8) / 0.2}>
                    <circle r="26" fill="rgba(255,112,112,0.15)" stroke="#ff7070" strokeWidth="1.5"/>
                    <text textAnchor="middle" y="5" fill="#ff7070" fontFamily="JetBrains Mono" fontSize="14" fontWeight="700">!</text>
                  </g>
                )}
              </svg>

              {/* Label */}
              {lineT > 0.9 && (
                <div style={{
                  position: 'absolute', left: '50%', top: 240, transform: 'translateX(-50%)',
                  fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase',
                  color: '#ff7070', fontWeight: 700,
                  opacity: (lineT - 0.9) / 0.1,
                }}>Contradiction</div>
              )}

              {/* Memory carryover mini graph below */}
              <div style={{
                position: 'absolute', left: '50%', bottom: -20, transform: 'translateX(-50%)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}>
                {FILM_STEPS.map((s, i) => {
                  const t = clamp((localTime - memStart - i * 0.15) / 0.4, 0, 1);
                  const lit = i >= 1 && localTime > memStart + i * 0.15;
                  return (
                    <React.Fragment key={s.id}>
                      <div style={{
                        padding: '8px 14px',
                        borderRadius: 12,
                        border: `1px solid ${lit ? 'rgba(255,112,112,0.6)' : 'rgba(115,138,171,0.3)'}`,
                        background: lit ? 'rgba(40,14,18,0.8)' : 'rgba(14,18,26,0.8)',
                        boxShadow: lit ? '0 0 16px rgba(255,112,112,0.3)' : 'none',
                        color: lit ? '#ff7070' : '#5d718f',
                        fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                        opacity: t,
                        fontFamily: "'JetBrains Mono', monospace",
                      }}>{s.id}</div>
                      {i < FILM_STEPS.length - 1 && (
                        <div style={{
                          width: 24, height: 2,
                          background: lit ? 'linear-gradient(90deg, #ff7070, rgba(255,112,112,0.3))' : 'rgba(115,138,171,0.2)',
                          opacity: t,
                        }}/>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              {localTime > memStart && (
                <div style={{
                  position: 'absolute', left: '50%', bottom: -52, transform: 'translateX(-50%)',
                  fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase',
                  color: '#5d718f', fontWeight: 600,
                  opacity: clamp((localTime - memStart) / 0.4, 0, 1),
                }}>Memory carryover → contaminates downstream</div>
              )}
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

function Scene7Edit() {
  return (
    <Sprite start={30.0} end={35.5}>
      {({ localTime }) => {
        const fadeIn = clamp(localTime / 0.4, 0, 1);
        const fadeOut = clamp((localTime - 4.9) / 0.6, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        const eyeT = clamp((localTime - 0.1) / 0.4, 0, 1);

        // original prompt on left, edited prompt on right — typewriter
        const oldPrompt = 'Implement cache persistence layer using Redis memorize().';
        const newPrompt = 'Implement cache persistence layer using the available Redis client methods. Verify method names against the repo before coding.';

        const typeStart = 0.6;
        const typeT = clamp((localTime - typeStart) / 3.2, 0, 1);
        const shown = newPrompt.slice(0, Math.floor(typeT * newPrompt.length));
        const typing = typeT > 0 && typeT < 1;

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity }}>
            <div style={{
              position: 'absolute', top: 140,
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#8bff8b', opacity: eyeT, fontWeight: 600,
            }}>Step 3 — Fix the step in place</div>

            {/* Inspector panel */}
            <div style={{
              width: 960,
              padding: 28,
              borderRadius: 24,
              border: '1px solid rgba(115,138,171,0.2)',
              background: 'linear-gradient(180deg, rgba(17,21,32,0.9), rgba(10,13,22,0.9))',
              boxShadow: '0 0 0 1px rgba(54,243,255,0.08), 0 30px 80px rgba(2,4,10,0.55)',
              backdropFilter: 'blur(16px)',
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <span style={{ width: 9, height: 9, borderRadius: 999, background: '#8bff8b', boxShadow: '0 0 10px #8bff8b' }}/>
                  <span style={{ color: '#8bff8b', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em' }}>CODER · s2</span>
                  <span style={{ color: '#5d718f', fontSize: 12 }}>· editing prompt</span>
                </div>
                <div style={{ color: '#5d718f', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Unsaved · Local fork</div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
                {/* Original */}
                <div>
                  <div style={{ fontSize: 11, color: '#5d718f', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8 }}>Original</div>
                  <div style={{
                    padding: '14px 16px',
                    borderRadius: 14,
                    background: 'rgba(4,8,14,0.88)',
                    border: '1px solid rgba(255,112,112,0.3)',
                    color: '#a7b8d1',
                    fontSize: 13, lineHeight: 1.7,
                    minHeight: 140,
                  }}>
                    {oldPrompt}
                  </div>
                </div>
                {/* Edited */}
                <div>
                  <div style={{ fontSize: 11, color: '#8bff8b', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8 }}>Edited</div>
                  <div style={{
                    padding: '14px 16px',
                    borderRadius: 14,
                    background: 'rgba(6,16,10,0.88)',
                    border: '1px solid rgba(139,255,139,0.55)',
                    boxShadow: '0 0 0 1px rgba(139,255,139,0.25), 0 0 24px rgba(139,255,139,0.15)',
                    color: '#f2f7ff',
                    fontSize: 13, lineHeight: 1.7,
                    minHeight: 140,
                  }}>
                    {shown}{typing && <span style={{ color: '#8bff8b' }}>▌</span>}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 20, gap: 12 }}>
                <div style={{
                  padding: '10px 22px',
                  borderRadius: 12,
                  border: '1px solid rgba(139,255,139,0.6)',
                  background: typeT > 0.9 ? 'linear-gradient(180deg, rgba(56,243,255,0.2), rgba(139,255,139,0.2))' : 'rgba(14,22,16,0.8)',
                  color: typeT > 0.9 ? '#f2f7ff' : '#8bff8b',
                  fontSize: 12, fontWeight: 700, letterSpacing: '0.08em',
                  boxShadow: typeT > 0.9 ? '0 0 24px rgba(139,255,139,0.4)' : 'none',
                  transition: 'all 300ms',
                }}>
                  TRY FIX FROM HERE →
                </div>
              </div>
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

window.Scene6Contradictions = Scene6Contradictions;
window.Scene7Edit = Scene7Edit;
