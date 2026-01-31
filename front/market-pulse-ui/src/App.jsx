import { useEffect, useMemo, useState } from "react";
import "./App.css";

async function apiGet(baseUrl, path, params = {}) {
  const url = new URL(path, baseUrl);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
  return data;
}

const AGENTS = [
  {
    id: "pulse",
    title: "Market Pulse",
    subtitle: "What skills are hot right now",
    emoji: "MP",
  },
  {
    id: "match",
    title: "CV -> Job Matches",
    subtitle: "Find matching roles fast",
    emoji: "JM",
  },
  {
    id: "upgrade",
    title: "CV -> Skill Upgrade",
    subtitle: "Get a focused learning plan",
    emoji: "SU",
  },
  {
    id: "salary",
    title: "Salary Snapshot",
    subtitle: "Pay bands by role & location",
    emoji: "SS",
  },
];

function Chip({ ok, children }) {
  return (
    <span className={`chip ${ok ? "chip-ok" : "chip-bad"}`}>
      {children}
    </span>
  );
}

function BubbleStage({ agents, selectedId, onSelect, apiOk, baseUrl, apiErr }) {
  const orbitAgents = agents.filter((a) => a.id !== "pulse");

  return (
    <section className="home" id="home">
      <div className="hero-copy">
        <div className="eyebrow">Multi-agent workspace</div>
        <h1>Market Pulse</h1>
        <p>
          Float between focused agents that surface market demand, salary ranges, and CV-driven insights.
          Pick a bubble to jump into the workspace.
        </p>
        {/* testing - remove later*/}
        {/* <div className="status-row">
          <Chip ok={apiOk}>{apiOk ? "API connected" : "API not reachable"}</Chip>
          <span className="status-base">Backend: <code>{baseUrl}</code></span>
        </div> */}
        {apiErr && <div className="status-error">{apiErr}</div>}
      </div>

      <div className="bubble-area">
        <div className="bubble-stage" aria-label="Agent bubbles">
          <div className="bubble-wrapper center-wrapper">
            <button
              className={`bubble center ${selectedId === "pulse" ? "selected" : ""}`}
              onClick={() => onSelect("pulse")}
            >
              <span className="bubble-icon">{AGENTS.find((a) => a.id === "pulse")?.emoji}</span>
              <span className="bubble-title">Market Pulse</span>
              <span className="bubble-subtitle">Skills, roles, salary</span>
            </button>
          </div>

          {orbitAgents.map((agent, idx) => (
            <div key={agent.id} className={`bubble-wrapper bubble${idx + 1}`}>
              <button
                className={`bubble ${selectedId === agent.id ? "selected" : ""}`}
                onClick={() => onSelect(agent.id)}
                style={{ animationDelay: `${0.7 * idx}s` }}
                title={agent.subtitle}
              >
                <span className="bubble-icon">{agent.emoji}</span>
                <span className="bubble-title">{agent.title}</span>
                <span className="bubble-subtitle">{agent.subtitle}</span>
              </button>
            </div>
          ))}
        </div>

        <div className="bubble-grid" aria-label="Agent bubbles mobile layout">
          {agents.map((agent, idx) => (
            <button
              key={agent.id}
              className={`bubble ${selectedId === agent.id ? "selected" : ""}`}
              onClick={() => onSelect(agent.id)}
              style={{ animationDelay: `${0.6 * idx}s` }}
              title={agent.subtitle}
            >
              <span className="bubble-icon">{agent.emoji}</span>
              <span className="bubble-title">{agent.title}</span>
              <span className="bubble-subtitle">{agent.subtitle}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function PanelShell({ title, subtitle, children, right }) {
  return (
    <section className="panel-shell">
      <div className="panel-head">
        <div>
          <div className="panel-title">{title}</div>
          <div className="panel-subtitle">{subtitle}</div>
        </div>
        {right}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function MarketPulsePanel({ baseUrl }) {
  const [limitJobs, setLimitJobs] = useState(100);
  const [topK, setTopK] = useState(20);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);

  async function load() {
    setLoading(true);
    setErr("");
    try {
      const d = await apiGet(baseUrl, "/skills/top", {
        limit_jobs: limitJobs,
        top_k: topK,
      });
      setData(d);
    } catch (e) {
      setErr(e.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <PanelShell
      title="Market Pulse"
      subtitle="Top skills in demand based on job listings stored in Cloudant."
      right={
        <div className="panel-controls">
          <label>
            Jobs:
            <input
              type="number"
              min={1}
              value={limitJobs}
              onChange={(e) => setLimitJobs(Number(e.target.value))}
            />
          </label>
          <label>
            Top:
            <input
              type="number"
              min={1}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </label>
          <button onClick={load} disabled={loading} className="btn-primary">
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      }
    >
      {err && <div className="msg-error">Error: {err}</div>}

      {!err && !data && <div className="msg-muted">No data yet.</div>}

      {data?.skills?.length > 0 && (
        <div className="skills-grid">
          <div className="skills-head">Skill</div>
          <div className="skills-head" style={{ textAlign: "right" }}>
            Count
          </div>
          {data.skills.map((s) => (
            <div key={s.skill} className="skills-row">
              <div><code>{s.skill}</code></div>
              <div style={{ textAlign: "right" }}>{s.count}</div>
            </div>
          ))}
        </div>
      )}

      {data && !data.skills?.length && !err && (
        <div className="msg-muted">
          No skills returned. That usually means the Muse job documents use different fields than our extractor. (We can
          fix that by inspecting one Muse doc.)
        </div>
      )}
    </PanelShell>
  );
}

function SalaryPanel({ baseUrl }) {
  const [jobTitle, setJobTitle] = useState("Frontend Developer");
  const [location, setLocation] = useState("Seattle");
  const [yoe, setYoe] = useState("ONE_TO_THREE");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const d = await apiGet(baseUrl, "/salary", {
        job_title: jobTitle,
        location,
        years_of_experience: yoe,
      });
      setData(d);
    } catch (e2) {
      setErr(e2.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <PanelShell
      title="Salary _____"
      subtitle="will fetche salary data from Cloudant (salary_data)"
    >
      <form onSubmit={submit} className="salary-form">
        <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Job title" />
        <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" />
        <select value={yoe} onChange={(e) => setYoe(e.target.value)}>
          <option value="ZERO_TO_ONE">ZERO_TO_ONE</option>
          <option value="ONE_TO_THREE">ONE_TO_THREE</option>
          <option value="FOUR_TO_SIX">FOUR_TO_SIX</option>
          <option value="SEVEN_TO_NINE">SEVEN_TO_NINE</option>
          <option value="TEN_PLUS">TEN_PLUS</option>
        </select>
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Loading..." : "Search"}
        </button>
      </form>

      {err && <div className="msg-error">Error: {err}</div>}

      {data && (
        <pre className="code-block">{JSON.stringify(data, null, 2)}</pre>
      )}
    </PanelShell>
  );
}

function CvJobMatchPanel() {
  return (
    <PanelShell
      title="CV -> Job Matches"
      subtitle="Upload a CV and we'll return the best matching job listings."
    >
      <div className="stack">
        <input type="file" accept=".pdf,.doc,.docx,.txt" />
        <button disabled className="btn-disabled">
          Run Job Match
        </button>
      </div>
    </PanelShell>
  );
}

function CvSkillUpgradePanel() {
  return (
    <PanelShell
      title="CV -> Skill Upgrade"
      subtitle="Upload your CV and we'll recommend missing skills plus a 2-4 week plan."
    >
      <div className="stack">
        <input type="file" accept=".pdf,.doc,.docx,.txt" />
        <input placeholder="Target role (e.g., Frontend Developer)" />
        <button disabled className="btn-disabled" title="Next step: create POST /agent/skill-gap">
          Generate Upgrade Plan
        </button>
      </div>
    </PanelShell>
  );
}

export default function App() {
  const baseUrl = useMemo(() => import.meta.env.VITE_API_BASE_URL, []);
  const [apiOk, setApiOk] = useState(false);
  const [apiErr, setApiErr] = useState("");
  const [selected, setSelected] = useState("pulse");

  useEffect(() => {
    (async () => {
      try {
        const h = await apiGet(baseUrl, "/health");
        setApiOk(h?.status === "healthy");
        setApiErr("");
      } catch (e) {
        setApiOk(false);
        setApiErr(e.message);
      }
    })();
  }, [baseUrl]);

  const handleSelect = (id) => {
    setSelected(id);
    const workspace = document.getElementById("workspace");
    if (workspace) {
      workspace.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <div className="app-shell">
      <BubbleStage
        agents={AGENTS}
        selectedId={selected}
        onSelect={handleSelect}
        apiOk={apiOk}
        baseUrl={baseUrl}
        apiErr={apiErr}
      />

      <section className="workspace" id="workspace">
        {selected === "pulse" && <MarketPulsePanel baseUrl={baseUrl} />}
        {selected === "salary" && <SalaryPanel baseUrl={baseUrl} />}
        {selected === "match" && <CvJobMatchPanel />}
        {selected === "upgrade" && <CvSkillUpgradePanel />}
      
      </section>
        <div className="msg-muted next-note" >
          IBM Hackathon Market Pulse - 2026  
        </div>
    </div>
    
  );
}
