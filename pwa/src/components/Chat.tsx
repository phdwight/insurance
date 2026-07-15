import { useEffect, useRef, useState } from "react";
import type { Question } from "../api";
import { SendIcon, ShieldIcon } from "./icons";
import ResetButton from "./ResetButton";

export interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

export default function Chat(props: {
  messages: ChatMessage[];
  question: Question | null;
  busy: boolean;
  done: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
}) {
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [props.messages, props.busy]);

  const showChoices =
    !props.done && !props.busy && props.question?.input_type === "choice" && props.question.options;
  const numeric = props.question?.input_type === "number";

  return (
    <div className="chat">
      <div className="messages">
        <div className="day-sep">
          <span>Today</span>
        </div>
        {props.messages.map((message, index) => {
          const agent = message.role === "agent";
          // one avatar per consecutive run of agent messages
          const firstOfRun = agent && props.messages[index - 1]?.role !== "agent";
          return (
            <div key={index} className={`msg-row ${message.role}`}>
              {agent && (
                <span className={`msg-avatar ${firstOfRun ? "" : "hidden"}`} aria-hidden="true">
                  <ShieldIcon size={15} />
                </span>
              )}
              <div className={`bubble ${message.role}`}>{message.text}</div>
            </div>
          );
        })}
        {props.busy && (
          <div className="msg-row agent">
            <span className="msg-avatar" aria-hidden="true">
              <ShieldIcon size={15} />
            </span>
            <div className="bubble agent thinking" role="status" aria-label="Assistant is typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {showChoices && (
        <div className="answer-chips">
          {props.question!.options!.map((option) => (
            <button key={option} className="answer-chip" onClick={() => props.onSend(option)}>
              {option}
            </button>
          ))}
        </div>
      )}

      {!props.done && (
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim() && !props.busy) {
              props.onSend(text.trim());
              setText("");
            }
          }}
        >
          <ResetButton onClick={props.onReset} />
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={
              showChoices
                ? "Tap an option above, or type…"
                : numeric
                  ? "Enter a number…"
                  : "Type your answer…"
            }
            inputMode={numeric ? "numeric" : "text"}
            disabled={props.busy}
          />
          <button
            type="submit"
            className="send-btn"
            disabled={props.busy || !text.trim()}
            aria-label="Send"
          >
            <SendIcon />
          </button>
        </form>
      )}
      {!props.done && (
        <p className="composer-note">
          Information only — not insurance advice. Confirm terms with the insurer.
        </p>
      )}
    </div>
  );
}
