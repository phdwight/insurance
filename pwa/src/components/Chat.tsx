import { useEffect, useRef, useState } from "react";
import type { Question } from "../api";
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
        {props.messages.map((message, index) => (
          <div key={index} className={`bubble ${message.role}`}>
            {message.text}
          </div>
        ))}
        {props.busy && <div className="bubble agent thinking">…</div>}
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
          <button type="submit" disabled={props.busy || !text.trim()}>
            Send
          </button>
        </form>
      )}
    </div>
  );
}
