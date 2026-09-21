import { useEffect, useState } from "react";

import {
  FiSearch,
  FiFolder,
  FiCpu,
} from "react-icons/fi";

import { BsStars } from "react-icons/bs";


const steps = [
  {
    icon: <FiSearch />,
    text: "Repository connected",
  },
  {
    icon: <FiFolder />,
    text: "Files analyzed",
  },
  {
    icon: <FiCpu />,
    text: "Code chunks created",
  },
  {
    icon: <BsStars />,
    text: "Embeddings generated",
  },
  {
    icon: <BsStars />,
    text: "AI knowledge base ready",
  },
];


function LoadingSequence({ onComplete }) {

  const [currentStep, setCurrentStep] = useState(0);

  const percentages = [
    20,
    40,
    60,
    80,
    100,
  ];


  /*
   * Move through loading stages.
   */

  useEffect(() => {

    if (currentStep >= steps.length - 1) {
      return;
    }

    const timer = setTimeout(() => {

      setCurrentStep(
        (previousStep) => previousStep + 1
      );

    }, 900);

    return () => clearTimeout(timer);

  }, [currentStep]);


  /*
   * When 100% is reached,
   * notify RepositoryInput.
   */

  useEffect(() => {

    if (currentStep !== steps.length - 1) {
      return;
    }

    console.log(
      "LoadingSequence: 100% reached."
    );

    const timer = setTimeout(() => {

      console.log(
        "LoadingSequence: calling onComplete."
      );

      if (onComplete) {
        onComplete();
      }

    }, 700);

    return () => clearTimeout(timer);

  }, [currentStep]);


  return (

    <div className="loading-card">


      {/* Header */}

      <div className="loading-header">

        <div className="loading-logo">

          <BsStars />

        </div>


        <h2>
          Analyzing Repository
        </h2>


        <span className="loading-percent">

          {percentages[currentStep]}%

        </span>

      </div>


      {/* Steps */}

      {steps.map((step, index) => (

        <div
          key={index}
          className={`loading-step ${
            index <= currentStep
              ? "active"
              : ""
          }`}
        >

          <div className="step-header">

            <span className="step-icon">

              {step.icon}

            </span>


            <p>
              {step.text}
            </p>


            {index <= currentStep && (

              <span className="step-check">
                ✓
              </span>

            )}

          </div>


          {index <= currentStep && (

            <div className="progress-line">

              <div className="progress-fill"></div>

            </div>

          )}

        </div>

      ))}


      {/* Footer */}

      <div className="loading-footer">

        <p>
          Estimated time: ~10 seconds
        </p>

        <span>
          Preparing intelligent answers...
        </span>

      </div>


    </div>

  );

}


export default LoadingSequence;