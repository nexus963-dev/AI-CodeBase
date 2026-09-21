import { useState } from "react";

function MessageInput({ onSend }) {
  const [input, setInput] = useState("");

  const handleSend = () => {
    const message = input.trim();

    if (!message) return;

    onSend(message);
    setInput("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="message-input-wrapper">

      <div className="message-input">

        <button
          className="attachment-btn"
          type="button"
          aria-label="Attach file"
        >
          📎
        </button>

        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this repository..."
        />

        <button
          className="send-btn"
          type="button"
          aria-label="Send message"
          onClick={handleSend}
          disabled={!input.trim()}
        >
          ↑
        </button>

      </div>

      <p className="input-hint">
        Repix answers using knowledge from your repository.
      </p>

    </div>
  );
}

export default MessageInput;