/** App Entry Point - Bootstraps the Local LLM Chat Interface. */

import { getApiUrl, getTimestamp, showError, showInfo, showSuccess } from "./core.js";
import { stateStore } from "./state.js";
import {
  initUI,
  updateMessageList,
  addMessage,
  showTypingIndicator,
  hideTypingIndicator,
  appendStreamingToken,
  finalizeStreamingMessage,
} from "./ui.js";
import { streamHandler } from "./stream.js";

// =============================================================================
// Data Loading
// =============================================================================

async function loadSessions() {
  try {
    const res = await fetch(getApiUrl("/sessions"));
    if (!res.ok) return;
    const data = await res.json();
    const sessions = data.sessions || data || [];
    sessions.forEach((s) => {
      stateStore.addSession({
        id: s.id,
        name: s.name || "Untitled",
        createdAt: s.created_at || s.createdAt || 0,
        updatedAt: s.updated_at || s.updatedAt || 0,
        messages: [],
        llmConfig: {},
        contextTokens: 0,
        isTyping: false,
      });
    });
    if (sessions.length > 0) {
      const sorted = [...sessions].sort(
        (a, b) =>
          (b.updated_at || b.created_at || 0) -
          (a.updated_at || a.created_at || 0),
      );
      stateStore.setActiveSession(sorted[0].id);
      await loadMessages(sorted[0].id);
    }
  } catch (err) {
    console.warn("Failed to load sessions:", err);
  }
}

async function loadMessages(sessionId) {
  try {
    const res = await fetch(getApiUrl(`/sessions/${sessionId}/messages`));
    if (!res.ok) return;
    const data = await res.json();
    const messages = data.messages || data || [];
    const mapped = messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      status: "complete",
      timestamp: m.created_at || m.createdAt || 0,
      createdAt: m.created_at || m.createdAt || 0,
    }));
    const session = stateStore.getSession(sessionId);
    if (session) {
      stateStore.updateSession(sessionId, { messages: mapped });
    }
    updateMessageList(mapped);
  } catch (err) {
    console.warn("Failed to load messages:", err);
  }
}

// =============================================================================
// Theme
// =============================================================================

function initTheme() {
  const saved = localStorage.getItem("theme") || "dark";
  document.body.className = `theme-${saved}`;

  const toggle = document.querySelector(".theme-toggle");
  if (!toggle) return;

  updateThemeIcon(toggle, saved);
  toggle.addEventListener("click", () => {
    const current = document.body.classList.contains("theme-dark")
      ? "dark"
      : "light";
    const next = current === "dark" ? "light" : "dark";
    document.body.className = `theme-${next}`;
    localStorage.setItem("theme", next);
    updateThemeIcon(toggle, next);
  });
}

function updateThemeIcon(btn, theme) {
  const icon = btn.querySelector(".theme-icon");
  if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
  btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
}

// =============================================================================
// Settings Modal
// =============================================================================

function initSettingsModal() {
  const settingsBtn = document.querySelector(".settings-btn");
  const modal = document.getElementById("settings-modal");
  if (!settingsBtn || !modal) return;

  const closeBtn = modal.querySelector(".modal-close");
  const doneBtn = modal.querySelector(".btn-primary");
  const overlay = modal.querySelector(".modal-overlay");

  const open = () => modal.setAttribute("aria-hidden", "false");
  const close = () => modal.setAttribute("aria-hidden", "true");

  settingsBtn.addEventListener("click", open);
  if (closeBtn) closeBtn.addEventListener("click", close);
  if (doneBtn) doneBtn.addEventListener("click", close);
  if (overlay) overlay.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
      close();
    }
  });
}

// =============================================================================
// Streaming Events
// =============================================================================

function initStreamEvents() {
  streamHandler.on("token", (data) => {
    const sessionId = stateStore.get("activeSessionId");
    if (!sessionId) return;

    const msgId = data.messageId;
    const existing = document.querySelector(`[data-message-id="${msgId}"]`);
    if (!existing) {
      addMessage({
        id: msgId,
        role: "assistant",
        content: "",
        status: "streaming",
        timestamp: getTimestamp(),
        createdAt: getTimestamp(),
      });
      showTypingIndicator();
    }
    appendStreamingToken(msgId, data.token);
  });

  streamHandler.on("complete", (data) => {
    finalizeStreamingMessage(data.messageId, data.content || "");
    hideTypingIndicator();
  });

  streamHandler.on("error", (data) => {
    hideTypingIndicator();
    showError(data.message || "LLM error occurred");
  });
}

// =============================================================================
// Init
// =============================================================================

async function initApp() {
  console.log("Initializing Local LLM Chat Interface...");
  initTheme();
  initUI();
  initSettingsModal();
  initStreamEvents();
  await loadSessions();
  console.log("App initialized.");
}

document.addEventListener("DOMContentLoaded", initApp);
