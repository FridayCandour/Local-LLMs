/** Core Module for Local LLM Chat Interface.
 *
 * Application orchestrator and utility functions.
 * Initializes all modules on DOMContentLoaded.
 */

import { stateStore } from "./state.js";
import {
  initUI,
  initSidebar,
  initComposer,
  renderSessionList,
  updateMessageList,
  addMessage,
  updateMessage,
  showTypingIndicator,
  hideTypingIndicator,
  appendStreamingToken,
  finalizeStreamingMessage,
} from "./ui.js";
import { streamHandler } from "./stream.js";

// API Configuration
const API_BASE_URL = "/api/v1";
const WS_PORT = 8765;

/**
 * Get full API URL for endpoint
 */
export function getApiUrl(endpoint) {
  return `${API_BASE_URL}${endpoint}`;
}

/**
 * Get WebSocket URL for a session
 */
export function getWsUrl(sessionId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const hostname = window.location.hostname;
  return `${protocol}//${hostname}:${WS_PORT}/api/v1/ws/${sessionId}`;
}

/** Generate a unique ID */
export function generateId() {
  return crypto.randomUUID();
}

/** Get current timestamp in seconds */
export function getTimestamp() {
  return Date.now() / 1000;
}

/** Debounce function */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/** Throttle function */
export function throttle(func, limit) {
  let inThrottle;
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/** Format file size for display */
export function formatFileSize(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

/** Show toast notification */
export function showToast(message, type = "info") {
  const container = document.querySelector(".toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("fade-out");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

export function showError(message) {
  showToast(message, "error");
}
export function showSuccess(message) {
  showToast(message, "success");
}
export function showInfo(message) {
  showToast(message, "info");
}

// =============================================================================
// App Bootstrap
// =============================================================================

/** Load sessions from backend and populate state */
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
    // Activate the most recent session
    if (sessions.length > 0) {
      const sorted = [...sessions].sort(
        (a, b) =>
          (b.updated_at || b.created_at || 0) -
          (a.updated_at || a.created_at || 0),
      );
      const activeId = sorted[0].id;
      stateStore.setActiveSession(activeId);
      await loadMessages(activeId);
    }
  } catch (err) {
    console.warn("Failed to load sessions:", err);
  }
}

/** Load messages for a session */
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
    // Store in state
    const session = stateStore.getSession(sessionId);
    if (session) {
      stateStore.updateSession(sessionId, { messages: mapped });
    }
    updateMessageList(mapped);
  } catch (err) {
    console.warn("Failed to load messages:", err);
  }
}

/** Wire up theme toggle */
function initTheme() {
  const saved = localStorage.getItem("theme") || "dark";
  document.body.className = `theme-${saved}`;

  const toggle = document.querySelector(".theme-toggle");
  if (toggle) {
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
}

function updateThemeIcon(btn, theme) {
  const icon = btn.querySelector(".theme-icon");
  if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
  btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
}

/** Wire up settings modal */
function initSettingsModal() {
  const settingsBtn = document.querySelector(".settings-btn");
  const modal = document.getElementById("settings-modal");
  if (!settingsBtn || !modal) return;

  const closeBtn = modal.querySelector(".modal-close");
  const doneBtn = modal.querySelector(".btn-primary");
  const overlay = modal.querySelector(".modal-overlay");

  function openModal() {
    modal.setAttribute("aria-hidden", "false");
  }
  function closeModal() {
    modal.setAttribute("aria-hidden", "true");
  }

  settingsBtn.addEventListener("click", openModal);
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (doneBtn) doneBtn.addEventListener("click", closeModal);
  if (overlay) overlay.addEventListener("click", closeModal);

  // Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
      closeModal();
    }
  });
}

/** Wire up streaming events from WebSocket */
function initStreamEvents() {
  streamHandler.on("token", (data) => {
    const sessionId = stateStore.get("activeSessionId");
    if (!sessionId) return;

    // If this is the first token, create the assistant message placeholder
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

/** Main app initialization */
async function initApp() {
  console.log("Initializing Local LLM Chat Interface...");

  // Theme
  initTheme();

  // UI modules (sidebar, composer, virtual scroll)
  initUI();

  // Settings modal
  initSettingsModal();

  // Stream event handlers
  initStreamEvents();

  // Load data from backend
  await loadSessions();

  console.log("App initialized.");
}

// Boot on DOM ready
document.addEventListener("DOMContentLoaded", initApp);

// Export for use in other modules
export default {
  getApiUrl,
  getWsUrl,
  generateId,
  getTimestamp,
  debounce,
  throttle,
  formatFileSize,
  showToast,
  showError,
  showSuccess,
  showInfo,
};
