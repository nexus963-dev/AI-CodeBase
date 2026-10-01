import { useEffect, useState } from "react";
import axios from "axios";

import {
  FiClock,
  FiExternalLink,
  FiX,
} from "react-icons/fi";

const API_URL = import.meta.env.VITE_API_URL;


/*
 * HistoryPanel — Phase 4b
 *
 * Timeline of the repository's commits (fetched live from
 * GitHub by the Phase 4a endpoint), newest first: who
 * changed what, and when.
 */

const formatDate = (isoDate) => {

  if (!isoDate) {
    return "";
  }

  try {

    return new Date(isoDate).toLocaleDateString(
      undefined,
      {
        year: "numeric",
        month: "short",
        day: "numeric",
      }
    );

  } catch {
    return isoDate;
  }

};


function HistoryPanel({ repositoryName, onClose }) {

  const [commits, setCommits] = useState([]);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState("");


  useEffect(() => {

    const loadHistory = async () => {

      if (!repositoryName) {
        setLoading(false);
        return;
      }

      setLoading(true);

      try {

        const response = await axios.get(
          `${API_URL}/repository/commits`,
          {
            params: {
              repository_name: repositoryName,
              limit: 30,
            },
          }
        );

        setCommits(response.data.commits || []);

        setError("");

      } catch (requestError) {

        console.error(
          "Failed to load commit history:",
          requestError
        );

        setError(
          requestError.response?.data?.detail ||
          "Failed to load commit history."
        );

      } finally {

        setLoading(false);

      }

    };


    loadHistory();

  }, [repositoryName]);


  return (

    <div
      className="file-panel-overlay"
      onClick={onClose}
    >

      <aside
        className="file-panel"
        onClick={(event) => event.stopPropagation()}
      >

        {/* Header */}

        <div className="file-panel-header">

          <div className="file-panel-title">

            <FiClock />

            <h3>Commit History</h3>

            {commits.length > 0 && (
              <span className="file-count">
                {commits.length}
              </span>
            )}

          </div>

          <button
            className="file-panel-close"
            onClick={onClose}
            title="Close history"
          >
            <FiX />
          </button>

        </div>


        {/* ---------- Timeline ---------- */}

        <div className="history-list">

          {loading && (
            <p className="file-list-empty">
              Loading history...
            </p>
          )}

          {!loading && error && (
            <p className="file-list-empty file-list-error">
              {error}
            </p>
          )}

          {!loading && !error && commits.length === 0 && (
            <p className="file-list-empty">
              No commits found for this repository.
            </p>
          )}

          {!loading && !error && commits.map((commit) => (

            <div
              key={commit.sha}
              className="history-item"
            >

              {/* Timeline rail */}

              <div className="history-rail">
                <span className="history-dot" />
              </div>


              {/* Commit details */}

              <div className="history-body">

                {commit.url ? (

                  <a
                    className="history-title"
                    href={commit.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {commit.title}
                    <FiExternalLink />
                  </a>

                ) : (

                  <span className="history-title">
                    {commit.title}
                  </span>

                )}

                <div className="history-meta">

                  {commit.avatar ? (

                    <img
                      className="history-avatar"
                      src={commit.avatar}
                      alt=""
                    />

                  ) : (

                    <span className="history-avatar history-avatar-fallback">
                      {(commit.author || "?")
                        .charAt(0)
                        .toUpperCase()}
                    </span>

                  )}

                  <span>{commit.author}</span>

                  <span className="history-sep">•</span>

                  <span>{formatDate(commit.date)}</span>

                  <span className="history-sha">
                    {commit.sha}
                  </span>

                </div>

                {commit.body && (
                  <p className="history-message">
                    {commit.body}
                  </p>
                )}

              </div>

            </div>

          ))}

        </div>

      </aside>

    </div>

  );

}


export default HistoryPanel;
