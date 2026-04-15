export default function ResultView({ result, model }) {
  const { bug_analysis, test_cases, root_causes, bug_report } = result

  const typeColor = { Positive: 'tc-positive', Negative: 'tc-negative', Edge: 'tc-edge' }
  const likelihoodColor = { High: 'lh-high', Medium: 'lh-medium', Low: 'lh-low' }

  return (
    <section className="results">
      <div className="section-label">
        Results
        <span className="results-meta">via {model}</span>
      </div>

      <div className="results-grid">

        {/* Agent 1 — Bug Analysis */}
        <div className="result-card card-full">
          <div className="card-header">
            <span className="agent-badge badge-1">Agent 1</span>
            <h3 className="card-title">Bug Analysis</h3>
          </div>
          <div className="card-body">
            <div className="ba-title">{bug_analysis.title}</div>
            <div className="ba-meta">
              <span className="badge-severity">{bug_analysis.severity}</span>
              <span className="badge-priority">{bug_analysis.priority}</span>
            </div>

            <div className="ba-grid">
              <div className="ba-block">
                <div className="ba-block-label">Steps to Reproduce</div>
                <ol className="ba-steps">
                  {bug_analysis.steps_to_reproduce.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              </div>
              <div className="ba-block">
                <div className="ba-block-label">Expected Result</div>
                <p className="ba-text">{bug_analysis.expected}</p>
                <div className="ba-block-label" style={{ marginTop: 16 }}>Actual Result</div>
                <p className="ba-text highlight-red">{bug_analysis.actual}</p>
              </div>
            </div>

            <div className="ba-components">
              <span className="ba-block-label">Affected Components</span>
              <div className="tag-list">
                {bug_analysis.affected_components.map(c => (
                  <span key={c} className="component-tag">{c}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Agent 2 — Test Cases */}
        <div className="result-card">
          <div className="card-header">
            <span className="agent-badge badge-2">Agent 2</span>
            <h3 className="card-title">Test Cases</h3>
          </div>
          <div className="card-body">
            <div className="tc-list">
              {test_cases.map(tc => (
                <div key={tc.id} className="tc-row">
                  <span className="tc-id">{tc.id}</span>
                  <span className={`tc-type ${typeColor[tc.type]}`}>{tc.type}</span>
                  <span className="tc-desc">{tc.description}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Agent 3 — Root Causes */}
        <div className="result-card">
          <div className="card-header">
            <span className="agent-badge badge-3">Agent 3</span>
            <h3 className="card-title">Root Cause Analysis</h3>
          </div>
          <div className="card-body">
            <div className="rc-list">
              {root_causes.map((rc, i) => (
                <div key={i} className="rc-row">
                  <span className={`rc-likelihood ${likelihoodColor[rc.likelihood]}`}>{rc.likelihood}</span>
                  <span className="rc-cause">{rc.cause}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Agent 4 — Bug Report */}
        <div className="result-card card-full">
          <div className="card-header">
            <span className="agent-badge badge-4">Agent 4</span>
            <h3 className="card-title">Bug Report</h3>
            <button
              className="copy-btn"
              onClick={() => navigator.clipboard.writeText(bug_report)}
            >
              Copy
            </button>
          </div>
          <div className="card-body">
            <pre className="bug-report-pre">{bug_report}</pre>
          </div>
        </div>

      </div>
    </section>
  )
}
