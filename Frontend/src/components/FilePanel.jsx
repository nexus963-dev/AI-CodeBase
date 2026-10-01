import { useEffect, useState } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";

import {
  FiArrowLeft,
  FiFileText,
  FiSearch,
  FiX,
} from "react-icons/fi";

const API_URL = import.meta.env.VITE_API_URL;


/*
 * Readability normalization (display only — wording untouched):
 *
 * Models sometimes write section titles as **Purpose**
 * instead of ## Purpose. Promote bold-only lines to real
 * headings so the panel can space the sections properly.
 */
const promoteBoldHeadings = (text) =>
  text.replace(/^\*\*([^*\n]+?)\*\*[ \t]*\r?$/gm, "## $1");


/*
 * FilePanel — Phase 3
 *
 * Drawer that lists every analyzed file (from the manifest)
 * and lets the user ask Repix for:
 *   - a plain-language explanation of the file, or
 *   - prioritized improvement suggestions
 */

function FilePanel({ repositoryName, onClose }) {

  const [files, setFiles] = useState([]);

  const [loadingFiles, setLoadingFiles] = useState(true);

  const [loadError, setLoadError] = useState("");

  const [filterText, setFilterText] = useState("");

  const [selectedFile, setSelectedFile] = useState(null);

  const [result, setResult] = useState(null);

  const [actionLoading, setActionLoading] = useState(null);

  const [actionError, setActionError] = useState("");


  /* ---------------- Load manifest files ---------------- */

  useEffect(() => {

    const loadFiles = async () => {

      if (!repositoryName) {
        setLoadingFiles(false);
        return;
      }

      setLoadingFiles(true);

      try {

        const response = await axios.get(
          `${API_URL}/files`,
          {
            params: {
              repository_name: repositoryName,
            },
          }
        );

        setFiles(response.data.files || []);

        setLoadError("");

      } catch (error) {

        console.error(
          "Failed to load repository files:",
          error
        );

        setLoadError(
          error.response?.data?.detail ||
          "Failed to load repository files."
        );

      } finally {

        setLoadingFiles(false);

      }

    };


    loadFiles();

  }, [repositoryName]);


  /* ---------------- Actions ---------------- */

  const visibleFiles = files.filter((entry) =>
    entry.path
      .toLowerCase()
      .includes(filterText.trim().toLowerCase())
  );


  const selectFile = (entry) => {

    setSelectedFile(entry);

    setResult(null);

    setActionError("");

  };


  const backToList = () => {

    setSelectedFile(null);

    setResult(null);

    setActionError("");

  };


  const runAction = async (type) => {

    if (!selectedFile) {
      return;
    }

    setActionLoading(type);

    setActionError("");

    setResult(null);

    try {

      const response = await axios.post(
        `${API_URL}/files/${type}`,
        {
          repository_name: repositoryName,
          file_path: selectedFile.path,
        }
      );

      const data = response.data;

      setResult({
        type,
        content:
          type === "explain"
            ? data.explanation
            : data.suggestions,
      });

    } catch (error) {

      console.error(
        `File ${type} request failed:`,
        error
      );

      setActionError(
        error.response?.data?.detail ||
        "The request failed. Please try again."
      );

    } finally {

      setActionLoading(null);

    }

  };


  /* ---------------- Render ---------------- */

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

            <FiFileText />

            <h3>Repository Files</h3>

            {files.length > 0 && (
              <span className="file-count">
                {files.length}
              </span>
            )}

          </div>

          <button
            className="file-panel-close"
            onClick={onClose}
            title="Close files"
          >
            <FiX />
          </button>

        </div>


        {/* ---------- List view ---------- */}

        {!selectedFile && (

          <div className="file-list-view">

            <div className="file-search">

              <FiSearch />

              <input
                type="text"
                placeholder="Filter files..."
                value={filterText}
                onChange={(event) =>
                  setFilterText(event.target.value)
                }
              />

            </div>

            <div className="file-list">

              {loadingFiles && (
                <p className="file-list-empty">
                  Loading files...
                </p>
              )}

              {!loadingFiles && loadError && (
                <p className="file-list-empty file-list-error">
                  {loadError}
                </p>
              )}

              {!loadingFiles &&
                !loadError &&
                visibleFiles.length === 0 && (
                  <p className="file-list-empty">
                    No files match.
                  </p>
                )}

              {visibleFiles.map((entry) => (

                <button
                  key={entry.path}
                  className="file-item"
                  onClick={() => selectFile(entry)}
                  title={entry.path}
                >

                  <span className="file-item-type">
                    {entry.type || "file"}
                  </span>

                  <span className="file-item-path">
                    {entry.path}
                  </span>

                  {entry.symbols?.length > 0 && (
                    <span className="file-item-symbols">
                      {entry.symbols.length}
                    </span>
                  )}

                </button>

              ))}

            </div>

          </div>

        )}


        {/* ---------- Detail view ---------- */}

        {selectedFile && (

          <div className="file-detail">

            <button
              className="file-back"
              onClick={backToList}
            >
              <FiArrowLeft />
              All files
            </button>

            <h4 className="file-detail-path">
              {selectedFile.path}
            </h4>

            {selectedFile.symbols?.length > 0 && (
              <div className="file-symbol-chips">
                {selectedFile.symbols
                  .slice(0, 8)
                  .map((symbol, index) => (
                    <span
                      key={`${symbol.name}-${index}`}
                      className="symbol-chip"
                      title={`${symbol.kind} at line ${symbol.line}`}
                    >
                      {symbol.kind === "class"
                        ? "class"
                        : "fn"}{" "}
                      {symbol.name}
                    </span>
                  ))}
              </div>
            )}

            <div className="file-actions">

              <button
                className="file-action-btn"
                onClick={() => runAction("explain")}
                disabled={actionLoading !== null}
              >
                Explain this file
              </button>

              <button
                className="file-action-btn file-action-secondary"
                onClick={() => runAction("suggest")}
                disabled={actionLoading !== null}
              >
                Suggest improvements
              </button>

            </div>

            {actionLoading && (
              <p className="file-result-loading">
                Repix is analyzing{" "}
                <strong>{selectedFile.path}</strong>...
              </p>
            )}

            {actionError && (
              <p className="file-action-error">
                {actionError}
              </p>
            )}

            {result && (

              <div className="file-result">

                <div className="file-result-label">
                  {result.type === "explain"
                    ? "Explanation"
                    : "Improvement suggestions"}
                </div>

                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkBreaks]}
                >
                  {promoteBoldHeadings(result.content)}
                </ReactMarkdown>

              </div>

            )}

          </div>

        )}

      </aside>

    </div>

  );

}


export default FilePanel;
