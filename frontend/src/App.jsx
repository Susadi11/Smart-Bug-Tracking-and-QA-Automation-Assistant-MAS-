import { useState } from 'react'
import './App.css'

const MODELS = [
  { id: 'llama3:8b',           label: 'Llama 3 8B',      ram: '8GB',  tag: 'Recommended' },
  { id: 'phi3',                label: 'Phi-3 Mini',       ram: '4GB',  tag: 'Low RAM' },
  { id: 'phi3:medium',         label: 'Phi-3 Medium',     ram: '8GB',  tag: null },
  { id: 'qwen:7b',             label: 'Qwen 7B',          ram: '8GB',  tag: null },
  { id: 'qwen:1.8b',           label: 'Qwen 1.8B',        ram: '4GB',  tag: 'Low RAM' },
  { id: 'mistral',             label: 'Mistral 7B',       ram: '8GB',  tag: null },
  { id: 'gemma:2b',            label: 'Gemma 2B',         ram: '4GB',  tag: 'Low RAM' },
  { id: 'codellama',           label: 'CodeLlama 7B',     ram: '8GB',  tag: 'Code' },
  { id: 'deepseek-coder:6.7b', label: 'DeepSeek Coder',  ram: '8GB',  tag: 'Code' },
]

const CONTEXT_WINDOWS = [
  { id: '2048', label: '2048 — default (recommended)' },
  { id: '4096', label: '4096 — extended' },
  { id: '8192', label: '8192 — large context' },
]

const AGENTS = [
  { key: 'bug_analysis', label: 'Bug Analyzer',         num: 1 },
  { key: 'test_cases',   label: 'Test Case Generator',  num: 2 },
  { key: 'root_causes',  label: 'Root Cause Analyzer',  num: 3 },
  { key: 'bug_report',   label: 'Bug Report Generator', num: 4 },
]

const TABS = [
  { key: 'bug_analysis', label: 'Bug Analysis' },
  { key: 'test_cases',   label: 'Test Cases' },
  { key: 'root_causes',  label: 'Root Causes' },
  { key: 'bug_report',   label: 'Bug Report' },
]

const MOCK = {
  bug_analysis: {
    title: 'Login button unresponsive on mobile Safari',
    severity: 'High', priority: 'P1',
    steps: [
      'Open app on iOS Safari 17',
      'Navigate to login screen',
      'Enter valid credentials',
      'Tap the Login button',
    ],
    expected: 'User is authenticated and redirected to dashboard',
    actual: 'Button tap registers no action — no network request fired',
    components: ['AuthController', 'LoginView', 'TouchEventHandler'],
  },
  test_cases: [
    { id: 'TC-01', type: 'Positive', desc: 'Login with valid credentials on Safari iOS 17' },
    { id: 'TC-02', type: 'Negative', desc: 'Login with invalid password shows clear error message' },
    { id: 'TC-03', type: 'Edge',     desc: 'Login button state when soft keyboard is open' },
    { id: 'TC-04', type: 'Edge',     desc: 'Double-tap does not trigger duplicate auth requests' },
    { id: 'TC-05', type: 'Negative', desc: 'Empty fields blocked with inline validation message' },
    { id: 'TC-06', type: 'Positive', desc: 'Successful login after a previously failed attempt' },
  ],
  root_causes: [
    { cause: 'Touch event blocked by overlapping invisible DOM element', likelihood: 'High' },
    { cause: 'CSS pointer-events: none applied incorrectly to button wrapper', likelihood: 'Medium' },
    { cause: 'JavaScript event listener not re-attached after dynamic re-render', likelihood: 'Medium' },
    { cause: 'Safari-specific passive event listener conflict on touch handlers', likelihood: 'Low' },
  ],
  bug_report: `## Bug Report — BUG-2024-0112

Title    : Login button unresponsive on mobile Safari
Severity : High  |  Priority: P1
Reporter : QA Automation MAS
Date     : ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}

────────────────────────────────────────

SUMMARY
The login button on the authentication screen is non-functional
when accessed via iOS Safari 17. Users are unable to sign in,
causing a complete service disruption on iOS devices.

ENVIRONMENT
  Platform : iOS 17 / Safari
  Build    : v2.4.1-prod
  Scope    : All iOS Safari users

STEPS TO REPRODUCE
  1. Open the app on iOS Safari 17
  2. Navigate to the login screen
  3. Enter valid credentials
  4. Tap the Login button

EXPECTED VS ACTUAL
  Expected : User authenticated and redirected to dashboard
  Actual   : No response on tap, no network request initiated

ROOT CAUSE (MOST LIKELY)
Touch event propagation blocked by an overlapping invisible DOM
element introduced in the v2.4.0 layout refactor.

RECOMMENDED FIX
Inspect z-index stacking context on .auth-overlay and remove or
reposition the blocking layer. Verify touch event listeners are
correctly bound post-render.

TEST COVERAGE REQUIRED
TC-01, TC-02, TC-03, TC-04, TC-05, TC-06 must pass before closing.`,
}

export default function App() {
  const [model, setModel]         = useState('llama3:8b')
  const [ctx, setCtx]             = useState('2048')
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [bugText, setBugText]     = useState('')
  const [running, setRunning]     = useState(false)
  const [progress, setProgress]   = useState(0)
  const [activeAgent, setActive]  = useState(null)
  const [doneAgents, setDone]     = useState([])
  const [revealed, setRevealed]   = useState({})
  const [activeTab, setTab]       = useState('bug_analysis')
  const [started, setStarted]     = useState(false)
  const [warnings, setWarnings]   = useState([])

  async function handleRun(e) {
    e.preventDefault()
    if (!bugText.trim() || running) return
    setStarted(true)
    setRunning(true)
    setDone([])
    setRevealed({})
    setProgress(0)
    setActive(null)
    setWarnings([])
    setTab('bug_analysis')

    for (let i = 0; i < AGENTS.length; i++) {
      const agent  = AGENTS[i]
      setActive(agent.key)
      const pStart = (i / AGENTS.length) * 100
      const pEnd   = ((i + 1) / AGENTS.length) * 100
      for (let s = 0; s <= 24; s++) {
        setProgress(Math.round(pStart + (pEnd - pStart) * (s / 24)))
        await new Promise(r => setTimeout(r, 55 + Math.random() * 25))
      }
      setDone(prev => [...prev, agent.key])
      setRevealed(prev => ({ ...prev, [agent.key]: true }))
      setTab(agent.key)
    }
    setActive(null)
    setProgress(100)
    setWarnings([
      '[BugAnalyzerAgent] Severity inferred from description — please verify manually.',
      '[TestCaseGeneratorAgent] TC-03 may need device-specific validation.',
    ])
    setRunning(false)
  }

  const tcColor = { Positive: 'tc-pos', Negative: 'tc-neg', Edge: 'tc-edge' }
  const lhColor = { High: 'lh-high', Medium: 'lh-med', Low: 'lh-low' }

  return (
    <div className="app">

      {/* ── NAVBAR ─────────────────────────────── */}
      <nav className="navbar">
        <div className="nav-inner">
          <div className="nav-brand">
            <span className="nav-hex">⬡</span>
            <span className="nav-name">BugMAS</span>
            <span className="nav-div" />
            <span className="nav-sub">Smart Bug Tracking &amp; QA Automation</span>
          </div>
          <div className="nav-right">
            <span className="nav-status">
              <span className="ns-dot" />
              Ollama · Local
            </span>
          </div>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────── */}
      <section className="hero">
        <div className="hero-inner">
          <h1 className="hero-h1">
            Smart Bug Tracking<br />
            <span className="hero-dim">&amp; QA Automation.</span>
          </h1>
          <p className="hero-p">
            Describe any bug in plain language. Four specialized AI agents analyze it,
            generate test cases, identify root causes, and produce a professional report.
          </p>
        </div>
      </section>

      {/* ── PAGE ───────────────────────────────── */}
      <div className="page">

        {/* ══ TOP — Input form ══ */}
        <section className="card">
          <div className="card-head-row">
            <span className="card-label">New Pipeline Run</span>
          </div>

          <div className="form-grid">
            {/* Bug description — left */}
            <div className="form-left">
              <label className="fl">Feature Request / Bug Description</label>
              <textarea
                className="textarea"
                rows={7}
                placeholder="Describe the bug in natural language…&#10;&#10;e.g. When a user taps login on Safari iOS 17, nothing happens. No error is shown and no network request is made. The same flow works on Chrome and Android."
                value={bugText}
                onChange={e => setBugText(e.target.value)}
                disabled={running}
              />
            </div>

            {/* Settings — right */}
            <div className="form-right">
              <div className="form-field">
                <label className="fl">Model</label>
                <select className="fselect" value={model} onChange={e => setModel(e.target.value)} disabled={running}>
                  {MODELS.map(m => (
                    <option key={m.id} value={m.id}>
                      {m.label} ({m.ram} RAM){m.tag ? ` · ${m.tag}` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label className="fl">Ollama URL</label>
                <input
                  className="finput"
                  value={ollamaUrl}
                  onChange={e => setOllamaUrl(e.target.value)}
                  disabled={running}
                  placeholder="http://localhost:11434"
                />
              </div>

              <div className="form-field">
                <label className="fl">Context Window (tokens)</label>
                <select className="fselect" value={ctx} onChange={e => setCtx(e.target.value)} disabled={running}>
                  {CONTEXT_WINDOWS.map(c => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
                <p className="fhint">Ensure your model supports the selected context size.</p>
              </div>

              <button className="run-btn" onClick={handleRun} disabled={running || !bugText.trim()}>
                {running
                  ? <><span className="run-spin" /> Pipeline Running…</>
                  : 'Run Pipeline →'}
              </button>
            </div>
          </div>
        </section>

        {/* ══ BOTTOM — Live status ══ */}
        <section className="card">
          <div className="card-head-row">
            <span className="card-label">Live Status</span>
            <span className={`status-pill ${running ? 'sp-run' : started ? 'sp-done' : 'sp-idle'}`}>
              {running ? 'RUNNING' : started ? 'COMPLETE' : 'IDLE'}
            </span>
            <div className="stat-group">
              <div className="stat">
                <span className="sk">PROGRESS</span>
                <span className="sv">{progress}%</span>
              </div>
              <div className="stat">
                <span className="sk">ACTIVE AGENT</span>
                <span className="sv">
                  {activeAgent ? AGENTS.find(a => a.key === activeAgent)?.label : '—'}
                </span>
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="pbar-track">
            <div className="pbar-fill" style={{ width: `${progress}%` }} />
          </div>

          {/* Agent steps */}
          <div className="agent-row">
            {AGENTS.map(agent => {
              const done   = doneAgents.includes(agent.key)
              const active = activeAgent === agent.key
              return (
                <div key={agent.key} className={`astep ${done ? 'as-done' : active ? 'as-active' : ''}`}>
                  <div className="adot">
                    {done   ? <span className="dot-ok"   /> :
                     active ? <span className="dot-spin" /> :
                              <span className="dot-q"    />}
                  </div>
                  <div className="ainfo">
                    <span className="aname">{agent.label}</span>
                    <span className="abadge">
                      {done ? 'COMPLETED' : active ? 'RUNNING' : 'QUEUED'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* ══ RESULTS ══ */}
        {started && (
          <section className="card">
            <div className="card-head-row">
              <span className="card-label">Pipeline Activity</span>
            </div>

            {/* Tabs */}
            <div className="tabs">
              {TABS.map(tab => (
                <button
                  key={tab.key}
                  className={`tab ${activeTab === tab.key ? 'tab-on' : ''} ${!revealed[tab.key] ? 'tab-lock' : ''}`}
                  onClick={() => revealed[tab.key] && setTab(tab.key)}
                >
                  {tab.label}
                  {revealed[tab.key] && <span className="tab-dot" />}
                </button>
              ))}
            </div>

            <div className="tab-body">
              {!revealed[activeTab] && (
                <div className="wait-row">
                  <span className="wd" /><span className="wd" /><span className="wd" />
                  <span>Waiting for agent to complete…</span>
                </div>
              )}

              {revealed[activeTab] && activeTab === 'bug_analysis' && (
                <div className="rb anim-in">
                  <div className="rb-title">{MOCK.bug_analysis.title}</div>
                  <div className="rb-pills">
                    <span className="pill-sev">Severity: {MOCK.bug_analysis.severity}</span>
                    <span className="pill-pri">Priority: {MOCK.bug_analysis.priority}</span>
                  </div>
                  <div className="rb-2col">
                    <div>
                      <div className="rl">Steps to Reproduce</div>
                      <ol className="rsteps">{MOCK.bug_analysis.steps.map((s,i) => <li key={i}>{s}</li>)}</ol>
                    </div>
                    <div>
                      <div className="rl">Expected</div>
                      <p className="rt">{MOCK.bug_analysis.expected}</p>
                      <div className="rl" style={{marginTop:14}}>Actual</div>
                      <p className="rt rt-red">{MOCK.bug_analysis.actual}</p>
                    </div>
                  </div>
                  <div className="rl" style={{marginTop:18}}>Affected Components</div>
                  <div className="rtags">
                    {MOCK.bug_analysis.components.map(c => <span key={c} className="rtag">{c}</span>)}
                  </div>
                </div>
              )}

              {revealed[activeTab] && activeTab === 'test_cases' && (
                <div className="rb anim-in">
                  {MOCK.test_cases.map(tc => (
                    <div key={tc.id} className="tc-row">
                      <span className="tc-id">{tc.id}</span>
                      <span className={`tc-type ${tcColor[tc.type]}`}>{tc.type}</span>
                      <span className="tc-desc">{tc.desc}</span>
                    </div>
                  ))}
                </div>
              )}

              {revealed[activeTab] && activeTab === 'root_causes' && (
                <div className="rb anim-in">
                  {MOCK.root_causes.map((rc, i) => (
                    <div key={i} className="rc-row">
                      <span className={`rc-lh ${lhColor[rc.likelihood]}`}>{rc.likelihood}</span>
                      <span className="rc-txt">{rc.cause}</span>
                    </div>
                  ))}
                </div>
              )}

              {revealed[activeTab] && activeTab === 'bug_report' && (
                <div className="rb anim-in">
                  <button className="copy-btn" onClick={() => navigator.clipboard.writeText(MOCK.bug_report)}>
                    Copy Report
                  </button>
                  <pre className="report-pre">{MOCK.bug_report}</pre>
                </div>
              )}
            </div>

            {warnings.length > 0 && (
              <div className="warns">
                <div className="wt">Errors &amp; Warnings</div>
                {warnings.map((w, i) => <div key={i} className="wr">· {w}</div>)}
              </div>
            )}
          </section>
        )}

      </div>

    </div>
  )
}
