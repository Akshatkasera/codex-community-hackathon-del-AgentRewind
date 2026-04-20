// Scene 8 — Replay branch animation
// Scene 9 — Before/after compare
// Scene 10 — Final product close
// 35.5 – 52.0s
const { Sprite, useSprite, Easing, interpolate, animate, clamp } = window;

function Scene8Replay() {
  return (
    <Sprite start={35.5} end={41.5}>
      {({ localTime }) => {
        const fadeIn = clamp(localTime / 0.4, 0, 1);
        const fadeOut = clamp((localTime - 5.4) / 0.6, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        const eyeT = clamp((localTime - 0.1) / 0.4, 0, 1);

        // Original steps stay left — dim after 0.8s
        const dimT = clamp((localTime - 0.8) / 0.5, 0, 1);
        // Fork branches right, steps cascade from 1.0s
        const forkStart = 1.0;

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity }}>
            <div style={{
              position: 'absolute', top: 140,
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#8bff8b', opacity: eyeT, fontWeight: 600,
            }}>Step 4 — Replay from the fix</div>

            <div style={{ position: 'relative', width: 1200, height: 680 }}>
              {/* Original branch */}
              <div style={{ position: 'absolute', left: 40, top: 40, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {FILM_STEPS.map((s, i) => (
                  <div key={s.id} style={{ opacity: (i < 2 ? 1 : (1 - dimT * 0.7)) }}>
                    <StepCard step={s} dim={i >= 2 && dimT > 0.5} />
                  </div>
                ))}
              </div>

              {/* Fork separator line */}
              <svg style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} width="1200" height="680">
                <path
                  d="M 400 130 Q 560 130, 620 240 L 740 240"
                  stroke="#8bff8b"
                  strokeWidth="2"
                  fill="none"
                  strokeDasharray="400"
                  strokeDashoffset={(1 - clamp((localTime - 0.8) / 0.8, 0, 1)) * 400}
                  style={{ filter: 'drop-shadow(0 0 8px rgba(139,255,139,0.8))' }}
                />
              </svg>

              {/* Fork label */}
              {localTime > 1.3 && (
                <div style={{
                  position: 'absolute', left: 540, top: 180,
                  fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase',
                  color: '#8bff8b', fontWeight: 700,
                  opacity: clamp((localTime - 1.3) / 0.3, 0, 1),
                  background: 'rgba(14,22,16,0.9)',
                  padding: '4px 10px', borderRadius: 8,
                  border: '1px solid rgba(139,255,139,0.4)',
                }}>fork · from s2</div>
              )}

              {/* New branch */}
              <div style={{ position: 'absolute', right: 40, top: 220, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {FILM_STEPS.slice(1).map((s, i) => {
                  const cardT = clamp((localTime - forkStart - 0.3 - i * 0.35) / 0.45, 0, 1);
                  const eased = Easing.easeOutCubic(cardT);
                  const forked = { ...s, id: 'f' + (i + 2), color: '#8bff8b' };
                  return (
                    <div key={s.id} style={{
                      opacity: eased,
                      transform: `translateX(${(1 - eased) * 40}px)`,
                    }}>
                      <StepCard step={forked} selected={i === 0 && cardT > 0.5} />
                    </div>
                  );
                })}
              </div>

              {/* bottom caption */}
              {localTime > 3.5 && (
                <div style={{
                  position: 'absolute', left: '50%', bottom: -10, transform: 'translateX(-50%)',
                  fontSize: 16, color: '#a7b8d1',
                  opacity: clamp((localTime - 3.5) / 0.5, 0, 1) * (1 - clamp((localTime - 5.2) / 0.4, 0, 1)),
                  fontFamily: "'JetBrains Mono', monospace",
                }}>
                  <span style={{ color: '#5d718f' }}>replay </span>
                  <span style={{ color: '#8bff8b' }}>forward</span>
                  <span style={{ color: '#5d718f' }}> · deterministic · snapshot sealed</span>
                </div>
              )}
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

function Metric({ label, valueFrom, valueTo, t, color, suffix = '', bad = false }) {
  const v = valueFrom + (valueTo - valueFrom) * Easing.easeOutCubic(t);
  const display = Number.isInteger(valueFrom) && Number.isInteger(valueTo) ? Math.round(v) : v.toFixed(2);
  return (
    <div style={{
      padding: '12px 16px',
      borderRadius: 14,
      background: bad ? 'rgba(24,10,12,0.8)' : 'rgba(10,16,20,0.8)',
      border: `1px solid ${color}55`,
      fontFamily: "'JetBrains Mono', monospace",
      minWidth: 140,
    }}>
      <div style={{ fontSize: 10, color: '#5d718f', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, color, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
        {display}{suffix}
      </div>
    </div>
  );
}

function Scene9Compare() {
  return (
    <Sprite start={41.5} end={47.0}>
      {({ localTime }) => {
        const fadeIn = clamp(localTime / 0.4, 0, 1);
        const fadeOut = clamp((localTime - 4.9) / 0.6, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        const eyeT = clamp((localTime - 0.1) / 0.4, 0, 1);

        const metricT = clamp((localTime - 0.9) / 1.6, 0, 1);
        const verdictT = clamp((localTime - 2.5) / 0.6, 0, 1);

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity }}>
            <div style={{
              position: 'absolute', top: 140,
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#36f3ff', opacity: eyeT, fontWeight: 600,
            }}>Compare — before · after</div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40, width: 1400 }}>
              {/* BEFORE */}
              <div style={{
                padding: 32,
                borderRadius: 24,
                border: '1px solid rgba(255,112,112,0.4)',
                background: 'linear-gradient(180deg, rgba(24,10,14,0.9), rgba(10,6,8,0.9))',
                boxShadow: '0 0 40px rgba(255,112,112,0.12)',
                backdropFilter: 'blur(14px)',
              }}>
                <div style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#ff7070', fontWeight: 700, marginBottom: 6 }}>Before</div>
                <div style={{ fontSize: 24, color: '#f2f7ff', fontWeight: 600, marginBottom: 22, letterSpacing: '-0.02em' }}>Original run</div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  <Metric label="Tests passing" valueFrom={0} valueTo={3} t={metricT} color="#ff7070" suffix="/8" bad/>
                  <Metric label="Hallucinations" valueFrom={0} valueTo={2} t={metricT} color="#ff7070" bad/>
                  <Metric label="Confidence" valueFrom={0} valueTo={0.34} t={metricT} color="#ff7070" bad/>
                </div>
                {verdictT > 0 && (
                  <div style={{
                    marginTop: 22,
                    padding: '10px 16px',
                    borderRadius: 999,
                    background: 'rgba(40,14,18,0.9)',
                    border: '1px solid #ff7070',
                    color: '#ff7070',
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                    display: 'inline-block',
                    opacity: verdictT,
                    boxShadow: '0 0 16px rgba(255,112,112,0.3)',
                  }}>× Still needs work</div>
                )}
              </div>

              {/* AFTER */}
              <div style={{
                padding: 32,
                borderRadius: 24,
                border: '1px solid rgba(139,255,139,0.55)',
                background: 'linear-gradient(180deg, rgba(10,24,14,0.9), rgba(6,12,8,0.9))',
                boxShadow: '0 0 60px rgba(139,255,139,0.18)',
                backdropFilter: 'blur(14px)',
              }}>
                <div style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#8bff8b', fontWeight: 700, marginBottom: 6 }}>After</div>
                <div style={{ fontSize: 24, color: '#f2f7ff', fontWeight: 600, marginBottom: 22, letterSpacing: '-0.02em' }}>Forked run</div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  <Metric label="Tests passing" valueFrom={3} valueTo={8} t={metricT} color="#8bff8b" suffix="/8"/>
                  <Metric label="Hallucinations" valueFrom={2} valueTo={0} t={metricT} color="#8bff8b"/>
                  <Metric label="Confidence" valueFrom={0.34} valueTo={0.94} t={metricT} color="#8bff8b"/>
                </div>
                {verdictT > 0 && (
                  <div style={{
                    marginTop: 22,
                    padding: '10px 16px',
                    borderRadius: 999,
                    background: 'rgba(14,32,18,0.9)',
                    border: '1px solid #8bff8b',
                    color: '#8bff8b',
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                    display: 'inline-block',
                    opacity: verdictT,
                    boxShadow: '0 0 24px rgba(139,255,139,0.4)',
                  }}>✓ Fix looks better</div>
                )}
              </div>
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

function Scene10Close() {
  return (
    <Sprite start={47.0} end={52.0}>
      {({ localTime }) => {
        const fadeIn = clamp(localTime / 0.8, 0, 1);
        const fadeOut = clamp((localTime - 4.6) / 0.4, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        const logoT = Easing.easeOutCubic(clamp(localTime / 1.2, 0, 1));
        const wordmarkT = clamp((localTime - 0.9) / 0.8, 0, 1);
        const taglineT = clamp((localTime - 1.6) / 0.7, 0, 1);
        const stepsT = clamp((localTime - 2.4) / 0.9, 0, 1);

        return (
          <div style={{
            position: 'absolute', inset: 0,
            background: '#03050a',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            opacity,
          }}>
            {/* soft glow */}
            <div style={{
              position: 'absolute', left: '50%', top: '50%',
              width: 1400, height: 1400,
              transform: 'translate(-50%, -50%)',
              background: 'radial-gradient(circle, rgba(54,243,255,0.15), transparent 55%)',
              pointerEvents: 'none',
              opacity: logoT,
            }}/>

            <div style={{
              opacity: logoT,
              transform: `scale(${0.7 + 0.3 * logoT}) rotate(${localTime * 6}deg)`,
              marginBottom: 32,
            }}>
              <LogoMark size={160} glow={1.1} />
            </div>

            <div style={{
              opacity: wordmarkT,
              transform: `translateY(${(1 - wordmarkT) * 12}px)`,
              fontSize: 72, fontWeight: 700, letterSpacing: '-0.05em',
              color: '#f2f7ff',
              textShadow: '0 0 30px rgba(54,243,255,0.4)',
            }}>AgentRewind</div>

            <div style={{
              opacity: taglineT,
              transform: `translateY(${(1 - taglineT) * 10}px)`,
              marginTop: 14,
              fontSize: 22, color: '#a7b8d1', letterSpacing: '-0.01em',
              fontWeight: 400,
            }}>Debug broken AI multi-agent runs.</div>

            <div style={{
              opacity: stepsT,
              transform: `translateY(${(1 - stepsT) * 8}px)`,
              marginTop: 36,
              display: 'flex', gap: 32,
              fontSize: 14, letterSpacing: '0.28em', textTransform: 'uppercase',
              color: '#36f3ff', fontWeight: 600,
            }}>
              <span>Upload</span>
              <span style={{ color: '#5d718f' }}>·</span>
              <span>Diagnose</span>
              <span style={{ color: '#5d718f' }}>·</span>
              <span>Replay</span>
              <span style={{ color: '#5d718f' }}>·</span>
              <span>Compare</span>
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

window.Scene8Replay = Scene8Replay;
window.Scene9Compare = Scene9Compare;
window.Scene10Close = Scene10Close;
