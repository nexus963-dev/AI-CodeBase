import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  Prism as SyntaxHighlighter,
} from "react-syntax-highlighter";

import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";


function ChatMessage({ role, content }) {

  const isUser = role === "user";

  const [copiedCode, setCopiedCode] = useState(null);


  // --------------------------------------------------
  // Clean AI response
  // --------------------------------------------------

  const cleanContent = (() => {

    if (!content) {
      return "";
    }

    let text = String(content).trim();


    // Remove unnecessary outer markdown fence.
    const firstFence = text.match(/^```[^\n]*\n/);
    const lastFence = text.match(/\n```\s*$/);

    if (firstFence && lastFence) {

      text = text
        .replace(/^```[^\n]*\n/, "")
        .replace(/\n```\s*$/, "")
        .trim();

    }


    // Remove accidental 4-space indentation.
    text = text
      .split("\n")
      .map((line) => {

        if (line.startsWith("    ")) {
          return line.slice(4);
        }

        return line;

      })
      .join("\n");


    return text.trim();

  })();


  // --------------------------------------------------
  // Copy code
  // --------------------------------------------------

  const handleCopy = async (code, index) => {

    try {

      await navigator.clipboard.writeText(code);

      setCopiedCode(index);

      setTimeout(() => {
        setCopiedCode(null);
      }, 1500);

    } catch (error) {

      console.error(
        "Failed to copy code:",
        error
      );

    }

  };


  return (

    <div
      className={`chat-message ${
        isUser
          ? "user-message"
          : "ai-message"
      }`}
    >

      {/* Avatar */}

      <div className="message-avatar">

        {isUser ? "You" : "✦"}

      </div>


      {/* Message */}

      <div className="message-body">

        {/* Name */}

        <div className="message-name">

          {isUser
            ? "You"
            : "Repix"}

        </div>


        {/* Content */}

        <div className="message-content">

          {isUser ? (

            content

          ) : (

            <ReactMarkdown
              remarkPlugins={[remarkGfm]}

              components={{

                // ------------------------------------
                // Headings
                // ------------------------------------

                h1: ({ children }) => (
                  <h1>{children}</h1>
                ),

                h2: ({ children }) => (
                  <h2>{children}</h2>
                ),

                h3: ({ children }) => (
                  <h3>{children}</h3>
                ),


                // ------------------------------------
                // Paragraphs
                // ------------------------------------

                p: ({ children }) => (
                  <p>{children}</p>
                ),


                // ------------------------------------
                // Lists
                // ------------------------------------

                ul: ({ children }) => (
                  <ul>{children}</ul>
                ),

                ol: ({ children }) => (
                  <ol>{children}</ol>
                ),

                li: ({ children }) => (
                  <li>{children}</li>
                ),


                // ------------------------------------
                // Bold
                // ------------------------------------

                strong: ({ children }) => (
                  <strong>
                    {children}
                  </strong>
                ),


                // ------------------------------------
                // Links
                // ------------------------------------

                a: ({
                  href,
                  children,
                }) => (

                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {children}
                  </a>

                ),


                // ------------------------------------
                // Code
                // ------------------------------------

                code({
                  className,
                  children,
                  ...props
                }) {

                  const match =
                    /language-([\w+-]+)/.exec(
                      className || ""
                    );


                  const code = String(
                    children
                  ).replace(/\n$/, "");


                  /*
                   * ReactMarkdown gives fenced
                   * code blocks a language-* class.
                   */

                  if (match) {

                    const language =
                      match[1];


                    return (

                      <div className="code-block-wrapper">

                        {/* Code header */}

                        <div className="code-block-header">

                          <span className="code-language">

                            {language}

                          </span>


                          <button
                            className="copy-code-btn"

                            onClick={() =>
                              handleCopy(
                                code,
                                code
                              )
                            }
                          >

                            {copiedCode === code
                              ? "Copied!"
                              : "Copy"}

                          </button>

                        </div>


                        {/* Code */}

                        <SyntaxHighlighter
                          style={oneDark}
                          language={language}
                          PreTag="div"
                          className="syntax-highlighter"
                          customStyle={{
                            margin: 0,
                            borderRadius:
                              "0 0 12px 12px",
                          }}
                        >

                          {code}

                        </SyntaxHighlighter>

                      </div>

                    );

                  }


                  /*
                   * Inline code:
                   *
                   * `is_prime`
                   */

                  return (

                    <code
                      className="inline-code"
                      {...props}
                    >
                      {children}
                    </code>

                  );

                },


                // ------------------------------------
                // Blockquotes
                // ------------------------------------

                blockquote: ({
                  children,
                }) => (

                  <blockquote>
                    {children}
                  </blockquote>

                ),


                // ------------------------------------
                // Horizontal rule
                // ------------------------------------

                hr: () => (
                  <hr />
                ),


                // ------------------------------------
                // Tables
                // ------------------------------------

                table: ({
                  children,
                }) => (

                  <div className="markdown-table-wrapper">

                    <table>
                      {children}
                    </table>

                  </div>

                ),

              }}
            >

              {cleanContent}

            </ReactMarkdown>

          )}

        </div>

      </div>

    </div>

  );

}


export default ChatMessage;