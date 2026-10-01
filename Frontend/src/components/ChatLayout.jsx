import { useState } from "react";

import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import FilePanel from "./FilePanel";


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
        onOpenFiles={() => setShowFiles(true)}
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

    </div>

  );

}


export default ChatLayout;