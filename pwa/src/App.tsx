import { useRef, useState } from "react";
import { newSessionId, streamChat, type Question, type Recommendations } from "./api";
import Chat, { type ChatMessage } from "./components/Chat";
import { ShieldIcon } from "./components/icons";
import Intake from "./components/Intake";
import ResetButton from "./components/ResetButton";
import Results from "./components/Results";
import "./app.css";

export default function App() {
  const sessionId = useRef(newSessionId());
  const modeRef = useRef<"freeform" | "guided">("freeform");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState<Question | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendations | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [started, setStarted] = useState(false);

  async function send(text: string, mode?: "freeform" | "guided") {
    if (mode) modeRef.current = mode;
    setStarted(true);
    setBusy(true);
    setQuestion(null);
    setMessages((current) => [...current, { role: "user", text }]);

    try {
      await streamChat(sessionId.current, text, modeRef.current, ({ event, data }) => {
        if (event === "question") {
          const q = data as Question;
          setQuestion(q);
          setMessages((current) => [...current, { role: "agent", text: q.text }]);
        } else if (event === "message") {
          const { text: agentText } = data as { text: string };
          setMessages((current) => [...current, { role: "agent", text: agentText }]);
        } else if (event === "recommendations") {
          setRecommendations(data as Recommendations);
          setDone(true);
        } else if (event === "error") {
          const detail = (data as { detail?: string }).detail ?? "unknown error";
          setMessages((current) => [
            ...current,
            { role: "agent", text: `Something went wrong on our side — please try again.\n(${detail})` },
          ]);
        }
      });
    } catch (error) {
      const rateLimited = error instanceof Error && error.message.includes("429");
      setMessages((current) => [
        ...current,
        {
          role: "agent",
          text: rateLimited
            ? "You're sending messages very quickly — please wait a moment and try again."
            : "Couldn't reach the service. Check your connection and retry.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    window.location.reload();
  }

  return (
    <main className={done ? "done" : ""}>
      <header className="topbar">
        <div className="brand-id">
          <span className="brand-avatar">
            <ShieldIcon size={20} />
            <span className="status-dot" />
          </span>
          <span className="brand-text">
            <span className="brand">Safe Harbor</span>
            <span className="brand-sub">Finds honest matches — never a forced fit</span>
          </span>
        </div>
        <span className="licensed">
          <ShieldIcon size={13} />
          Licensed
        </span>
      </header>

      {!started ? (
        <Intake onSubmit={(text, mode) => void send(text, mode)} />
      ) : (
        <>
          <Chat
            messages={messages}
            question={question}
            busy={busy}
            done={done}
            onSend={(text) => void send(text)}
            onReset={reset}
          />
          {recommendations && <Results recommendations={recommendations} />}
          {done && (
            <div className="reset-row">
              <ResetButton onClick={reset} label className="reset-btn" />
            </div>
          )}
        </>
      )}

      <footer className="build-stamp">build {__BUILD_ID__}</footer>
    </main>
  );
}
