import {
  FaGithub,
  FaBrain,
  FaComments,
  FaRocket,
} from "react-icons/fa";

function Features() {
  const features = [
    {
      icon: <FaGithub />,
      title: "Repository Intelligence",
      description:
        "Analyze any public GitHub repository and understand its structure, files, dependencies, and codebase without reading everything manually.",
    },
    {
      icon: <FaBrain />,
      title: "AI-Powered Understanding",
      description:
        "Repix processes your codebase and builds a searchable knowledge base before answering your questions.",
    },
    {
      icon: <FaComments />,
      title: "Chat With Your Code",
      description:
        "Ask questions about your repository naturally and get clear, developer-friendly explanations.",
    },
    {
      icon: <FaRocket />,
      title: "Fast Answers",
      description:
        "Find relevant code and understand unfamiliar projects faster without manually searching through hundreds of files.",
    },
  ];

  return (
    <section
      id="features"
      className="container features-section"
    >
      <div className="section-heading">
        <span className="section-eyebrow">
          WHY REPIX?
        </span>

        <h2>
          Understand your codebase.
          <br />
          <span>Without the digging.</span>
        </h2>

        <p>
          Repix turns unfamiliar repositories into something
          you can actually understand and talk to.
        </p>
      </div>

      <div className="features-grid">

        {features.map((feature, index) => (
          <div
            className="feature-card"
            key={index}
          >
            <div className="feature-icon">
              {feature.icon}
            </div>

            <div className="feature-content">
              <h3>{feature.title}</h3>

              <p>
                {feature.description}
              </p>
            </div>
          </div>
        ))}

      </div>
    </section>
  );
}

export default Features;