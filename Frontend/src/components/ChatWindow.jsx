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


    try {

      const response = await axios.post(
        `${API_URL}/chat`,
        {
          repository_name: repositoryName,
          question: message,

          /*
           * Send session_id only when
           * continuing an existing chat.
           */

          ...(sessionId && {
            session_id: sessionId,
          }),

        }
      );


      const answer = response.data.answer;

      const returnedSessionId =
        response.data.session_id;


      /*
       * If this was a new chat,
       * the backend created a session.
       */

      if (
        !sessionId &&
        returnedSessionId
      ) {

        onSessionCreated(
          returnedSessionId
        );

      }


      /*
       * Create empty assistant message.
       */

      const assistantMessage = {

        role: "assistant",

        content: "",

      };


      setMessages((previousMessages) => [

        ...previousMessages,

        assistantMessage,

      ]);


      /*
       * Typing animation.
       */

      let currentText = "";

      for (let i = 0; i < answer.length; i += 10) {

        currentText += answer.slice(i, i + 10);

        setMessages((previousMessages) => {

          const updatedMessages = [...previousMessages];

          const lastMessageIndex =
            updatedMessages.length - 1;

          if (
            updatedMessages[lastMessageIndex]?.role === "assistant"
          ) {
            updatedMessages[lastMessageIndex] = {
              ...updatedMessages[lastMessageIndex],
              content: currentText,
            };
          }

          return updatedMessages;
        });

        await new Promise(
          (resolve) => setTimeout(resolve, 10)
        );
      }

    } catch (error) {

      console.error(
        "Chat API error:",
        error
      );


      const errorMessage = {

        role: "assistant",

        content:
          "Sorry, I couldn't process your request. Please make sure the backend is running and the repository has been indexed.",

      };


      setMessages(
        (previousMessages) => [

          ...previousMessages,

          errorMessage,

        ]
      );

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