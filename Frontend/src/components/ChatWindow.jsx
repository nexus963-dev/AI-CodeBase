import { useEffect, useState } from "react";
import axios from "axios";

import MessageInput from "./MessageInput";
import ChatMessage from "./ChatMessage";

const API_URL = import.meta.env.VITE_API_URL;

function ChatWindow({
  repositoryName,
  sessionId,
  onSessionCreated,
}) {

  const [messages, setMessages] = useState([]);

  const [isLoading, setIsLoading] = useState(false);


  /*
   * Load previous messages whenever
   * the selected session changes.
   */

  useEffect(() => {

    const loadMessages = async () => {

      /*
       * No session means this is a new chat.
       */

      if (!sessionId) {

        setMessages([]);

        return;

      }


      try {

        const response = await axios.get(
          `${API_URL}/chat/sessions/${sessionId}`
        );

        setMessages(response.data);

      } catch (error) {

        console.error(
          "Failed to load chat messages:",
          error
        );

        setMessages([]);

      }

    };


    loadMessages();

  }, [sessionId]);


  const handleSendMessage = async (message) => {

    if (isLoading) {
      return;
    }


    const userMessage = {
      role: "user",
      content: message,
    };


    setMessages((previousMessages) => [

      ...previousMessages,

      userMessage,

    ]);


    setIsLoading(true);


    /*
     * Streaming state lives outside try so the
     * catch block can keep a partial answer.
     */

    let assistantContent = "";

    let assistantStarted = false;

    let returnedSessionId = null;


    const updateStreamingMessage = (content) => {

      setMessages((previousMessages) => {

        const updatedMessages = [...previousMessages];

        for (
          let index = updatedMessages.length - 1;
          index >= 0;
          index -= 1
        ) {

          if (updatedMessages[index].streaming) {

            updatedMessages[index] = {
              ...updatedMessages[index],
              content,
            };

            break;

          }

        }

        return updatedMessages;

      });

    };


    const appendToken = (text) => {

      assistantContent += text;

      if (!assistantStarted) {

        assistantStarted = true;

        setMessages((previousMessages) => [

          ...previousMessages,

          {
            role: "assistant",
            content: assistantContent,
            streaming: true,
          },

        ]);

      } else {

        updateStreamingMessage(assistantContent);

      }

    };


    try {

      const response = await fetch(
        `${API_URL}/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            repository_name: repositoryName,
            question: message,

            /*
             * Send session_id only when
             * continuing an existing chat.
             */

            ...(sessionId && {
              session_id: sessionId,
            }),

          }),
        }
      );


      if (!response.ok || !response.body) {

        throw new Error(
          `Chat API error: HTTP ${response.status}`
        );

      }


      const reader = response.body.getReader();

      const decoder = new TextDecoder();

      let buffer = "";


      /*
       * NDJSON events arrive as:
       * meta -> token* -> done | error
       */

      while (true) {

        const { done, value } =
          await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, {
          stream: true,
        });

        const lines = buffer.split("\n");

        buffer = lines.pop();


        for (const line of lines) {

          if (!line.trim()) {
            continue;
          }

          const event = JSON.parse(line);

          if (event.type === "meta") {

            returnedSessionId = event.session_id;

          } else if (event.type === "token") {

            appendToken(event.text);

          } else if (event.type === "error") {

            throw new Error(
              event.detail || "Stream failed"
            );

          }

        }

      }


      /*
       * Clear streaming flags so future
       * updates ignore this message.
       */

      if (assistantStarted) {

        setMessages((previousMessages) =>
          previousMessages.map((streamedMessage) =>
            streamedMessage.streaming
              ? { ...streamedMessage, streaming: false }
              : streamedMessage
          )
        );

      }


      /*
       * Register a brand new session only after
       * "done" - the backend has saved the answer
       * by then. Firing this mid-stream would
       * switch the session and reload messages,
       * wiping the tokens being rendered.
       */

      if (
        !sessionId &&
        returnedSessionId
      ) {

        onSessionCreated(
          returnedSessionId
        );

      }

    } catch (error) {

      console.error(
        "Chat API error:",
        error
      );


      if (assistantStarted) {

        /*
         * Keep the partial answer and note
         * that it was cut off.
         */

        updateStreamingMessage(
          assistantContent
          + "\n\n**[Response interrupted]**"
        );

      } else {

        setMessages(
          (previousMessages) => [

            ...previousMessages,

            {
              role: "assistant",
              content:
                "Sorry, I couldn't process your request. Please make sure the backend is running and the repository has been indexed.",
            },

          ]
        );

      }

    } finally {

      setIsLoading(false);

    }

  };


  return (

    <main className="chat-window">

      <div className="chat-messages">


        {messages.length === 0 &&
          !isLoading && (

            <div className="chat-welcome">

              <div className="chat-welcome-icon">
                ✦
              </div>

              <h1>
                Welcome to Repix
              </h1>

              <p>
                Your AI repository companion is ready.
              </p>

              <span>
                Ask anything about your codebase,
                architecture, files, or implementation.
              </span>

            </div>

          )}


        {messages.map(
          (message, index) => (

            <ChatMessage
              key={
                message.id || index
              }
              role={message.role}
              content={message.content}
            />

          )
        )}


        {isLoading &&
          messages.length > 0 &&
          messages[
            messages.length - 1
          ]?.role !== "assistant" && (

            <ChatMessage
              role="assistant"
              content="Repix is thinking..."
            />

          )}


      </div>


      <MessageInput
        onSend={handleSendMessage}
      />

    </main>

  );

}


export default ChatWindow;