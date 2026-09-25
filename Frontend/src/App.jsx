import { useEffect, useState } from "react";

import Navbar from "./components/Navbar";
import Hero from "./components/Hero";
import RepositoryInput from "./components/RepositoryInput";
import Features from "./components/Features";
import HowItWorks from "./components/HowItWorks";
import Footer from "./components/Footer";
import AuroraBackground from "./components/AuroraBackground";
import ChatLayout from "./components/ChatLayout";


function App() {

  const [repositoryName, setRepositoryName] = useState(
    () => localStorage.getItem("repositoryName")
  );

  const [chunkCount, setChunkCount] = useState(
    () => localStorage.getItem("chunkCount")
  );

  const [language, setLanguage] = useState(
    () => localStorage.getItem("repositoryLanguage")
  );

  const [branch, setBranch] = useState(
    () => localStorage.getItem("repositoryBranch")
  );

  const [license, setLicense] = useState(
    () => localStorage.getItem("repositoryLicense")
  );

  const [showChat, setShowChat] = useState(false);


  /*
   * Debug repository state
   */

  useEffect(() => {

    console.log(
      "Current repository:",
      repositoryName
    );

    console.log(
      "Chunk count:",
      chunkCount
    );

    console.log(
      "Language:",
      language
    );

    console.log(
      "Branch:",
      branch
    );

    console.log(
      "License:",
      license
    );

    console.log(
      "Show chat:",
      showChat
    );

  }, [
    repositoryName,
    chunkCount,
    language,
    branch,
    license,
    showChat,
  ]);


  /*
   * Called after:
   *
   * 1. Backend analysis is complete
   * 2. Loading animation reaches 100%
   */

  const handleRepositoryAnalyzed = ({
    repositoryName,
    chunkCount,
    language,
    branch,
    license,
  }) => {

    console.log(
      "Analyzed repository:",
      repositoryName
    );

    console.log(
      "Chunk count:",
      chunkCount
    );

    console.log(
      "Language:",
      language
    );

    console.log(
      "Branch:",
      branch
    );

    console.log(
      "License:",
      license
    );


    /*
     * Update React state
     */

    setRepositoryName(repositoryName);

    setChunkCount(chunkCount);

    setLanguage(language);

    setBranch(branch);

    setLicense(license);


    /*
     * Open chat interface
     */

    console.log(
      "Opening ChatLayout..."
    );

    setShowChat(true);

  };


  /*
   * CHAT PAGE
   *
   * Once repository analysis is complete,
   * show the repository chat interface.
   */

  if (showChat && repositoryName) {

    return (
      <>
        <AuroraBackground />

        <ChatLayout
          repositoryName={repositoryName}
          chunkCount={chunkCount}
          language={language}
          branch={branch}
          license={license}
        />
      </>
    );

  }


  /*
   * Open the chat directly from the Navbar
   * (resume a previously analyzed repository).
   */

  const handleOpenChat = () => {

    if (repositoryName) {
      setShowChat(true);
    }

  };


  /*
   * HOME PAGE
   */

  return (
    <>
      <AuroraBackground />

      <Navbar
        hasRepository={Boolean(repositoryName)}
        onOpenChat={handleOpenChat}
      />

      <Hero />

      <RepositoryInput
        onRepositoryAnalyzed={
          handleRepositoryAnalyzed
        }
      />

      <Features />

      <HowItWorks />

      <Footer />
    </>
  );

}


export default App;