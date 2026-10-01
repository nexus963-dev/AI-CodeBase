import { useState } from "react";

import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import FilePanel from "./FilePanel";
import HistoryPanel from "./HistoryPanel";


function ChatLayout({
  repositoryName,
  chunkCount,
  language,
  branch,
  license,
}) {

  const [activeSessionId, setActiveSessionId] = useState(null);

  const [sessionsRefreshKey, setSessionsRefreshKey] = useState(0);

  const [showFiles, setShowFiles] = useState(false);

  const [showHistory, setShowHistory] = useState(false);


  const handleSessionCreated = (sessionId) => {

    setActiveSessionId(sessionId);

    setSessionsRefreshKey(
      (previous) => previous + 1
    );

  };


  const handleNewChat = () => {

    setActiveSessionId(null);

  };


  return (

    <div className="chat-layout">

      <Sidebar
        repositoryName={repositoryName}
        chunkCount={chunkCount}
        language={language}
        branch={branch}
        license={license}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSessionId}
        onNewChat={handleNewChat}
        onOpenFiles={() => {
          setShowHistory(false);
          setShowFiles(true);
        }}
        onOpenHistory={() => {
          setShowFiles(false);
          setShowHistory(true);
        }}
        refreshKey={sessionsRefreshKey}
      />

      <ChatWindow
        repositoryName={repositoryName}
        sessionId={activeSessionId}
        onSessionCreated={handleSessionCreated}
      />

      {showFiles && (
        <FilePanel
          repositoryName={repositoryName}
          onClose={() => setShowFiles(false)}
        />
      )}

      {showHistory && (
        <HistoryPanel
          repositoryName={repositoryName}
          onClose={() => setShowHistory(false)}
        />
      )}

    </div>

  );

}


export default ChatLayout;