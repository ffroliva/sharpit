# Interactive Tutorial: See Inside Your FastAPI Application

Welcome to sharpit. In under five minutes, this interactive walkthrough demonstrates what sharpit is, the hidden runtime problems it detects, and how both developers and AI coding agents inspect running FastAPI services.

<div class="tutorial-walkthrough" id="tutorial-walkthrough">

  <!-- Progress header (interactive mode only) -->
  <div class="tutorial-header" role="region" aria-label="Tutorial Progress">
    <div class="tutorial-progress-meta">
      <span class="tutorial-step-counter" id="step-counter">Step 1 of 7</span>
      <span class="tutorial-time-estimate">~4 min interactive walkthrough</span>
    </div>
    <div class="tutorial-progress-track" role="progressbar" aria-valuenow="1" aria-valuemin="1" aria-valuemax="7" id="tutorial-progressbar" aria-label="Walkthrough progress">
      <div class="tutorial-progress-fill" style="width: 14.28%;"></div>
    </div>
    <nav class="tutorial-nav-tabs" aria-label="Tutorial steps">
      <button type="button" class="tutorial-tab is-active" data-step="1" aria-current="step">1. Problem</button>
      <button type="button" class="tutorial-tab" data-step="2">2. One Line</button>
      <button type="button" class="tutorial-tab" data-step="3">3. Console</button>
      <button type="button" class="tutorial-tab" data-step="4">4. Checks</button>
      <button type="button" class="tutorial-tab" data-step="5">5. In CI</button>
      <button type="button" class="tutorial-tab" data-step="6">6. AI Agent</button>
      <button type="button" class="tutorial-tab" data-step="7">7. Try It</button>
    </nav>
  </div>

  <!-- Steps container -->
  <div class="tutorial-steps-container">

    <!-- Step 1: The Problem -->
    <section class="tutorial-step is-active" id="step-1" data-step="1" tabindex="-1" aria-labelledby="step-1-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 1</span>
        <h2 class="tutorial-step-title" id="step-1-heading">The Problem: Passing Tests, Broken Runtime</h2>
        <p class="tutorial-step-desc">
          Automated unit tests check return values and status codes, but they rarely reveal how an endpoint actually executes in production.
        </p>
      </div>

      <div class="tutorial-grid-2">
        <div class="tutorial-card">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <strong>Test Suite Output</strong>
            <span class="tutorial-status-badge tutorial-status-pass">PASSED</span>
          </div>
          <div class="tutorial-code-block">
<code>test_orders.py::test_get_orders PASSED  [100%]
1 passed in 0.08s
Status: 200 OK
Body: {"orders": 30, "status": "active"}</code>
          </div>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.5rem 0 0 0;">
            The endpoint returns HTTP 200, the JSON payload matches schema, and all assertions pass.
          </p>
        </div>

        <div class="tutorial-card">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <strong>Hidden Runtime Reality</strong>
            <span class="tutorial-status-badge tutorial-status-danger">DEFECTS</span>
          </div>
          <div class="tutorial-code-block">
<code>Endpoint: GET /orders
Queries executed: 31 (1 parent + 30 repeated SELECTs)
Exceptions: 1 swallowed behind try/except (200 OK)
Configuration: insecure default fallback</code>
          </div>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.5rem 0 0 0;">
            A classic N+1 query pattern issues 31 queries for one page. An exception is swallowed silently, and you only discover the bottleneck in production.
          </p>
        </div>
      </div>
    </section>

    <!-- Step 2: One Line -->
    <section class="tutorial-step" id="step-2" data-step="2" tabindex="-1" aria-labelledby="step-2-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 2</span>
        <h2 class="tutorial-step-title" id="step-2-heading">One Line: Developer Console In Your App</h2>
        <p class="tutorial-step-desc">
          Install sharpit and mount it to your existing FastAPI application. It activates only in development, stays on localhost, and masks secrets automatically.
        </p>
      </div>

      <div class="tutorial-code-block">
<code>pip install sharpit</code>
      </div>

      <div class="tutorial-code-block">
<code>from fastapi import FastAPI
import sharpit

app = FastAPI()

# Mount sharpit after your application middleware:
sharpit.install(app)  # mounts /sharpit and /sharpit/api</code>
      </div>

      <div class="tutorial-grid-4">
        <div class="tutorial-card">
          <strong>Fails Closed</strong>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.25rem 0 0 0;">
            Turns on only when a dev server signal is present (<code>fastapi dev</code>, <code>uvicorn --reload</code>) or <code>SHARPIT_ENABLED=ON</code>. Otherwise answers 404.
          </p>
        </div>
        <div class="tutorial-card">
          <strong>Localhost Only</strong>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.25rem 0 0 0;">
            Restricted to loopback callers. Reverse-proxy forwarding headers never grant trust, and remote access requires an explicit token.
          </p>
        </div>
        <div class="tutorial-card">
          <strong>Masks Secrets</strong>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.25rem 0 0 0;">
            Passwords, tokens, credentials, and sensitive SQL parameters are masked before filtering, display, or JSON serialization.
          </p>
        </div>
        <div class="tutorial-card">
          <strong>No Read Side Effects</strong>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.25rem 0 0 0;">
            Inspecting panels, routes, configuration, or traces never opens a socket, writes a file, or modifies logger levels.
          </p>
        </div>
      </div>
    </section>

    <!-- Step 3: The Console -->
    <section class="tutorial-step" id="step-3" data-step="3" tabindex="-1" aria-labelledby="step-3-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 3</span>
        <h2 class="tutorial-step-title" id="step-3-heading">The Console: Runtime Insights & N+1 Detection</h2>
        <p class="tutorial-step-desc">
          Open <code>http://127.0.0.1:8000/sharpit/</code> in your browser. Sharpit correlates every incoming HTTP request with the SQL statements it triggered and evaluates runtime insight rules.
        </p>
      </div>

      <!-- Mock Console UI -->
      <div class="tutorial-mock-console">
        <div class="tutorial-mock-header">
          <span class="tutorial-mock-brand">sharpit</span>
          <nav class="tutorial-mock-nav" aria-label="Console panels">
            <span class="tutorial-mock-nav-item">Overview</span>
            <span class="tutorial-mock-nav-item">Live Activity</span>
            <span class="tutorial-mock-nav-item">SQL Traces</span>
            <span class="tutorial-mock-nav-item is-selected">Runtime Insights</span>
          </nav>
        </div>
        <div class="tutorial-mock-body">
          <div class="tutorial-mock-request-bar">
            <span><span class="tutorial-mock-method">GET</span> /orders</span>
            <span>Status: <strong style="color: var(--ok);">200 OK</strong></span>
            <span>Duration: <strong>45.0 ms</strong></span>
            <span>Queries: <strong style="color: var(--danger);">31 statements</strong></span>
          </div>

          <table class="tutorial-mock-sql-table">
            <thead>
              <tr>
                <th style="width: 75px;">Time</th>
                <th>Statement</th>
                <th style="width: 170px;">Call Site</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>2.0 ms</td>
                <td>SELECT id, customer_id, total FROM orders WHERE status = ?</td>
                <td>app/routes/orders.py:40</td>
              </tr>
              <tr class="tutorial-mock-sql-highlight">
                <td>1.0 ms</td>
                <td>SELECT id, order_id, product_name, price FROM order_items WHERE order_id = ? <span style="color: var(--warn); font-weight: 600;">(repeated &times;30)</span></td>
                <td>app/routes/orders.py:42</td>
              </tr>
            </tbody>
          </table>

          <div class="tutorial-mock-insight-box">
            <div class="tutorial-mock-insight-title">
              <span class="tutorial-status-badge tutorial-status-warn">OBSERVED</span>
              <span>Repeated SELECTs (N+1 query pattern)</span>
            </div>
            <div class="tutorial-mock-insight-sentence">
              <code>GET /orders</code> ran <code>SELECT id, order_id, product_name, price FROM order_items WHERE order_id = ?</code> 5 or more times after another statement in 3 of 3 requests, up to 30 times in one.
            </div>
            <div class="tutorial-mock-insight-remediation">
              <strong>Remediation:</strong> Open an exemplar request in Live Activity and check whether each repeat loads the children of one row the first statement returned. If it does, load them with one statement, such as a join or an IN list, in SQL Trace's call site (<code>app/routes/orders.py:42</code>).
            </div>
          </div>
        </div>
      </div>
      <p style="font-size: 0.8125rem; color: var(--muted); margin-top: 0.5rem;">
        Captured directly from the sharpit engine's <code>repeated-selects</code> analyzer. The exact statement shape, repeat frequency, and source code line are reported immediately.
      </p>
    </section>

    <!-- Step 4: Checks You Can Run -->
    <section class="tutorial-step" id="step-4" data-step="4" tabindex="-1" aria-labelledby="step-4-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 4</span>
        <h2 class="tutorial-step-title" id="step-4-heading">Checks You Can Run: Built-In Advisors</h2>
        <p class="tutorial-step-desc">
          Sharpit provides automated advisor scans that inspect configuration, physical schemas, dependencies, and code structure. Run them in the web console or via CLI.
        </p>
      </div>

      <div class="tutorial-grid-2">
        <div class="tutorial-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.375rem;">
            <strong>Security Advisor</strong>
            <code style="font-size: 0.75rem;">sharpit security scan --fail-on high</code>
          </div>
          <p style="font-size: 0.84375rem; color: var(--ink); line-height: 1.45; margin: 0;">
            Actively reviews application security configuration, middleware filter chains, and security headers against heuristic rules to detect missing host validation, weak tokens, or disabled guards.
          </p>
        </div>

        <div class="tutorial-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.375rem;">
            <strong>Database Advisor</strong>
            <code style="font-size: 0.75rem;">sharpit db report --json</code>
          </div>
          <p style="font-size: 0.84375rem; color: var(--ink); line-height: 1.45; margin: 0;">
            Introspects physical database schemas through SQLAlchemy to flag missing primary keys, unindexed foreign keys, and connection pool bottlenecks.
          </p>
        </div>

        <div class="tutorial-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.375rem;">
            <strong>Vulnerabilities (OSV)</strong>
            <code style="font-size: 0.75rem;">sharpit vulnerabilities report --json</code>
          </div>
          <p style="font-size: 0.84375rem; color: var(--ink); line-height: 1.45; margin: 0;">
            Scans installed Python packages against the OSV.dev vulnerability database to identify known CVEs affecting runtime dependencies.
          </p>
        </div>

        <div class="tutorial-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.375rem;">
            <strong>Architecture Advisor</strong>
            <code style="font-size: 0.75rem;">sharpit architecture report --json</code>
          </div>
          <p style="font-size: 0.84375rem; color: var(--ink); line-height: 1.45; margin: 0;">
            Analyzes application classes and packages against project-agnostic structure rules to prevent layer leaks and cyclic dependencies.
          </p>
        </div>
      </div>
    </section>

    <!-- Step 5: In CI -->
    <section class="tutorial-step" id="step-5" data-step="5" tabindex="-1" aria-labelledby="step-5-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 5</span>
        <h2 class="tutorial-step-title" id="step-5-heading">In CI: Gating Builds on Runtime Evidence</h2>
        <p class="tutorial-step-desc">
          Automate security checks and runtime regression gates in continuous integration pipelines using predictable exit codes.
        </p>
      </div>

      <div class="tutorial-grid-2">
        <div class="tutorial-card">
          <strong>1. Standalone Security Scan</strong>
          <div class="tutorial-code-block">
<code>sharpit security scan --fail-on high</code>
          </div>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0;">
            Scans the running service and returns an exit code based on the highest finding severity.
          </p>
        </div>

        <div class="tutorial-card">
          <strong>2. Pytest Runtime Plugin</strong>
          <div class="tutorial-code-block">
<code>pytest --sharpit</code>
          </div>
          <p style="font-size: 0.8125rem; color: var(--muted); margin: 0;">
            Tracks queries and swallowed exceptions per test, gates N+1 queries (<code>sharpit.n-plus-one</code>), and assesses REST API conventions.
          </p>
        </div>
      </div>

      <h3 style="font-size: 1rem; margin: 1.25rem 0 0.5rem 0;">Exit Code Contract</h3>
      <table class="tutorial-table">
        <thead>
          <tr>
            <th style="width: 70px;">Code</th>
            <th style="width: 140px;">Outcome</th>
            <th>Meaning</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>0</code></td>
            <td><strong>PASS</strong> (SUCCESS)</td>
            <td>All checks completed cleanly; no findings met or exceeded the failure threshold.</td>
          </tr>
          <tr>
            <td><code>1</code></td>
            <td><strong>CANNOT EVALUATE</strong> (ERROR)</td>
            <td>Capture was incomplete, the application could not be inspected, or test gates failed closed (<code>status: unknown</code>).</td>
          </tr>
          <tr>
            <td><code>2</code></td>
            <td><strong>REFUSED</strong> (REFUSED)</td>
            <td>Access denied by the security guard chain, panel disabled, or action refused under read-only policy.</td>
          </tr>
          <tr>
            <td><code>3</code></td>
            <td><strong>THRESHOLD MET</strong> (THRESHOLD)</td>
            <td>One or more findings reached or exceeded the <code>--fail-on</code> severity threshold (e.g. <code>HIGH</code>).</td>
          </tr>
        </tbody>
      </table>

      <div class="tutorial-card" style="margin-top: 1rem;">
        <strong>Real Pytest Failure Transcript:</strong>
        <div class="tutorial-code-block">
<code>FAILURES: test_orders_route
sharpit: sharpit.n-plus-one: 30 executions of one SELECT in the call phase
================================ sharpit: fail ================================
status: fail
tests with findings: 1
gate counts:
  sharpit.n-plus-one: 1
worst tests:
  test_orders.py::test_orders_route: 1 finding(s)
report: sharpit-report.json
sharpit checked: test-runtime gates (sharpit.max-queries, sharpit.n-plus-one, sharpit.exception)</code>
        </div>
      </div>
    </section>

    <!-- Step 6: With An AI Agent -->
    <section class="tutorial-step" id="step-6" data-step="6" tabindex="-1" aria-labelledby="step-6-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 6</span>
        <h2 class="tutorial-step-title" id="step-6-heading">With an AI Agent: Runtime Grounding vs Guesswork</h2>
        <p class="tutorial-step-desc">
          AI coding agents often struggle with performance bugs because static source code does not show query execution counts or runtime bottlenecks.
        </p>
      </div>

      <div class="tutorial-grid-2">
        <div class="tutorial-card">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <strong>Without sharpit</strong>
            <span class="tutorial-status-badge tutorial-status-warn">SPECULATIVE</span>
          </div>
          <ul style="font-size: 0.8125rem; color: var(--ink); padding-left: 1.25rem; margin: 0; line-height: 1.6;">
            <li>The agent reads static files, greps through logs, and guesses execution frequency.</li>
            <li>It hypothesizes whether an ORM relationship loads lazily or eagerly.</li>
            <li>Proposes trial-and-error edits with no way to verify runtime query counts.</li>
            <li>Risk of introducing regressions or unnecessary premature optimizations.</li>
          </ul>
        </div>

        <div class="tutorial-card">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
            <strong>With sharpit</strong>
            <span class="tutorial-status-badge tutorial-status-pass">BOUNDED EVIDENCE</span>
          </div>
          <ul style="font-size: 0.8125rem; color: var(--ink); padding-left: 1.25rem; margin: 0; line-height: 1.6;">
            <li>Agent queries the running application over MCP (<code>/sharpit/api/mcp</code>) or CLI (<code>sharpit activity --json</code>).</li>
            <li>Follows structured diagnostic playbooks (e.g. <code>database-efficiency.md</code>).</li>
            <li>Receives masked, bounded evidence with exact statement fingerprints and call sites.</li>
            <li>Verifies the fix immediately: query count drops from 31 to 1 at runtime.</li>
          </ul>
        </div>
      </div>

      <div class="tutorial-card" style="margin-top: 1rem;">
        <p style="margin: 0; font-size: 0.875rem;">
          Learn how to connect Claude Code, Cursor, Codex, or custom agents: read the full <a href="ai-agents.md">AI agents guide</a>.
        </p>
      </div>
    </section>

    <!-- Step 7: Try It -->
    <section class="tutorial-step" id="step-7" data-step="7" tabindex="-1" aria-labelledby="step-7-heading">
      <div class="tutorial-step-header">
        <span class="tutorial-step-tag">Step 7</span>
        <h2 class="tutorial-step-title" id="step-7-heading">Try It: Get Started in Seconds</h2>
        <p class="tutorial-step-desc">
          Add sharpit to your FastAPI project today to eliminate runtime surprises and give your team real visibility.
        </p>
      </div>

      <div class="tutorial-card">
        <strong>1. Install the package:</strong>
        <div class="tutorial-code-block">
<code>pip install "sharpit[fastapi]"
# or using uv:
uv add "sharpit[fastapi]"</code>
        </div>

        <strong>2. Add to your FastAPI app:</strong>
        <div class="tutorial-code-block">
<code>from fastapi import FastAPI
import sharpit

app = FastAPI()

# Register application middleware first, then mount sharpit:
sharpit.install(app)</code>
        </div>

        <strong>3. Run with a dev server signal:</strong>
        <div class="tutorial-code-block">
<code>fastapi dev app.py  # or: uvicorn app:app --reload</code>
        </div>
        <p style="font-size: 0.8125rem; color: var(--muted); margin: 0.5rem 0 0 0;">
          Then open <a href="http://127.0.0.1:8000/sharpit/">http://127.0.0.1:8000/sharpit/</a> in your browser.
        </p>
      </div>

      <div class="tutorial-cta-group">
        <a href="quickstart.md" class="tutorial-btn tutorial-btn-primary">Go to Quickstart &rarr;</a>
        <a href="https://github.com/ffroliva/sharpit" class="tutorial-star-btn" target="_blank" rel="noopener noreferrer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25z"/>
          </svg>
          Star sharpit on GitHub
        </a>
      </div>
    </section>

  </div>

  <!-- Walkthrough interactive footer controls -->
  <div class="tutorial-controls">
    <button type="button" class="tutorial-btn tutorial-btn-secondary" id="tutorial-prev" disabled>&larr; Previous</button>
    <div class="tutorial-keyboard-hint">
      Navigate with <kbd>&larr;</kbd> and <kbd>&rarr;</kbd>
    </div>
    <button type="button" class="tutorial-btn tutorial-btn-primary" id="tutorial-next">Next &rarr;</button>
  </div>

</div>
