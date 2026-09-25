function Hero({ children }) {
  return (
    <section className="hero container">

      <div className="hero-content">

        <div className="hero-badge">
          ✨ AI-powered Repository Intelligence
        </div>

        <h1 className="hero-title">
          Every Repository
          <br />
          Has a Story.
          <br />
          <span>Repix Helps You Read It.</span>
        </h1>

        <p className="hero-description">
          Paste any public GitHub repository.
          Repix understands your project structure,
          learns the architecture, and lets you
          chat with your code naturally.
        </p>

        <div className="hero-input">
          {children}
        </div>

        <div className="hero-tech">

          <span>React</span>

          <span>Python</span>

          <span>FastAPI</span>

          <span>Gemini AI</span>

          <span>Open Source</span>

        </div>

      </div>

    </section>
  );
}

export default Hero;