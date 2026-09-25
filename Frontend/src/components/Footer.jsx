import {
  FaGithub,
  FaLinkedin,
} from "react-icons/fa";

function Footer() {
  return (
    <footer className="footer-section">

      <div className="footer-container">

        {/* Main footer content */}
        <div className="footer-main">

          {/* Brand */}
          <div className="footer-brand">

            <div className="footer-logo">
              <span>✦</span>
              <span>Repix</span>
            </div>

            <p>
              Talk to any GitHub repository.
              Understand your codebase faster
              with AI-powered repository intelligence.
            </p>

            <div className="footer-socials">

              <a
                href="https://github.com/Akshitagupta299/AI-GitHub-Repository-Assistant"
                target="_blank"
                rel="noreferrer"
                aria-label="GitHub"
              >
                <FaGithub />
              </a>

              <a
                href="https://www.linkedin.com/"
                target="_blank"
                rel="noreferrer"
                aria-label="LinkedIn"
              >
                <FaLinkedin />
              </a>

            </div>

          </div>


          {/* Product navigation */}
          <div className="footer-column">

            <h4>Product</h4>

            <a href="#features">
              Features
            </a>

            <a href="#how-it-works">
              How It Works
            </a>

            <a href="#repository">
              Analyze Repository
            </a>

          </div>


          {/* Technology */}
          <div className="footer-column">

            <h4>Built With</h4>

            <span>React</span>
            <span>FastAPI</span>
            <span>ChromaDB</span>
            <span>Gemini AI</span>

          </div>

        </div>


        {/* Divider */}
        <div className="footer-divider"></div>


        {/* Bottom footer */}
        <div className="footer-bottom">

          <span>
            © {new Date().getFullYear()} Repix. All rights reserved.
          </span>

          <span className="footer-made-with">
            Built for developers who want to understand code faster.
          </span>

        </div>

      </div>

    </footer>
  );
}

export default Footer;