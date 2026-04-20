// Scene 4 — Trace upload + Scene 5 — Root-cause diagnosis
// 13.5 – 24.5s
const { Sprite, useSprite, Easing, interpolate, animate, clamp } = window;

const FILM_STEPS = [
  { id: 's1', agent: 'Planner',  color: '#36f3ff', label: 'Plan repo audit' },
  { id: 's2', agent: 'Coder',    color: '#8bff8b', label: 'Implement cache layer' },
  { id: 's3', agent: 'Tester',   color: '#ffe45e', label: 'Run unit tests' },
  { id: 's4', agent: 'Reviewer', color: '#ff63f8', label: 'Review PR diff' },
  { id: 's5', agent: 'Editor',   color: '#ff9d42', label: 'Finalize output' },
];

function StepCard({ step, selected, broken, dim, scale = 1, show = 1 }) {
  let border = 'rgba(115,138,171,0.24)';
  let glow = 'none';
  if (selected) { border = 'rgba(54,243,255,0.75)'; glow = '0 0 0 1px rgba(54,243,255,0.8), 0 0 28px rgba(54,243,255,0.28)'; }
  if (broken)   { border = 'rgba(255,112,112,0.75)'; glow = '0 0 0 1px rgba(255,112,112,0.8), 0 0 36px rgba(255,112,112,0.38)'; }

  return (
    <div style={{
      width: 360,
      padding: '14px 18px',
      borderRadius: 16,
      border: `1px solid ${border}`,
      background: 'linear-gradient(180deg, rgba(17,21,32,0.92), rgba(10,13,22,0.92))',
      boxShadow: glow,
      opacity: (dim ? 0.35 : 1) * show,
      transform: `scale(${scale})`,
      transformOrigin: 'left center',
      transition: 'none',
      backdropFilter: 'blur(14px)',
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <span style={{
          width: 9, height: 9, borderRadius: 999,
          background: step.color,
          boxShadow: `0 0 10px ${step.color}`,
        }}/>
        <span style={{ color: step.color, fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{step.agent}</span>
        <span style={{ color: '#5d718f', fontSize: 12, marginLeft: 'auto' }}>{step.id}</span>
      </div>
      <div style={{ color: '#f2f7ff', fontSize: 15, fontWeight: 500, letterSpacing: '-0.01em' }}>
        {step.label}
      </div>
    </div>
  );
}
window.StepCard = StepCard;
window.FILM_STEPS = FILM_STEPS;

function Scene4Upload() {
  return (
    <Sprite start={13.5} end={18.5}>
      {({ localTime, progress }) => {
        // File drops in from top
        const fileIn = Easing.easeOutCubic(clamp(localTime / 0.9, 0, 1));
        const fileY = -200 + fileIn * 200;
        const fileOp = fileIn;
        // file dissolves at 1.3s
        const fileDissolve = clamp((localTime - 1.3) / 0.5, 0, 1);
        // steps cascade from 1.5s
        const stepStart = 1.6;
        // fadeout
        const fadeOut = clamp((localTime - 4.4) / 0.6, 0, 1);

        // eyebrow
        const eyeT = clamp((localTime - 0.3) / 0.4, 0, 1);

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: 1 - fadeOut }}>
            {/* eyebrow */}
            <div style={{
              position: 'absolute', top: 140,
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#36f3ff', opacity: eyeT, fontWeight: 600,
            }}>Step 1 — Upload a run</div>

            {/* the .json file icon */}
            <div style={{
              position: 'absolute',
              left: '50%', top: '50%',
              transform: `translate(-50%, calc(-50% + ${fileY - 240}px)) scale(${1 - fileDissolve * 0.3})`,
              opacity: fileOp * (1 - fileDissolve),
            }}>
              <div style={{
                width: 180, height: 220,
                background: 'linear-gradient(180deg, rgba(17,21,32,0.96), rgba(10,13,22,0.96))',
                border: '1px solid rgba(54,243,255,0.5)',
                borderRadius: 10,
                boxShadow: '0 0 0 1px rgba(54,243,255,0.3), 0 0 40px rgba(54,243,255,0.25)',
                padding: 20,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
                color: '#5d718f',
                lineHeight: 1.5,
                overflow: 'hidden',
                position: 'relative',
              }}>
                <div style={{ color: '#36f3ff', fontSize: 11, fontWeight: 700, marginBottom: 14, letterSpacing: '0.1em' }}>TRACE.JSON</div>
                <div>{'{'}</div>
                <div>&nbsp;&nbsp;"trace_id": "4a8f...",</div>
                <div>&nbsp;&nbsp;"steps": [</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;{'{'} "agent":</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"planner" {'}'},</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;{'{'} "agent":</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"coder" {'}'},</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;...</div>
                <div>&nbsp;&nbsp;]</div>
                <div>{'}'}</div>
              </div>
            </div>

            {/* Timeline slot (importer target) */}
            <div style={{
              display: 'flex', flexDirection: 'column', gap: 14,
              marginTop: 60,
            }}>
              {FILM_STEPS.map((s, i) => {
                const cardT = clamp((localTime - stepStart - i * 0.22) / 0.5, 0, 1);
                const eased = Easing.easeOutCubic(cardT);
                return (
                  <div key={s.id} style={{
                    opacity: eased,
                    transform: `translateX(${(1 - eased) * -40}px)`,
                  }}>
                    <StepCard step={s} />
                  </div>
                );
              })}
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

function DiagnosisBox({ typeT }) {
  const full = 'The Coder in step s2 fabricated a Redis method that does not exist anywhere in the repository. Downstream tests passed against the hallucinated interface — masking the bug.';
  const visible = full.slice(0, Math.floor(typeT * full.length));
  const typing = typeT > 0 && typeT < 1;

  return (
    <div style={{
      width: 560,
      padding: '20px 22px',
      borderRadius: 20,
      border: '1px solid rgba(255,112,112,0.55)',
      background: 'linear-gradient(180deg, rgba(32,14,18,0.92), rgba(14,8,10,0.92))',
      boxShadow: '0 0 0 1px rgba(255,112,112,0.4), 0 0 48px rgba(255,112,112,0.22)',
      fontFamily: "'JetBrains Mono', monospace",
      backdropFilter: 'blur(14px)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
        fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: 999, background: '#ff7070', boxShadow: '0 0 10px #ff7070' }}/>
        <span style={{ color: '#ff7070', fontWeight: 700 }}>Problem step — Hallucination</span>
        <span style={{ color: '#5d718f', marginLeft: 'auto' }}>s2 | high | 0.66</span>
      </div>
      <div style={{ color: '#f2f7ff', fontSize: 14, lineHeight: 1.6, minHeight: 100 }}>
        {visible}{typing && <span style={{ color: '#ff7070' }}>▌</span>}
      </div>
    </div>
  );
}

function Scene5Diagnosis() {
  return (
    <Sprite start={18.5} end={24.5}>
      {({ localTime, progress }) => {
        const fadeIn = clamp(localTime / 0.5, 0, 1);
        const fadeOut = clamp((localTime - 5.4) / 0.6, 0, 1);
        const opacity = fadeIn * (1 - fadeOut);

        // Scan pass: a cyan bar moves down the step list 0.2→1.6s
        const scanT = clamp((localTime - 0.2) / 1.6, 0, 1);
        const scanY = scanT * 520;

        // s2 pulses red from 1.8s
        const pulseOn = localTime > 1.8;
        const pulseT = pulseOn ? (Math.sin((localTime - 1.8) * 4) * 0.5 + 0.5) : 0;

        // diagnosis box types from 2.2s
        const typeT = clamp((localTime - 2.4) / 2.6, 0, 1);

        // eyebrow
        const eyeT = clamp((localTime - 0.1) / 0.4, 0, 1);

        return (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 80, opacity }}>
            {/* eyebrow */}
            <div style={{
              position: 'absolute', top: 140, left: '50%', transform: 'translateX(-50%)',
              fontSize: 13, letterSpacing: '0.32em', textTransform: 'uppercase',
              color: '#ff7070', opacity: eyeT, fontWeight: 600,
            }}>Step 2 — Find the broken step</div>

            {/* Steps column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'relative' }}>
              {FILM_STEPS.map((s, i) => (
                <StepCard key={s.id}
                  step={s}
                  broken={s.id === 's2' && pulseOn}
                  scale={s.id === 's2' && pulseOn ? 1.0 + pulseT * 0.02 : 1}
                />
              ))}
              {/* scan bar */}
              {scanT < 1 && (
                <div style={{
                  position: 'absolute', left: -20, right: -20, top: scanY,
                  height: 3,
                  background: 'linear-gradient(90deg, transparent, #36f3ff, transparent)',
                  boxShadow: '0 0 24px #36f3ff',
                  filter: 'blur(0.5px)',
                }}/>
              )}
            </div>

            {/* Diagnosis */}
            <div style={{ opacity: typeT > 0 ? 1 : 0, transform: `translateX(${(1 - Math.min(1, typeT * 3)) * 40}px)` }}>
              <DiagnosisBox typeT={typeT} />
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

window.Scene4Upload = Scene4Upload;
window.Scene5Diagnosis = Scene5Diagnosis;
