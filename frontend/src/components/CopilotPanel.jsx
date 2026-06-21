import React, { useState } from "react";
import { api } from "../api/client";

const SAMPLES = [
  "What's the risk on Hosur Road tomorrow at 7 PM?",
  "How does Tumkur Road behave on Saturdays?",
  "Risk profile of Mysore Road during festivals",
  "Yelahanka station performance at 9 AM",
];

export default function CopilotPanel() {
  const [q, setQ] = useState("");
  const [resp, setResp] = useState(null);
  const [busy, setBusy] = useState(false);

  const ask = async (text) => {
    const query = text ?? q;
    if (!query.trim()) return;
    setBusy(true);
    try {
      const r = await api.copilot(query);
      setResp(r);
    } catch (e) {
      setResp({
        answer: "Co-pilot unavailable.",
        citations: [],
        insufficient: true,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="copilot">
      <div className="input-row">
        <input
          placeholder="Ask the city: 'risk on Hosur Road at 7 PM tomorrow?'"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
        />
        <button className="primary" onClick={() => ask()} disabled={busy}>
          {busy ? "..." : "Ask"}
        </button>
      </div>

      {!resp && (
        <>
          <div className="muted small">Try one of:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {SAMPLES.map((s, i) => (
              <button
                key={i}
                style={{ fontSize: 11, padding: "4px 8px" }}
                onClick={() => {
                  setQ(s);
                  ask(s);
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </>
      )}

      {resp && (
        <>
          <div
            className={
              "answer" + (resp.insufficient ? " insufficient" : "")
            }
            dangerouslySetInnerHTML={{
              __html: resp.answer
                .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                .replace(/\n/g, "<br/>"),
            }}
          />
          <div className="citations">
            {resp.citations
              ?.filter((c) => c.type === "row_count")
              .map((c, i) => (
                <span className="cite" key={i}>
                  source: {c.value} matching rows
                </span>
              ))}
            {resp.filters && (
              <span className="cite">
                filters:{" "}
                {Object.entries(resp.filters)
                  .filter(([, v]) => v != null && v !== "")
                  .map(([k, v]) => `${k}=${v}`)
                  .join(", ") || "none"}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
