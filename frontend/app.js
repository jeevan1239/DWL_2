const summarizeForm = document.getElementById("summarize-form");
const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatLog = document.getElementById("chat-log");

let sessionId = null;
const apiBase =
  document.querySelector('meta[name="api-base"]')?.content ||
  "http://localhost:8000";

const setStatus = (message) => {
  statusEl.textContent = message;
};

const addMessage = (text, role) => {
  const message = document.createElement("div");
  message.className = `chat-message ${role}`;
  message.textContent = text;
  chatLog.appendChild(message);
  chatLog.scrollTop = chatLog.scrollHeight;
};

summarizeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = document.getElementById("site-url").value.trim();
  if (!url) return;

  summarizeForm.querySelector("button").disabled = true;
  setStatus("Scanning the website and preparing a summary...");
  summaryEl.textContent = "";
  chatLog.innerHTML = "";

  try {
    const response = await fetch(`${apiBase}/api/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) {
      if (contentType.includes("application/json")) {
        const err = await response.json();
        throw new Error(err.detail || "Unable to summarize the website.");
      }
      throw new Error(
        "Backend did not return JSON. Is the API running on http://localhost:8000?"
      );
    }

    if (!contentType.includes("application/json")) {
      throw new Error(
        "Backend did not return JSON. Is the API running on http://localhost:8000?"
      );
    }

    const data = await response.json();
    sessionId = data.session_id;
    summaryEl.textContent = data.summary;
    setStatus(`Summary ready. Pages crawled: ${data.pages_crawled}.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    summarizeForm.querySelector("button").disabled = false;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = chatInput.value.trim();
  if (!question || !sessionId) return;

  addMessage(question, "user");
  chatInput.value = "";

  try {
    const response = await fetch(`${apiBase}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, question }),
    });

    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) {
      if (contentType.includes("application/json")) {
        const err = await response.json();
        throw new Error(err.detail || "Unable to answer the question.");
      }
      throw new Error(
        "Backend did not return JSON. Is the API running on http://localhost:8000?"
      );
    }

    if (!contentType.includes("application/json")) {
      throw new Error(
        "Backend did not return JSON. Is the API running on http://localhost:8000?"
      );
    }

    const data = await response.json();
    addMessage(data.answer, "assistant");
  } catch (error) {
    addMessage(`Error: ${error.message}`, "assistant");
  }
});
