import {
  FaLink,
  FaFolderOpen,
  FaCode,
  FaComments,
} from "react-icons/fa";

function HowItWorks() {
  const steps = [
    {
      number: "01",
      icon: <FaLink />,
      title: "Connect Repository",
      description:
        "Paste any public GitHub repository URL and let Repix connect to your codebase.",
    },
    {
      number: "02",
      icon: <FaFolderOpen />,
      title: "Analyze the Code",
      description:
        "Repix explores your files, project structure, dependencies, and source code.",
    },
    {
      number: "03",
      icon: <FaCode />,
      title: "Build AI Knowledge",
      description:
        "Your code is transformed into searchable knowledge so relevant context can be retrieved instantly.",
    },
    {
      number: "04",
      icon: <FaComments />,
      title: "Start Chatting",
      description:
        "Ask questions naturally and get explanations based on the actual code in your repository.",
    },
  ];

  return (
    <section
      id="how-it-works"
      className="container how-it-works-section"
    >
      <div className="section-heading">
        <span className="section-eyebrow">
          HOW IT WORKS?
        </span>

        <h2>
          From repository
          <br />
          <span>to understanding.</span>
        </h2>

        <p>
          Repix takes care of the heavy lifting so you can
          focus on understanding and working with your code.
        </p>
      </div>

      <div className="how-it-works-grid">

        {steps.map((step, index) => (
          <div
            className="workflow-step"
            key={step.number}
          >
            <div className="workflow-number">
              {step.number}
            </div>

            <div className="workflow-icon">
              {step.icon}
            </div>

            <h3>
              {step.title}
            </h3>

            <p>
              {step.description}
            </p>

            {index < steps.length - 1 && (
              <div className="workflow-connector" />
            )}
          </div>
        ))}

      </div>
    </section>
  );
}

export default HowItWorks;