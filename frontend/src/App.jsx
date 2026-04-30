import { useState, useEffect } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const MODELS = [
  { id: 'tinyllama',     label: 'TinyLlama 1.1B',  note: '~600 MB · fastest' },
  { id: 'qwen2:0.5b',   label: 'Qwen2 0.5B',       note: '~350 MB · ultra-light' },
  { id: 'gemma:2b',     label: 'Gemma 2B',          note: '~1.4 GB · lightweight' },
  { id: 'phi3:mini',    label: 'Phi-3 Mini 3.8B',   note: '~2.2 GB · smart & fast' },
  { id: 'mistral:7b',   label: 'Mistral 7B',        note: '~4.1 GB · balanced' },
  { id: 'qwen:7b',      label: 'Qwen 7B',           note: '~4.5 GB · balanced' },
  { id: 'llama3:8b',    label: 'Llama 3 8B',        note: '~4.7 GB · recommended' },
  { id: 'codellama:7b', label: 'Code Llama 7B',     note: '~3.8 GB · code-focused' },
  { id: '__custom__',   label: 'Custom model…',     note: 'enter name manually' },
]

const CONTEXT_WINDOWS = [
  { id: '512',  label: '512' },
  { id: '1024', label: '1024' },
  { id: '2048', label: '2048 — default' },
  { id: '4096', label: '4096 — extended' },
  { id: '8192', label: '8192 — large' },
]

// key = API step key, resultKey = key in API result{}
const AGENTS = [
  { key: 'bug_analyzer',         resultKey: 'bug_analysis', label: 'Bug Analyzer',         num: 1 },
  { key: 'test_case_generator',  resultKey: 'test_cases',   label: 'Test Case Generator',  num: 2 },
  { key: 'root_cause_analyzer',  resultKey: 'root_causes',  label: 'Root Cause Analyzer',  num: 3 },
  { key: 'bug_report_generator', resultKey: 'bug_report',   label: 'Bug Report Generator', num: 4 },
]

const TABS = [
  { key: 'bug_analysis', label: 'Bug Analysis' },
  { key: 'test_cases',   label: 'Test Cases' },
  { key: 'root_causes',  label: 'Root Causes' },
  { key: 'bug_report',   label: 'Bug Report' },
]

const ACTION_VERBS = [
  'click','tap','login','logout','submit','open','close','load','crash','fail',
  'error','navigate','scroll','type','enter','select','upload','download','sign',
  'register','delete','save','update','create','search','filter','sort','render',
  'display','show','hide','redirect','refresh','request','fetch','send','receive',
  'connect','disconnect',
]

function validateBug(text) {
  if (text.trim().length < 30) return 'Description is too short — add more detail (min 30 characters).'
  const lower = text.toLowerCase()
  if (!ACTION_VERBS.some(v => lower.includes(v)))
    return 'No action detected — describe what the user did (e.g. "clicked", "submitted", "opened").'
  return null
}

export default function App() {
  const [model, setModel]           = useState('phi3:mini')
  const [customModel, setCustom]    = useState('')
  const [ctx, setCtx]               = useState('2048')
  const [ollamaUrl, setOllamaUrl]   = useState('http://localhost:11434')
  const [bugText, setBugText]       = useState('')
  const [codeSnippet, setCode]      = useState('')
  const [showCode, setShowCode]     = useState(false)
  const [platform, setPlatform]     = useState('')
  const [appVersion, setAppVersion] = useState('')
  const [severity, setSeverity]     = useState('')
  const [validErr, setValidErr]     = useState(null)
  const [running, setRunning]       = useState(false)
  const [progress, setProgress]     = useState(0)
  const [activeAgent, setActive]    = useState(null)   // step key
  const [doneAgents, setDone]       = useState([])     // step keys
  const [revealed, setRevealed]     = useState({})     // result keys
  const [activeTab, setTab]         = useState('bug_analysis')
  const [started, setStarted]       = useState(false)
  const [result, setResult]         = useState({})
  const [apiErrors, setApiErrors]   = useState([])
  const [submitErr, setSubmitErr]   = useState(null)
  const [expandedTC, setExpandedTC] = useState(null)  // expanded test case id

  // Load default model from backend .env on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/config`, { cache: 'no-store' })
      .then(r => r.json())
      .then(cfg => {
        if (!cfg.default_model) return
        const known = MODELS.find(m => m.id === cfg.default_model)
        if (known && known.id !== '__custom__') {
          setModel(cfg.default_model)
        } else {
          setModel('__custom__')
          setCustom(cfg.default_model)
        }
      })
      .catch(() => {}) // keep phi3:mini if backend unreachable
  }, [])

  function handleBugChange(e) {
    const val = e.target.value
    setBugText(val)
    if (validErr) setValidErr(validateBug(val))
  }

  const effectiveModel = model === '__custom__'
    ? (customModel.trim() || 'phi3:mini')
    : model

  async function handleRun(e) {
    e.preventDefault()
    const err = validateBug(bugText)
    if (err) { setValidErr(err); return }
    setValidErr(null)
    setSubmitErr(null)
    if (running) return

    setStarted(true)
    setRunning(true)
    setDone([])
    setRevealed({})
    setResult({})
    setApiErrors([])
    setProgress(0)
    setActive(null)
    setTab('bug_analysis')
    setExpandedTC(null)

    try {
      const resp = await fetch(`${API_BASE}/api/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({
          bug_description: bugText,
          code_snippet:    codeSnippet.trim() || null,
          platform:        platform  || null,
          app_version:     appVersion || null,
          user_severity:   severity  || null,
          model_name:      effectiveModel,
          ollama_base_url: ollamaUrl,
          num_ctx:         parseInt(ctx),
        }),
      })

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body?.detail?.message || `HTTP ${resp.status}`)
      }

      const { run_id } = await resp.json()
      await pollRun(run_id)

    } catch (exc) {
      setSubmitErr(`Failed to start pipeline: ${exc.message}`)
      setRunning(false)
    }
  }

  async function pollRun(runId) {
    let delay = 1500
    let consecutiveErrors = 0

    while (true) {
      await new Promise(r => setTimeout(r, delay))

      try {
        const resp = await fetch(`${API_BASE}/api/runs/${runId}`, { cache: 'no-store' })
        if (!resp.ok) throw new Error('fetch failed')
        const run = await resp.json()

        // Progress & active agent
        setProgress(run.progress_percent)
        const activeStep = run.steps.find(s => s.status === 'running')
        setActive(activeStep?.key ?? null)

        // Completed step keys
        const done = run.steps.filter(s => s.status === 'completed').map(s => s.key)
        setDone(done)

        // Reveal tabs for all completed agents (even if they have no output yet)
        const newRevealed = {}
        run.steps.forEach(step => {
          if (step.status === 'completed') {
            const agent = AGENTS.find(a => a.key === step.key)
            if (agent) newRevealed[agent.resultKey] = true
          }
        })
        setRevealed(newRevealed)

        // Auto-switch to latest completed tab
        const latestDone = AGENTS.filter(a => done.includes(a.key)).at(-1)
        if (latestDone) setTab(latestDone.resultKey)

        consecutiveErrors = 0
        delay = Math.min(delay * 1.5, 12000)

        if (run.status === 'completed' || run.status === 'failed') {
          setResult(run.result || {})
          setApiErrors(run.errors || [])
          setProgress(100)
          setActive(null)
          setRunning(false)
          break
        }

      } catch {
        consecutiveErrors++
        if (consecutiveErrors >= 5) {
          setSubmitErr('Lost connection to backend after 5 retries.')
          setRunning(false)
          break
        }
      }
    }
  }

  const tcColor = { Positive: 'tc-pos', Negative: 'tc-neg', Edge: 'tc-edge' }
  const lhColor = { High: 'lh-high', Medium: 'lh-med', Low: 'lh-low' }

  const ba = result.bug_analysis
  const tc = result.test_cases
  const rc = result.root_causes
  const br = result.bug_report

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

      <div className="page">

        {/* ══ INPUT FORM ══ */}
        <section className="card">
          <div className="card-head-row">
            <span className="card-label">New Pipeline Run</span>
          </div>

          <div className="form-grid">

            {/* ── LEFT: bug input ── */}
            <div className="form-left">
              <div className="form-field">
                <label className="fl">
                  Bug Description
                  <span className="fl-req">required</span>
                </label>
                <textarea
                  className={`textarea ${validErr ? 'textarea-err' : ''}`}
                  rows={6}
                  placeholder="Describe the bug in natural language…&#10;&#10;e.g. When a user taps the login button on Safari iOS 17, nothing happens. No error is shown and no network request is fired."
                  value={bugText}
                  onChange={handleBugChange}
                  disabled={running}
                />
                {validErr && <p className="field-err">{validErr}</p>}
                <p className="fhint">{bugText.length} chars · min 30 · describe what the user did and what happened</p>
              </div>

              <div className="env-row">
                <div className="form-field">
                  <label className="fl">Platform</label>
                  <select className="fselect" value={platform} onChange={e => setPlatform(e.target.value)} disabled={running}>
                    <option value="">Select…</option>
                    <option>iOS Safari</option>
                    <option>Android Chrome</option>
                    <option>Web — Chrome</option>
                    <option>Web — Firefox</option>
                    <option>Web — Safari</option>
                    <option>Desktop App</option>
                    <option>API / Backend</option>
                    <option>Other</option>
                  </select>
                </div>
                <div className="form-field">
                  <label className="fl">App Version</label>
                  <input
                    className="finput"
                    value={appVersion}
                    onChange={e => setAppVersion(e.target.value)}
                    disabled={running}
                    placeholder="e.g. v2.4.1"
                  />
                </div>
                <div className="form-field">
                  <label className="fl">Severity (guess)</label>
                  <select className="fselect" value={severity} onChange={e => setSeverity(e.target.value)} disabled={running}>
                    <option value="">Unknown</option>
                    <option>Critical</option>
                    <option>High</option>
                    <option>Medium</option>
                    <option>Low</option>
                  </select>
                </div>
              </div>

              <div className="code-section">
                <button type="button" className="code-toggle" onClick={() => setShowCode(p => !p)} disabled={running}>
                  <span className="ct-icon">{showCode ? '▾' : '▸'}</span>
                  Code Snippet
                  <span className="ct-badge">optional — helps Agent 1 &amp; 3</span>
                </button>
                {showCode && (
                  <div className="code-body">
                    <p className="fhint" style={{ marginBottom: 8 }}>
                      Paste the relevant function or component. Agent 1 uses this to identify affected components.
                    </p>
                    <textarea
                      className="code-textarea"
                      rows={8}
                      placeholder="// paste relevant code here"
                      value={codeSnippet}
                      onChange={e => setCode(e.target.value)}
                      disabled={running}
                      spellCheck={false}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* ── RIGHT: settings ── */}
            <div className="form-right">
              <div className="form-field">
                <label className="fl">Model</label>
                <select className="fselect" value={model} onChange={e => setModel(e.target.value)} disabled={running}>
                  {MODELS.map(m => (
                    <option key={m.id} value={m.id}>{m.label} · {m.note}</option>
                  ))}
                </select>
                {model === '__custom__' && (
                  <input
                    className="finput"
                    style={{ marginTop: 6 }}
                    placeholder="e.g. llama3:8b"
                    value={customModel}
                    onChange={e => setCustom(e.target.value)}
                    disabled={running}
                  />
                )}
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

              <div className="input-summary">
                <div className="is-title">Input Summary</div>
                <div className="is-row">
                  <span className="is-k">Description</span>
                  <span className={`is-v ${bugText.trim().length >= 30 ? 'isv-ok' : 'isv-no'}`}>
                    {bugText.trim().length >= 30 ? '✓ Ready' : '✗ Too short'}
                  </span>
                </div>
                <div className="is-row">
                  <span className="is-k">Platform</span>
                  <span className={`is-v ${platform ? 'isv-ok' : 'isv-dim'}`}>{platform || 'Not set'}</span>
                </div>
                <div className="is-row">
                  <span className="is-k">Version</span>
                  <span className={`is-v ${appVersion ? 'isv-ok' : 'isv-dim'}`}>{appVersion || 'Not set'}</span>
                </div>
                <div className="is-row">
                  <span className="is-k">Severity</span>
                  <span className={`is-v ${severity ? 'isv-ok' : 'isv-dim'}`}>{severity || 'Unknown'}</span>
                </div>
                <div className="is-row">
                  <span className="is-k">Code Snippet</span>
                  <span className={`is-v ${codeSnippet.trim() ? 'isv-ok' : 'isv-dim'}`}>
                    {codeSnippet.trim() ? `✓ ${codeSnippet.trim().split('\n').length} lines` : 'None'}
                  </span>
                </div>
              </div>

              {submitErr && <p className="field-err" style={{ marginTop: 8 }}>{submitErr}</p>}

              <button className="run-btn" onClick={handleRun} disabled={running || !bugText.trim()}>
                {running
                  ? <><span className="run-spin" /> Pipeline Running…</>
                  : 'Run Pipeline →'}
              </button>
            </div>
          </div>
        </section>

        {/* ══ LIVE STATUS ══ */}
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

          <div className="pbar-track">
            <div className="pbar-fill" style={{ width: `${progress}%` }} />
          </div>

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

        {/* ══ PIPELINE OUTPUT ══ */}
        {started && (
          <section className="card">
            <div className="card-head-row">
              <span className="card-label">Pipeline Output</span>
            </div>

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

              {/* ── Bug Analysis (Agent 1) ── */}
              {revealed[activeTab] && activeTab === 'bug_analysis' && (
                <div className="rb anim-in">
                  {ba ? (
                    <>
                      <div className="rb-title">{ba.title}</div>
                      <div className="rb-pills">
                        <span className="pill-sev">Severity: {ba.severity}</span>
                        <span className="pill-pri">Priority: {ba.priority}</span>
                      </div>
                      <div className="rb-2col">
                        <div>
                          <div className="rl">Steps to Reproduce</div>
                          <ol className="rsteps">
                            {ba.steps_to_reproduce.map((s, i) => <li key={i}>{s}</li>)}
                          </ol>
                        </div>
                        <div>
                          <div className="rl">Expected</div>
                          <p className="rt">{ba.expected_result}</p>
                          <div className="rl" style={{ marginTop: 14 }}>Actual</div>
                          <p className="rt rt-red">{ba.actual_result}</p>
                        </div>
                      </div>
                      <div className="rl" style={{ marginTop: 18 }}>Affected Components</div>
                      <div className="rtags">
                        {ba.affected_components.map(c => <span key={c} className="rtag">{c}</span>)}
                      </div>
                    </>
                  ) : (
                    <div className="not-impl">Agent 1 produced no output — check backend logs.</div>
                  )}
                </div>
              )}

              {/* ── Test Cases (Agent 2) ── */}
              {revealed[activeTab] && activeTab === 'test_cases' && (
                <div className="rb anim-in">
                  {tc && tc.length > 0 ? (
                    tc.map(t => (
                      <div key={t.id} className={`tc-card ${expandedTC === t.id ? 'tc-expanded' : ''}`}>
                        <div 
                          className="tc-header" 
                          onClick={() => setExpandedTC(expandedTC === t.id ? null : t.id)}
                          style={{ cursor: 'pointer' }}
                        >
                          <span className="tc-expand-icon">{expandedTC === t.id ? '▾' : '▸'}</span>
                          <span className="tc-id">{t.id}</span>
                          <span className={`tc-type ${tcColor[t.type] || ''}`}>{t.type}</span>
                          <span className="tc-desc">{t.description}</span>
                        </div>
                        {expandedTC === t.id && (
                          <div className="tc-details">
                            <div className="tc-metadata">
                              <div className="tcm-row">
                                <span className="tcm-label">Test Case ID:</span>
                                <span className="tcm-value">{t.id}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Test Case Title:</span>
                                <span className="tcm-value">{t.description}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Module:</span>
                                <span className="tcm-value">{t.module}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Sub-module:</span>
                                <span className="tcm-value">{t.submodule}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Priority:</span>
                                <span className="tcm-value tcm-priority">{t.priority}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Severity:</span>
                                <span className="tcm-value tcm-severity">{t.severity}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Test Type:</span>
                                <span className="tcm-value">{t.test_type}</span>
                              </div>
                              <div className="tcm-row">
                                <span className="tcm-label">Created Date:</span>
                                <span className="tcm-value">{t.created_date}</span>
                              </div>
                            </div>
                            <div className="tc-detail-group">
                              <div className="tc-detail-label">Steps:</div>
                              <ol className="tc-steps">
                                {t.steps.map((step, i) => (
                                  <li key={i}>{step}</li>
                                ))}
                              </ol>
                            </div>
                            <div className="tc-detail-group">
                              <div className="tc-detail-label">Expected Result:</div>
                              <p className="tc-expected">{t.expected}</p>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="not-impl">Agent 2 — Test Case Generator not yet implemented.</div>
                  )}
                </div>
              )}

              {/* ── Root Causes (Agent 3) ── */}
              {revealed[activeTab] && activeTab === 'root_causes' && (
                <div className="rb anim-in">
                  {rc && rc.length > 0 ? (
                    rc.map((r, i) => (
                      <div key={i} className="rc-row">
                        <span className={`rc-lh ${lhColor[r.likelihood] || ''}`}>{r.likelihood}</span>
                        <span className="rc-txt">{r.cause}</span>
                      </div>
                    ))
                  ) : (
                    <div className="not-impl">Agent 3 — Root Cause Analyzer not yet implemented.</div>
                  )}
                </div>
              )}

              {/* ── Bug Report (Agent 4) ── */}
              {revealed[activeTab] && activeTab === 'bug_report' && (
                <div className="rb anim-in">
                  {br ? (
                    <>
                      <button className="copy-btn" onClick={() => navigator.clipboard.writeText(br)}>
                        Copy Report
                      </button>
                      <pre className="report-pre">{br}</pre>
                    </>
                  ) : (
                    <div className="not-impl">Agent 4 — Bug Report Generator not yet implemented.</div>
                  )}
                </div>
              )}
            </div>

            {apiErrors.length > 0 && (
              <div className="warns">
                <div className="wt">Errors &amp; Warnings</div>
                {apiErrors.map((w, i) => <div key={i} className="wr">· {w}</div>)}
              </div>
            )}
          </section>
        )}

      </div>
    </div>
  )
}
