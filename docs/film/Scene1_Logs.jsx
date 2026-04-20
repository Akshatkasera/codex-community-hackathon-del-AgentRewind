// Scene 1 — Cluttered logs / confusing traces
// 0.0 – 5.5s
const { Sprite, useSprite, Easing, interpolate, animate, clamp } = window;

const LOG_LEVELS = [
  { tag: 'INFO',  color: '#a7b8d1' },
  { tag: 'DEBUG', color: '#5d718f' },
  { tag: 'WARN',  color: '#ffe45e' },
  { tag: 'ERROR', color: '#ff7070' },
  { tag: 'TRACE', color: '#36f3ff' },
];

const AGENTS = ['planner', 'coder', 'tester', 'reviewer', 'editor', 'indexer'];

function hashStr(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return Math.abs(h); }

function genLogLine(i) {
  const levelIdx = hashStr('l' + i) % LOG_LEVELS.length;
  const level = LOG_LEVELS[levelIdx];
  const agent = AGENTS[hashStr('a' + i) % AGENTS.length];
  const ts = `2025-11-08T14:${String(22 + (i % 30)).padStart(2,'0')}:${String((i*7) % 60).padStart(2,'0')}.${String((i*137) % 1000).padStart(3,'0')}Z`;
  const traceId = (hashStr('t' + Math.floor(i/6))).toString(16).slice(0, 8);
  const spanId = (hashStr('s' + i)).toString(16).slice(0, 6);
  const messages = [
    `invoke_tool("read_file", path="src/index.ts")`,
    `memory.write(key="prev_result", bytes=2148)`,
    `llm.request model="sonnet-4.5" tokens=12483`,
    `handoff ${agent} -> coder ctx=prev_result`,
    `timeout(30s) exceeded — retrying (2/3)`,
    `unexpected schema: expected Array got Object at $.steps[4].output`,
    `tool_call:redis.memorize() — method not found on client`,
    `ctx_window used=84% (168,400/200,000)`,
    `retry backoff=1.2s reason=rate_limit`,
    `plan.revise() — step_4 contradicts step_2.output`,
    `state.hash=${spanId} drift from t-1 (${(hashStr('d'+i)%90+10)}%)`,
    `embedding.search k=8 latency=412ms`,
  ];
  const msg = messages[hashStr('m' + i) % messages.length];
  return { ts, level, agent, traceId, spanId, msg };
}

function ScrollingLogs({ speed = 260, rowH = 24, rows = 48 }) {
  const { localTime, duration, progress } = useSprite();
  const offset = localTime * speed;
  const scale = 1 + progress * 0.05;
  const brightness = interpolate([0, 0.1, 0.85, 1], [0, 1, 1, 0.15], Easing.easeInOutCubic)(progress);

  const items = [];
  for (let i = 0; i < rows; i++) {
    const line = genLogLine(i);
    const y = i * rowH - (offset % rowH);
    items.push(
      <div key={i} style={{
        position: 'absolute', left: 0, right: 0, top: y,
        height: rowH,
        display: 'grid',
        gridTemplateColumns: '180px 70px 90px 120px 90px 1fr',
        gap: 18,
        padding: '0 36px',
        alignItems: 'center',
        fontSize: 13,
        fontFamily: "'JetBrains Mono', monospace",
        whiteSpace: 'nowrap',
        opacity: 0.55 + ((i % 5) === 0 ? 0.25 : 0),
      }}>
        <span style={{ color: '#5d718f' }}>{line.ts}</span>
        <span style={{ color: line.level.color, fontWeight: 700 }}>{line.level.tag}</span>
        <span style={{ color: '#a7b8d1' }}>{line.agent}</span>
        <span style={{ color: '#5d718f' }}>trace={line.traceId}</span>
        <span style={{ color: '#5d718f' }}>span={line.spanId}</span>
        <span style={{ color: '#a7b8d1', overflow: 'hidden', textOverflow: 'ellipsis' }}>{line.msg}</span>
      </div>
    );
  }

  return (
    <div style={{
      position: 'absolute', inset: 0,
      transform: `scale(${scale})`,
      transformOrigin: '50% 50%',
      filter: `brightness(${brightness})`,
      overflow: 'hidden',
    }}>
      {items}
      {/* second column offset - makes it feel cluttered */}
      <div style={{
        position: 'absolute', inset: 0,
        opacity: 0.25,
        transform: 'translateX(40%) translateY(13%) rotate(-1.5deg)',
        pointerEvents: 'none',
      }}>
        {items.map((item, i) => React.cloneElement(item, { key: 'g'+i }))}
      </div>
    </div>
  );
}

// Minimal-line reveal with fade/swap. Each line is a beat.
function Beat({ text, appearAt, holdDur, color = '#f2f7ff', local, italic = false, strike = false }) {
  const dt = local - appearAt;
  if (dt < -0.1 || dt > holdDur + 0.6) return null;
  const inT = clamp(dt / 0.35, 0, 1);
  const outT = clamp((dt - holdDur) / 0.5, 0, 1);
  const opacity = Easing.easeOutCubic(inT) * (1 - Easing.easeInCubic(outT));
  const ty = (1 - inT) * 8 - outT * 4;
  return (
    <div style={{
      fontSize: 56, fontWeight: 500, color,
      letterSpacing: '-0.035em', lineHeight: 1.1,
      fontFamily: "'JetBrains Mono', monospace",
      fontStyle: italic ? 'italic' : 'normal',
      textDecoration: strike ? 'line-through' : 'none',
      textDecorationColor: 'rgba(255,112,112,0.7)',
      opacity, transform: `translateY(${ty}px)`,
      whiteSpace: 'nowrap',
    }}>{text}</div>
  );
}

function Scene1Logs() {
  // Scene runs 0.0 – 9.0s. Four lines, each a beat, each strips more context.
  return (
    <Sprite start={0} end={9.0}>
      {({ localTime }) => {
        const fadeIn = Math.min(1, localTime / 0.5);
        const fadeOut = Math.max(0, 1 - Math.max(0, localTime - 8.3) / 0.7);
        const opacity = fadeIn * fadeOut;

        // Logs brightness drops as lines progress (visual stripping-away)
        const stripT = interpolate(
          [0, 1.5, 4.0, 6.0, 8.2],
          [1, 0.9, 0.55, 0.22, 0.05],
          Easing.easeInOutCubic
        )(localTime);

        // Vignette tightens with each beat
        const vignetteTight = interpolate(
          [0, 2.0, 5.0, 7.5],
          [0.78, 0.68, 0.52, 0.32],
          Easing.easeInOutCubic
        )(localTime);

        return (
          <div style={{ position: 'absolute', inset: 0, opacity }}>
            <div style={{ position: 'absolute', inset: 0, opacity: stripT, filter: `saturate(${0.4 + 0.6 * stripT})` }}>
              <ScrollingLogs />
            </div>
            {/* vignette darkening — tightens each beat */}
            <div style={{
              position: 'absolute', inset: 0,
              background: `radial-gradient(ellipse at 50% 50%, transparent ${vignetteTight * 25}%, rgba(4,6,10,0.94) ${vignetteTight * 100}%)`,
              pointerEvents: 'none',
            }} />
            {/* Beat stack — four minimal lines */}
            <div style={{
              position: 'absolute', left: '50%', top: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 8,
            }}>
              <Beat text="You can see the run."   appearAt={0.9} holdDur={1.3} color="#f2f7ff" local={localTime} />
              <Beat text="But not the failure."   appearAt={2.8} holdDur={1.3} color="#a7b8d1" local={localTime} />
              <Beat text="Not the cause."         appearAt={4.7} holdDur={1.3} color="#7a8aa6" local={localTime} />
              <Beat text="Not the fix."           appearAt={6.6} holdDur={1.6} color="#5d718f" italic local={localTime} />
            </div>
          </div>
        );
      }}
    </Sprite>
  );
}

window.Scene1Logs = Scene1Logs;
