import { useRef, useState } from "react";
import { streamChat, type Question, type Recommendations } from "./api";
import Chat, { type ChatMessage } from "./components/Chat";
import Intake from "./components/Intake";
import Results from "./components/Results";
import "./app.css";

export default function App() {
  const sessionId = useRef(crypto.randomUUID());
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
    } catch {
      setMessages((current) => [
        ...current,
        { role: "agent", text: "Couldn't reach the service. Check your connection and retry." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    window.location.reload();
  }

  return (
    <main>
      <header className="topbar">
        <span className="brand">Safe Harbor</span>
        <div className="topbar-right">
          {started && (
            <button className="link" onClick={reset}>
              Start over
            </button>
          )}
          <span className="licensed">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6l7-3z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path
                d="M9 12l2 2 4-4"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Licensed
          </span>
        </div>
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
          />
          {recommendations && <Results recommendations={recommendations} />}
        </>
      )}
    </main>
  );
}
