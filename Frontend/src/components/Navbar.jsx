import { FaGithub } from "react-icons/fa";
import { FiMessageSquare } from "react-icons/fi";

function Navbar({ hasRepository = false, onOpenChat }) {
  return (
    <header className="navbar-wrapper">

      <nav className="navbar glass container">

        <div className="logo">
          <span className="logo-icon">✦</span>
          <span>Repix</span>
        </div>

        <ul className="nav-links">

          <li>
            <a href="#features">
              Features
            </a>
          </li>

          <li>
            <a href="#how-it-works">
              How it Works
            </a>
          </li>

          <li>
            <a
              href="https://github.com/Akshitagupta299/AI-GitHub-Repository-Assistant.git"
              target="_blank"
              rel="noreferrer"
              aria-label="GitHub Repository"
            >
              <FaGithub />
            </a>
          </li>

        </ul>

      <div className="nav-actions">

        {hasRepository && (
          <button
            className="nav-chats-btn"
            onClick={onOpenChat}
            title="Resume your repository chat"
          >
            <FiMessageSquare />
            My Chats
          </button>
        )}

      <button
        className="nav-btn"
        onClick={() => {
          document
            .getElementById("repository-input")
            ?.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
        }}
      >
        Start Exploring →
      </button>

      </div>

      </nav>

    </header>
  );
}

export default Navbar;