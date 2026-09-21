import { useEffect, useState } from "react";
import axios from "axios";

import {
  FiFolder,
  FiLayers,
  FiGitBranch,
} from "react-icons/fi";

import { BsStars } from "react-icons/bs";

const API_URL = import.meta.env.VITE_API_URL;

function Sidebar({
  repositoryName,
  chunkCount,
  language,
  branch,
  license,
  activeSessionId,
  onSelectSession,
  onNewChat,
  refreshKey,
}) {

  const [sessions, setSessions] = useState([]);

  const [loadingSessions, setLoadingSessions] =
    useState(false);


  useEffect(() => {

    const loadSessions = async () => {

      if (!repositoryName) {
        return;
      }

      setLoadingSessions(true);

      try {

        const response = await axios.get(
          `${API_URL}/chat/sessions`,
          {
            params: {
              repository_name: repositoryName,
            },
          }
        );

        setSessions(response.data);

      } catch (error) {

        console.error(
          "Failed to load chat sessions:",
          error
        );

      } finally {

        setLoadingSessions(false);

      }

    };


    loadSessions();

  }, [repositoryName, refreshKey]);


  return (

    <aside className="sidebar">

      <div>

        {/* Logo */}

        <div className="sidebar-logo">

          <span>✦</span>

          <h2>Repix</h2>

        </div>


        {/* Repository */}

        <div className="repository-card-side">

          <div className="repo-icon">
            <FiFolder />
          </div>

          <h3 title={repositoryName}>
            {repositoryName || "Repository"}
          </h3>

          <div className="repo-status">

            <span className="status-dot"></span>

            AI Ready

          </div>

        </div>


        {/* Repository statistics */}

        <div className="repo-stats">

          <div>

            <FiLayers />

            <span>
              {chunkCount || 0} Chunks
            </span>

          </div>


          <div>

            🐍

            <span>
              {language || "Unknown"}
            </span>

          </div>


          <div>

            <FiGitBranch />

            <span>
              {branch || "Unknown"}
            </span>

          </div>


          <div>

            ⚖

            <span>
              {license || "No License"}
            </span>

          </div>

        </div>


        {/* Chat history */}
        <div className="chat-history">

          <div className="chat-history-header">
            <span>Recent Chats</span>
            {sessions.length > 0 && (
              <span className="chat-count">
                {sessions.length}
              </span>
            )}
          </div>

          <div className="chat-history-list">

            {loadingSessions && (
              <p className="chat-history-empty">
                Loading chats...
              </p>
            )}

            {!loadingSessions &&
              sessions.length === 0 && (
                <p className="chat-history-empty">
                  No previous chats
                </p>
              )}

            {!loadingSessions &&
              sessions.map((session) => (
                <button
                  key={session.id}
                  className={
                    `chat-session-item ${
                      activeSessionId === session.id
                        ? "active"
                        : ""
                    }`
                  }
                  onClick={() =>
                    onSelectSession(session.id)
                  }
                  title={session.title}
                >

                  <span className="chat-session-icon">
                    ◇
                  </span>

                  <span className="chat-session-title">
                    {session.title || "New Chat"}
                  </span>

                </button>
              ))}

          </div>
        </div>

      </div>


      {/* Bottom section */}

      <div>

        <button
          className="new-chat-btn"
          onClick={onNewChat}
        >

          <BsStars />

          New Chat

        </button>


        <p className="sidebar-footer">

          Made with ❤️

        </p>

      </div>

    </aside>

  );

}


export default Sidebar;