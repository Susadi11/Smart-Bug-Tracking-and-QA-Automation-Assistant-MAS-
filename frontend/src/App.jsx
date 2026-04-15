import { useState } from 'react'
import './App.css'

const MODELS = [
  { id: 'llama3:8b',    label: 'Llama 3 8B',      ram: '8GB',  speed: 'Balanced',  tag: 'Recommended' },
  { id: 'phi3',         label: 'Phi-3 Mini',       ram: '4GB',  speed: 'Fast',      tag: 'Low RAM' },
  { id: 'phi3:medium',  label: 'Phi-3 Medium',     ram: '8GB',  speed: 'Balanced',  tag: null },
  { id: 'qwen:7b',      label: 'Qwen 7B',          ram: '8GB',  speed: 'Balanced',  tag: null },
  { id: 'qwen:1.8b',    label: 'Qwen 1.8B',        ram: '4GB',  speed: 'Fast',      tag: 'Low RAM' },
  { id: 'mistral',      label: 'Mistral 7B',       ram: '8GB',  speed: 'Balanced',  tag: null },
  { id: 'gemma:2b',     label: 'Gemma 2B',         ram: '4GB',  speed: 'Fast',      tag: 'Low RAM' },
  { id: 'gemma:7b',     label: 'Gemma 7B',         ram: '8GB',  speed: 'Balanced',  tag: null },
  { id: 'codellama',    label: 'CodeLlama 7B',     ram: '8GB',  speed: 'Balanced',  tag: 'Code' },
  { id: 'deepseek-coder:6.7b', label: 'DeepSeek Coder', ram: '8GB', speed: 'Balanced', tag: 'Code' },
  { id: 'llama3:70b',   label: 'Llama 3 70B',      ram: '32GB', speed: 'Slow',      tag: 'High RAM' },
  { id: 'mixtral',      label: 'Mixtral 8x7B',     ram: '32GB', speed: 'Slow',      tag: 'High RAM' },
]

const AGENTS = [
  { key: 'bug_analysis',  label: 'Bug Analyzer',         num: 1, badge: 'badge-1' },
  { key: 'test_cases',    label: 'Test Case Generator',  num: 2, badge: 'badge-2' },
  { key: 'root_causes',   label: 'Root Cause Analyzer',  num: 3, badge: 'badge-3' },
  { key: 'bug_report',    label: 'Bug Report Generator', num: 4, badge: 'badge-4' },
]

const MOCK = {
  bug_analysis: {
    title: 'Login button unresponsive on mobile Safari',
    severity: 'High', priority: 'P1',
    steps: ['Open app on iOS Safari 17', 'Navigate to login screen', 'Enter valid credentials', 'Tap the Login button'],
    expected: 'User is authenticated and redirected to dashboard',
    actual: 'Button tap registers no action — no network request fired',
    components: ['AuthController', 'LoginView', 'TouchEventHandler'],
  },
  test_cases: [
    { id: 'TC-01', type: 'Positive', desc: 'Login with valid credentials on Safari iOS 17' },
    { id: 'TC-02', type: 'Negative', desc: 'Login with invalid password shows clear error' },
    { id: 'TC-03', type: 'Edge',     desc: 'Login button behavior when soft keyboard is open' },
    { id: 'TC-04', type: 'Edge',     desc: 'Double-tap does not trigger duplicate auth requests' },
    { id: 'TC-05', type: 'Negative', desc: 'Empty fields blocked with inline validation' },
    { id: 'TC-06', type: 'Positive', desc: 'Login succeeds after failed attempt with correct credentials' },
  ],
  root_causes: [
    { cause: 'Touch event blocked by overlapping invisible DOM element', likelihood: 'High' },
    { cause: 'CSS pointer-events: none applied incorrectly to button wrapper', likelihood: 'Medium' },
    { cause: 'JavaScript event listener not re-attached after dynamic re-render', likelihood: 'Medium' },
    { cause: 'Safari-specific passive event listener conflict on touch handlers', likelihood: 'Low' },
  ],
  bug_report: `## Bug Report — BUG-2024-0112

**Title:** Login button unresponsive on mobile Safari
**Severity:** High  |  **Priority:** P1
**Reporter:** QA Automation MAS
**Date:** ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}

---

### Summary
The login button on the authentication screen is non-functional when accessed via iOS Safari 17. Users are unable to sign in, causing a complete service disruption on iOS devices.

### Environment
- **Platform:** iOS 17 / Safari
- **Build:** v2.4.1-prod
- **Affects:** All iOS Safari users

### Steps to Reproduce
1. Open the app on iOS Safari 17
2. Navigate to the login screen
3. Enter valid credentials
4. Tap the Login button

### Expected vs Actual
- **Expected:** Authentication succeeds, user redirected to dashboard
- **Actual:** No response on tap, no network request initiated

### Root Cause (Most Likely)
Touch event propagation blocked by an overlapping invisible DOM element introduced in the v2.4.0 layout refactor.

### Recommended Fix
Inspect z-index stacking context on \`.auth-overlay\` and remove or reposition the blocking layer. Verify touch event listeners are correctly bound post-render.

### Test Coverage Required
TC-01, TC-02, TC-03, TC-04, TC-05, TC-06 must pass before closing.`,
}

function AgentResultCard({ agentKey, data, badge, label, num, visible }) {
  const tc = { Positive: 'tc-pos', Negative: 'tc-neg', Edge: 'tc-edge' }
  const lh = { High: 'lh-high', Medium: 'lh-med', Low: 'lh-low' }

  return (
    <div className={`result-card ${visible ? 'card-visible' : ''}`}>
      <div className="card-head">
        <span className={`a-badge ${badge}`}>Agent {num}</span>
        <h3 className="card-title">{label}</h3>
        {visible && <span className="card-done">✓ Complete</span>}
      </div>

      {!visible && (
        <div className="card-waiting">
          <span className="waiting-dot" /><span className="waiting-dot" /><span className="waiting-dot" />
          <span>Waiting…</span>
        </div>
      )}

      {visible && agentKey === 'bug_analysis' && (
        <div className="card-body">
          <div className="ba-title">{data.title}</div>
          <div className="ba-badges">
            <span className="sev-badge">{data.severity}</span>
            <span className="pri-badge">{data.priority}</span>
          </div>
          <div className="ba-grid">
            <div>
              <div className="blabel">Steps to Reproduce</div>
              <ol className="ba-steps">{data.steps.map((s,i) => <li key={i}>{s}</li>)}</ol>
            </div>
            <div>
              <div className="blabel">Expected</div>
              <p className="ba-text">{data.expected}</p>
              <div className="blabel" style={{marginTop:14}}>Actual</div>
              <p className="ba-text red">{data.actual}</p>
            </div>
          </div>
          <div className="blabel" style={{marginTop:16}}>Affected Components</div>
          <div className="tag-row">{data.components.map(c => <span key={c} className="comp-tag">{c}</span>)}</div>
        </div>
      )}

      {visible && agentKey === 'test_cases' && (
        <div className="card-body">
          {data.map(tc_item => (
            <div key={tc_item.id} className="tc-row">
              <span className="tc-id">{tc_item.id}</span>
              <span className={`tc-type ${tc[tc_item.type]}`}>{tc_item.type}</span>
              <span className="tc-desc">{tc_item.desc}</span>
            </div>
          ))}
        </div>
      )}

      {visible && agentKey === 'root_causes' && (
        <div className="card-body">
          {data.map((rc, i) => (
            <div key={i} className="rc-row">
              <span className={`rc-lh ${lh[rc.likelihood]}`}>{rc.likelihood}</span>
              <span className="rc-cause">{rc.cause}</span>
            </div>
          ))}
        </div>
      )}

      {visible && agentKey === 'bug_report' && (
        <div className="card-body">
          <button className="copy-btn" onClick={() => navigator.clipboard.writeText(data)}>
            Copy Report
          </button>
          <pre className="report-pre">{data}</pre>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [model, setModel] = useState('llama3:8b')
  const [temperature, setTemperature] = useState(0.3)
  const [bugText, setBugText] = useState('')
  const [running, setRunning] = useState(false)
  const [activeAgent, setActiveAgent] = useState(null)
  const [doneAgents, setDoneAgents] = useState([])
  const [revealed, setRevealed] = useState({})
  const [started, setStarted] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!bugText.trim() || running) return
    setStarted(true)
    setRunning(true)
    setDoneAgents([])
    setRevealed({})
    setActiveAgent(null)

    for (const agent of AGENTS) {
      setActiveAgent(agent.key)
      await new Promise(r => setTimeout(r, 1400 + Math.random() * 800))
      setDoneAgents(prev => [...prev, agent.key])
      setRevealed(prev => ({ ...prev, [agent.key]: true }))
    }
    setActiveAgent(null)
    setRunning(false)
  }

  const selectedModel = MODELS.find(m => m.id === model)

  return (
    <div className="app">
      <header className="header">
        <div className="hlogo">
          <span className="hlogo-icon">⬡</span>
          <span className="hlogo-name">BugMAS</span>
          <span className="hlogo-sep" />
          <span className="hlogo-sub">Smart Bug Tracking &amp; QA Automation</span>
        </div>
        <div className="hright">
          <span className="hstatus">
            <span className="hstatus-dot" />
            Ollama Local
          </span>
        </div>
      </header>

      <div className="page">
        {/* ── LEFT PANEL ── */}
        <aside className="left-panel">
          <section className="panel-card">
            <div className="panel-title">Model</div>
            <div className="model-list">
              {MODELS.map(m => (
                <button
                  key={m.id}
                  className={`model-item ${model === m.id ? 'model-selected' : ''}`}
                  onClick={() => setModel(m.id)}
                  disabled={running}
                >
                  <div className="mi-top">
                    <span className="mi-name">{m.label}</span>
                    {m.tag && (
                      <span className={`mi-tag ${
                        m.tag === 'Recommended' ? 'tag-blue' :
                        m.tag === 'Low RAM' ? 'tag-green' :
                        m.tag === 'Code' ? 'tag-purple' :
                        'tag-orange'
                      }`}>{m.tag}</span>
                    )}
                  </div>
                  <div className="mi-meta">
                    <span>{m.ram} RAM</span>
                    <span className="mi-dot">·</span>
                    <span>{m.speed}</span>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-title">Parameters</div>
            <div className="param-row">
              <label className="param-label">
                Temperature
                <span className="param-val">{temperature}</span>
              </label>
              <input
                type="range" min="0" max="1" step="0.1"
                value={temperature}
                onChange={e => setTemperature(parseFloat(e.target.value))}
                className="slider"
                disabled={running}
              />
              <div className="slider-hints">
                <span>Precise</span><span>Creative</span>
              </div>
            </div>
            <div className="param-row" style={{marginTop:14}}>
              <label className="param-label">Selected Model</label>
              <div className="param-info">
                <span className="pi-name">{selectedModel?.label}</span>
                <span className="pi-ram">{selectedModel?.ram} RAM required</span>
              </div>
            </div>
          </section>

          <section className="panel-card pipeline-card">
            <div className="panel-title">Agent Pipeline</div>
            <div className="pipeline-steps">
              {AGENTS.map((agent) => {
                const isDone = doneAgents.includes(agent.key)
                const isActive = activeAgent === agent.key
                return (
                  <div key={agent.key} className={`ps-row ${isDone ? 'ps-done' : ''} ${isActive ? 'ps-active' : ''}`}>
                    <div className="ps-icon">
                      {isDone ? <span className="ps-check">✓</span>
                        : isActive ? <span className="ps-pulse" />
                        : <span className="ps-num">{agent.num}</span>}
                    </div>
                    <div className="ps-info">
                      <span className="ps-name">{agent.label}</span>
                      <span className="ps-status">
                        {isDone ? 'Complete' : isActive ? 'Processing…' : 'Queued'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        </aside>

        {/* ── MAIN CONTENT ── */}
        <main className="content">
          <section className="input-card">
            <div className="input-card-head">
              <div>
                <div className="panel-title">Bug Description</div>
                <p className="input-hint">Describe the bug in natural language — Agent 1 will analyze and extract structured details</p>
              </div>
            </div>
            <form onSubmit={handleSubmit}>
              <textarea
                className="bug-textarea"
                placeholder="e.g. When a user taps the login button on Safari iOS 17, nothing happens. No error appears and no network request is made. The same flow works correctly on Chrome desktop and Android. This started occurring after the v2.4.0 release last Tuesday."
                value={bugText}
                onChange={e => setBugText(e.target.value)}
                rows={6}
                disabled={running}
              />
              <div className="input-foot">
                <span className="char-count">{bugText.length} characters</span>
                <button type="submit" className="run-btn" disabled={running || !bugText.trim()}>
                  {running ? (
                    <><span className="btn-spinner" /> Analyzing with {selectedModel?.label}…</>
                  ) : (
                    <><span className="btn-arrow">→</span> Run Analysis</>
                  )}
                </button>
              </div>
            </form>
          </section>

          {started && (
            <div className="results-area">
              {AGENTS.map(agent => (
                <AgentResultCard
                  key={agent.key}
                  agentKey={agent.key}
                  data={MOCK[agent.key]}
                  badge={agent.badge}
                  label={agent.label}
                  num={agent.num}
                  visible={!!revealed[agent.key]}
                />
              ))}
            </div>
          )}
        </main>
      </div>

      <footer className="footer">
        SE4010 CTSE Assignment 2 · Smart Bug Tracking &amp; QA Automation MAS · Powered by Ollama + LangGraph · Zero Cloud Cost
      </footer>
    </div>
  )
}
