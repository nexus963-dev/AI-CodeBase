import { useEffect, useState } from "react";
import { FiGithub } from "react-icons/fi";
import LoadingSequence from "./LoadingSequence";

const API_URL = import.meta.env.VITE_API_URL;

function RepositoryInput({ onRepositoryAnalyzed }) {

  const repositories = [
    "https://github.com/vercel/next.js",
    "https://github.com/facebook/react",
    "https://github.com/openai/openai-python",
    "https://github.com/langchain-ai/langchain",
    "https://github.com/microsoft/vscode",
  ];

  const [placeholder, setPlaceholder] = useState(repositories[0]);
  const [repoUrl, setRepoUrl] = useState("");

  const [loading, setLoading] = useState(false);

  // Backend analysis completed
  const [analysisComplete, setAnalysisComplete] =
    useState(false);

  // Loading animation reached 100%
  const [loadingSequenceComplete, setLoadingSequenceComplete] =
    useState(false);

  // Repository metadata returned by backend
  const [analysisData, setAnalysisData] =
    useState(null);

  const [error, setError] = useState("");


  /*
   * Rotating placeholder URLs
   */

  useEffect(() => {

    let index = 0;

    const interval = setInterval(() => {

      index = (index + 1) % repositories.length;

      setPlaceholder(repositories[index]);

    }, 2500);

    return () => clearInterval(interval);

  }, []);


  /*
   * IMPORTANT:
   *
   * Open Chat ONLY when BOTH:
   *
   * 1. Backend analysis is complete
   * 2. Loading animation has reached 100%
   */

  useEffect(() => {

    if (
      !loading ||
      !analysisComplete ||
      !loadingSequenceComplete ||
      !analysisData
    ) {
      return;
    }

    console.log(
      "Backend analysis complete."
    );

    console.log(
      "Loading animation complete."
    );

    console.log(
      "Opening Chat..."
    );


    if (onRepositoryAnalyzed) {

      onRepositoryAnalyzed({

        repositoryName:
          analysisData.repositoryName,

        chunkCount:
          analysisData.chunkCount,

        language:
          analysisData.language,

        branch:
          analysisData.branch,

        license:
          analysisData.license,

      });

    }

    /*
     * Stop loading only after
     * everything is completely finished.
     */

    setLoading(false);

  }, [
    loading,
    analysisComplete,
    loadingSequenceComplete,
    analysisData,
    onRepositoryAnalyzed,
  ]);


  /*
   * Analyze Repository
   */

  const handleAnalyzeRepository = async () => {

    const url = repoUrl.trim();


    /*
     * Validate URL
     */

    if (!url) {

      setError(
        "Please enter a GitHub repository URL."
      );

      return;

    }


    if (!url.startsWith("https://github.com/")) {

      setError(
        "Please enter a valid GitHub repository URL."
      );

      return;

    }


    /*
     * Reset previous state
     */

    setError("");

    setLoading(true);

    setAnalysisComplete(false);

    setLoadingSequenceComplete(false);

    setAnalysisData(null);


    try {

      console.log(
        "Starting repository analysis..."
      );


      /*
       * Call backend
       */

const response = await fetch(
  `${API_URL}/analyze-repository`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            repo_url: url,
          }),

        }
      );


      const data = await response.json();


      /*
       * Handle backend error
       */

      if (!response.ok) {

        throw new Error(
          data.detail ||
          "Repository analysis failed."
        );

      }


      console.log(
        "Repository analyzed:",
        data
      );


      /*
       * Extract repository metadata
       */

      const repositoryName =
        data.repository_name;

      const chunkCount =
        data.chunk_count;

      const language =
        data.language;

      const branch =
        data.branch;

      const license =
        data.license;


      /*
       * Save metadata
       */

      localStorage.setItem(
        "repositoryName",
        repositoryName
      );

      localStorage.setItem(
        "chunkCount",
        chunkCount
      );

      localStorage.setItem(
        "repositoryLanguage",
        language
      );

      localStorage.setItem(
        "repositoryBranch",
        branch
      );

      localStorage.setItem(
        "repositoryLicense",
        license
      );


      /*
       * Store analysis data.
       *
       * We DON'T open Chat here.
       *
       * The loading animation must also
       * reach 100%.
       */

      setAnalysisData({

        repositoryName,

        chunkCount,

        language,

        branch,

        license,

      });


      /*
       * Backend is now complete.
       */

      setAnalysisComplete(true);


      console.log(
        "Backend analysis finished. Waiting for loading sequence..."
      );


    } catch (error) {

      console.error(
        "Repository analysis error:",
        error
      );


      /*
       * Stop loading on actual error.
       */

      setLoading(false);

      setAnalysisComplete(false);

      setLoadingSequenceComplete(false);

      setAnalysisData(null);


      setError(
        error.message ||
        "Unable to analyze the repository."
      );

    }

  };


  /*
   * Loading screen
   */

  if (loading) {

    return (

      <section className="container">

        <LoadingSequence
          onComplete={() => {

            console.log(
              "RepositoryInput: Loading sequence complete."
            );

            setLoadingSequenceComplete(true);

          }}
        />

      </section>

    );

  }


  /*
   * Normal Repository Input
   */

  return (
    <section
      id="repository-input"
      className="container repository-section"
    >
      <div className="repository-card">

        <div className="repository-header">

          <div className="repository-icon">
            <FiGithub />
          </div>

          <div>
            <h2>
              Analyze Any GitHub Repository
            </h2>

            <p>
              Paste a public GitHub repository URL and let Repix
              understand the complete codebase before answering
              your questions.
            </p>
          </div>

        </div>

        <div className="repository-input-wrapper">

          <input
            type="text"
            value={repoUrl}
            onChange={(event) =>
              setRepoUrl(event.target.value)
            }
            placeholder={placeholder}
          />

        </div>

        {error && (
          <p className="repository-error">
            {error}
          </p>
        )}

        <div className="repository-footer">

          <div className="repository-note">
            ✓ Supports any public GitHub repository
          </div>

          <button
            onClick={handleAnalyzeRepository}
          >
            Start Understanding
          </button>

        </div>

      </div>
    </section>
  );
}

export default RepositoryInput;