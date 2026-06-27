import React from "react";
import ReactDOM from "react-dom/client";
import { AlertTriangle, Check, CircleDot, Database, GitBranch, Gauge, Play, Server, ShieldCheck, Terminal, X } from "lucide-react";
import "./styles.css";

type AgentStatus = "pending" | "running" | "complete";
type InvestigationStatus = "queued" | "running" | "complete";

type Agent = {
  name: string;
  status: AgentStatus;
  summary: string;
  findings: string[];
};

type Score = {
  hypothesis: string;
  score: number;
  reasons: string[];
};

type Report = {
  summary: string;
  root_cause: string;
  evidence: string[];
  immediate_actions: string[];
  long_term_recommendations: string[];
  human_approval_required: boolean;
};

type Investigation = {
  id: string;
  description: string;
  status: InvestigationStatus;
  progress: number;
  agents: Agent[];
  scores: Score[];
  report: Report | null;
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const starterDescription = "Checkout API is timing out and returning HTTP 500 errors.";

const iconMap: Record<string, React.ElementType> = {
  Planner: CircleDot,
  Deployment: GitBranch,
  Metrics: Gauge,
  Logs: Terminal,
  Database: Database,
  Kubernetes: Server,
};

function App() {
  const [description, setDescription] = React.useState(starterDescription);
  const [investigation, setInvestigation] = React.useState<Investigation | null>(null);
  const [decision, setDecision] = React.useState<"approved" | "rejected" | null>(null);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!investigation || investigation.status === "complete") return;
    const handle = window.setInterval(async () => {
      const response = await fetch(`${API_URL}/investigation/${investigation.id}`);
      const data = (await response.json()) as Investigation;
      setInvestigation(data);
    }, 700);
    return () => window.clearInterval(handle);
  }, [investigation]);

  async function startInvestigation() {
    setError("");
    setDecision(null);
    try {
      const response = await fetch(`${API_URL}/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description }),
      });
      if (!response.ok) throw new Error("Investigation request failed");
      setInvestigation((await response.json()) as Investigation);
    } catch {
      setError("Backend is not reachable. Start FastAPI on port 8000, then try again.");
    }
  }

  const topScore = investigation?.scores?.[0];

  return (
    <main className="min-h-screen bg-[#edf2f7] text-ink">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded bg-ink text-white">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-normal">SentinelAI</h1>
              <p className="text-sm text-slate-600">AI Production War Room</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="rounded border border-line bg-panel px-3 py-1.5 text-slate-700">Read-only investigation</span>
            <span className="rounded border border-teal-200 bg-teal-50 px-3 py-1.5 text-signal">Human approval required</span>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-4 px-5 py-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Panel title="Incident Description">
          <div className="space-y-3">
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-32 w-full resize-none rounded border border-line bg-white p-3 text-sm outline-none ring-signal/20 focus:ring-4"
            />
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={startInvestigation} className="inline-flex items-center gap-2 rounded bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
                <Play size={16} />
                Investigate
              </button>
              {investigation && <span className="text-sm text-slate-600">Status: {investigation.status} · Progress: {investigation.progress}%</span>}
            </div>
            {error && <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-danger">{error}</p>}
          </div>
        </Panel>

        <Panel title="Hypothesis Scores">
          {investigation?.scores?.length ? (
            <div className="space-y-3">
              {investigation.scores.map((score) => (
                <div key={score.hypothesis}>
                  <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium">{score.hypothesis}</span>
                    <span className="tabular-nums text-slate-600">{score.score}</span>
                  </div>
                  <div className="h-2 rounded bg-slate-200">
                    <div className="h-2 rounded bg-signal" style={{ width: `${Math.min(score.score, 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState label="Scores appear when the evidence collector finishes." />
          )}
        </Panel>
      </section>

      <section className="mx-auto grid max-w-7xl gap-4 px-5 pb-5 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Live Agent Status">
          <div className="grid gap-3 sm:grid-cols-2">
            {(investigation?.agents ?? defaultAgents()).map((agent) => (
              <AgentCard key={agent.name} agent={agent} />
            ))}
          </div>
        </Panel>

        <Panel title="Incident Report">
          {investigation?.report ? (
            <div className="space-y-4">
              <div className="rounded border border-amber-200 bg-amber-50 p-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 text-amber" size={18} />
                  <div>
                    <p className="font-medium">{topScore?.hypothesis}</p>
                    <p className="text-sm text-slate-700">{investigation.report.root_cause}</p>
                  </div>
                </div>
              </div>
              <ReportSection title="Evidence" items={investigation.report.evidence} />
              <ReportSection title="Immediate Actions" items={investigation.report.immediate_actions} />
              <ReportSection title="Long-term Recommendations" items={investigation.report.long_term_recommendations} />
              <div className="flex flex-wrap gap-3 border-t border-line pt-4">
                <button onClick={() => setDecision("approved")} className="inline-flex items-center gap-2 rounded bg-signal px-4 py-2 text-sm font-medium text-white hover:bg-teal-800">
                  <Check size={16} />
                  Approve
                </button>
                <button onClick={() => setDecision("rejected")} className="inline-flex items-center gap-2 rounded border border-line bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50">
                  <X size={16} />
                  Reject
                </button>
                {decision && <span className="self-center text-sm font-medium text-slate-700">Remediation {decision} by engineer.</span>}
              </div>
            </div>
          ) : (
            <EmptyState label="Start an investigation to generate the incident report." />
          )}
        </Panel>
      </section>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-line bg-white p-4 shadow-soft">
      <h2 className="mb-4 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  const Icon = iconMap[agent.name] ?? CircleDot;
  const statusClass = {
    pending: "border-slate-200 bg-slate-50 text-slate-500",
    running: "border-amber-200 bg-amber-50 text-amber",
    complete: "border-teal-200 bg-teal-50 text-signal",
  }[agent.status];

  return (
    <article className="min-h-40 rounded border border-line bg-panel p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon size={18} />
          <h3 className="font-medium">{agent.name}</h3>
        </div>
        <span className={`rounded border px-2 py-1 text-xs capitalize ${statusClass}`}>{agent.status}</span>
      </div>
      <p className="mb-2 text-sm text-slate-700">{agent.summary || "Waiting for planner."}</p>
      <ul className="space-y-1 text-xs leading-5 text-slate-600">
        {agent.findings.slice(0, 3).map((finding) => (
          <li key={finding}>• {finding}</li>
        ))}
      </ul>
    </article>
  );
}

function ReportSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <ul className="space-y-2 text-sm text-slate-700">
        {items.map((item) => (
          <li key={item} className="rounded border border-line bg-panel px-3 py-2">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="grid min-h-40 place-items-center rounded border border-dashed border-line bg-panel p-5 text-center text-sm text-slate-500">{label}</div>;
}

function defaultAgents(): Agent[] {
  return ["Planner", "Deployment", "Metrics", "Logs", "Database", "Kubernetes"].map((name) => ({
    name,
    status: "pending",
    summary: "",
    findings: [],
  }));
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

