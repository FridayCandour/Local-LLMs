/** UI Module for Local LLM Chat Interface.
 *
 * DOM manipulation, rendering, and user interaction handling.
 * Implements virtualized scrolling for efficient message display.
 */

import {
  generateId,
  getTimestamp,
  getApiUrl,
  debounce,
  throttle,
  formatFileSize,
  showToast,
  showSuccess,
  showError,
  showInfo,
} from "./core.js";
import { stateStore } from "./state.js";
import { streamHandler } from "./stream.js";
import { validateFile, generatePreview } from "./uploader.js";

// Virtual Scroll Configuration
const MESSAGE_LIST_SELECTOR = ".message-list";
const MESSAGES_CONTAINER_SELECTOR = ".messages-container";
const MESSAGE_ITEM_SELECTOR = ".message";
const BUFFER_SIZE = 10; // Messages above and below visible area
const HEIGHT_CACHE_TTL = 30000; // 30 seconds
const SCROLL_DEBOUNCE_MS = 16; // ~60fps

/**
 * Virtual Scroll Manager for message list
 * Implements efficient rendering with buffer zones and height caching
 */
class VirtualScrollManager {
  constructor(containerSelector, itemSelector) {
    this.container = document.querySelector(containerSelector);
    this.itemSelector = itemSelector;
    this.scrollHeight = 0;
    this.visibleMessages = [];
    this.heightCache = new Map();
    this.messageHeights = new Map();
    this.viewportHeight = 0;
    this.scrollTop = 0;
    this.totalMessages = 0;
    this.messageHeightEstimate = 100; // Initial estimate in pixels
    this.isInitialized = false;
    this.renderedMessages = new Map();

    this._onScroll = this._onScroll.bind(this);
    this._updateVisibleRange = this._updateVisibleRange.bind(this);
    this._debouncedUpdate = debounce(
      this._updateVisibleRange,
      SCROLL_DEBOUNCE_MS,
    );
  }

  /**
   * Initialize virtual scroll
   */
  init() {
    if (!this.container) {
      console.error("VirtualScrollManager: Container not found");
      return;
    }

    this.viewportHeight = this.container.clientHeight;
    this.container.addEventListener("scroll", this._onScroll, {
      passive: true,
    });
    this.isInitialized = true;

    // Measure existing messages
    this._measureExistingMessages();
  }

  /**
   * Measure heights of existing messages in DOM
   */
  _measureExistingMessages() {
    const messages = this.container.querySelectorAll(this.itemSelector);
    messages.forEach((msg) => {
      const id = msg.dataset.messageId;
      if (id) {
        const height = msg.offsetHeight;
        this.messageHeights.set(id, height);
        this.heightCache.set(id, {
          height,
          timestamp: Date.now(),
        });
      }
    });
  }

  /**
   * Set total message count
   * @param {number} count - Total number of messages
   */
  setTotalMessages(count) {
    this.totalMessages = count;
    this._recalculateScrollHeight();
  }

  /**
   * Recalculate total scroll height
   */
  _recalculateScrollHeight() {
    if (this.totalMessages === 0) {
      this.scrollHeight = 0;
      return;
    }

    // Calculate height from cached measurements
    let cachedHeight = 0;
    let estimatedCount = 0;

    for (const [id, height] of this.messageHeights) {
      cachedHeight += height;
      estimatedCount++;
    }

    // Estimate remaining messages
    const remainingCount = this.totalMessages - estimatedCount;
    const estimatedHeight = remainingCount * this.messageHeightEstimate;

    this.scrollHeight = cachedHeight + estimatedHeight;
    this.container.style.height = `${this.scrollHeight}px`;
  }

  /**
   * Get visible range based on scroll position
   * @returns {Object} { startIndex, endIndex, visibleMessages }
   */
  getVisibleRange() {
    const scrollTop = this.container.scrollTop;
    const viewportHeight = this.container.clientHeight;

    if (viewportHeight === 0) {
      return { startIndex: 0, endIndex: 0, visibleMessages: [] };
    }

    // Binary search to find visible range
    let cumulativeHeight = 0;
    let startIndex = 0;
    let endIndex = 0;

    for (let i = 0; i < this.totalMessages; i++) {
      const height = this._getMessageHeight(i);
      cumulativeHeight += height;

      if (startIndex === 0 && cumulativeHeight > scrollTop) {
        startIndex = i;
      }

      if (cumulativeHeight > scrollTop + viewportHeight) {
        endIndex = i;
        break;
      }
    }

    // Add buffer zones
    const bufferStart = Math.max(0, startIndex - BUFFER_SIZE);
    const bufferEnd = Math.min(this.totalMessages - 1, endIndex + BUFFER_SIZE);

    return {
      startIndex: bufferStart,
      endIndex: bufferEnd,
      visibleMessages: this.visibleMessages.slice(bufferStart, bufferEnd + 1),
    };
  }

  /**
   * Get estimated height for a message at index
   * @param {number} index - Message index
   * @returns {number} Estimated height in pixels
   */
  _getMessageHeight(index) {
    // Try to get from cache first
    const cached = this.heightCache.get(index);
    if (cached && Date.now() - cached.timestamp < HEIGHT_CACHE_TTL) {
      return cached.height;
    }

    // Try to get from messageHeights map
    const height = this.messageHeights.get(index);
    if (height) {
      return height;
    }

    // Use estimate
    return this.messageHeightEstimate;
  }

  /**
   * Measure and cache message height
   * @param {string} messageId - Message ID
   * @param {HTMLElement} element - Message element
   */
  measureMessageHeight(messageId, element) {
    const height = element.offsetHeight;
    this.messageHeights.set(messageId, height);
    this.heightCache.set(messageId, {
      height,
      timestamp: Date.now(),
    });
    this._recalculateScrollHeight();
  }

  /**
   * Invalidate height cache for a message
   * @param {string} messageId - Message ID
   */
  invalidateHeightCache(messageId) {
    this.heightCache.delete(messageId);
    this._recalculateScrollHeight();
  }

  /**
   * Update visible range and render messages
   */
  _updateVisibleRange() {
    const range = this.getVisibleRange();

    // Render only visible messages
    this._renderMessages(range.startIndex, range.endIndex);

    // Update visible messages array
    this.visibleMessages = Array.from(
      this.container.querySelectorAll(this.itemSelector),
    );
  }

  /**
   * Render messages in range
   * @param {number} startIndex - Start index (inclusive)
   * @param {number} endIndex - End index (inclusive)
   */
  _renderMessages(startIndex, endIndex) {
    // For now, we'll just track the range
    // Actual rendering is handled by the renderer module
    this.renderedMessages.set("visibleRange", {
      startIndex,
      endIndex,
      timestamp: Date.now(),
    });
  }

  /**
   * Handle scroll events
   */
  _onScroll() {
    this.scrollTop = this.container.scrollTop;

    // Debounce the visible range update
    this._debouncedUpdate();
  }

  /**
   * Get current scroll position
   * @returns {Object} { scrollTop, scrollHeight, clientHeight }
   */
  getScrollPosition() {
    return {
      scrollTop: this.container.scrollTop,
      scrollHeight: this.container.scrollHeight,
      clientHeight: this.container.clientHeight,
    };
  }

  /**
   * Scroll to message by index
   * @param {number} index - Message index
   * @param {Object} options - Scroll options
   */
  scrollToMessage(index, options = {}) {
    let cumulativeHeight = 0;

    for (let i = 0; i < index; i++) {
      cumulativeHeight += this._getMessageHeight(i);
    }

    const targetScrollTop = cumulativeHeight - (options.offset || 0);

    this.container.scrollTo({
      top: targetScrollTop,
      behavior: options.behavior || "auto",
    });
  }

  /**
   * Scroll to bottom
   */
  scrollToBottom() {
    this.container.scrollTo({
      top: this.container.scrollHeight,
      behavior: "smooth",
    });
  }

  /**
   * Save scroll position
   * @returns {number} Current scroll position
   */
  saveScrollPosition() {
    return this.container.scrollTop;
  }

  /**
   * Restore scroll position
   * @param {number} position - Scroll position to restore
   */
  restoreScrollPosition(position) {
    this.container.scrollTop = position;
  }

  /**
   * Destroy virtual scroll manager
   */
  destroy() {
    if (this.container) {
      this.container.removeEventListener("scroll", this._onScroll);
    }
    this.heightCache.clear();
    this.messageHeights.clear();
    this.isInitialized = false;
  }
}

// Initialize virtual scroll manager
const virtualScrollManager = new VirtualScrollManager(
  MESSAGES_CONTAINER_SELECTOR,
  MESSAGE_ITEM_SELECTOR,
);

/**
 * Initialize UI module
 */
export function initUI() {
  virtualScrollManager.init();
  initSidebar();
  initComposer();
  console.log(
    "UI module initialized with virtual scrolling, sidebar, and message composer",
  );
}

/**
 * Update message list with virtual scrolling
 * @param {Array} messages - Array of message objects
 */
export function updateMessageList(messages) {
  const container = document.querySelector(MESSAGES_CONTAINER_SELECTOR);
  if (!container) return;

  // Clear existing messages
  container.innerHTML = "";

  // Render messages
  messages.forEach((message) => {
    const messageEl = createMessageElement(message);
    container.appendChild(messageEl);
  });

  // Update virtual scroll manager
  virtualScrollManager.setTotalMessages(messages.length);

  // Measure heights of rendered messages
  const renderedMessages = container.querySelectorAll(MESSAGE_ITEM_SELECTOR);
  renderedMessages.forEach((msg) => {
    const id = msg.dataset.messageId;
    if (id) {
      virtualScrollManager.measureMessageHeight(id, msg);
    }
  });
}

/**
 * Create message element with distinct styling, status indicators, and actions
 * @param {Object} message - Message object
 * @returns {HTMLElement} Message DOM element
 */
function createMessageElement(message) {
  const el = document.createElement("article");
  const status = message.status || "complete";
  el.className = `message message-${message.role} message-status-${status}`;
  el.dataset.messageId = message.id;
  el.dataset.role = message.role;
  el.setAttribute("aria-label", `${getMessageAuthor(message.role)} message`);

  const ts = message.timestamp || message.createdAt || 0;
  const date = new Date(ts * 1000);
  const timestamp = date.toLocaleTimeString();

  const avatarIcon =
    message.role === "user" ? "👤" : message.role === "assistant" ? "🤖" : "⚙️";

  const statusHtml = buildStatusIndicator(status);
  const actionsHtml = buildMessageActions(message.role);
  const contentText = message.streamingContent || message.content || "";

  el.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${avatarIcon}</div>
    <div class="message-body">
      <div class="message-header">
        <span class="message-author">${getMessageAuthor(message.role)}</span>
        <time class="message-time" datetime="${date.toISOString()}">${timestamp}</time>
        ${statusHtml}
      </div>
      <div class="message-content">${escapeHtml(contentText)}</div>
      ${actionsHtml}
    </div>
  `;

  // Bind action handlers
  bindMessageActions(el, message);

  return el;
}

/**
 * Build status indicator HTML
 * @param {string} status - Message status (sending, complete, error, pending)
 * @returns {string} Status indicator HTML
 */
function buildStatusIndicator(status) {
  const indicators = {
    pending:
      '<span class="message-status message-status-pending" aria-label="Pending">⏳</span>',
    sending:
      '<span class="message-status message-status-sending" aria-label="Sending"><span class="sending-spinner" aria-hidden="true"></span></span>',
    complete:
      '<span class="message-status message-status-complete" aria-label="Sent">✓</span>',
    error:
      '<span class="message-status message-status-error" aria-label="Error sending">⚠️</span>',
    streaming:
      '<span class="message-status message-status-streaming" aria-label="Generating"><span class="streaming-pulse" aria-hidden="true"></span></span>',
  };
  return indicators[status] || "";
}

/**
 * Build message action buttons HTML
 * @param {string} role - Message role
 * @returns {string} Actions HTML
 */
function buildMessageActions(role) {
  const copyBtn = `<button type="button" class="msg-action-btn msg-copy-btn" aria-label="Copy message" title="Copy"><span aria-hidden="true">📋</span></button>`;
  const editBtn =
    role === "user"
      ? `<button type="button" class="msg-action-btn msg-edit-btn" aria-label="Edit message" title="Edit"><span aria-hidden="true">✏️</span></button>`
      : "";
  const deleteBtn = `<button type="button" class="msg-action-btn msg-delete-btn" aria-label="Delete message" title="Delete"><span aria-hidden="true">🗑️</span></button>`;

  return `<div class="message-actions">${copyBtn}${editBtn}${deleteBtn}</div>`;
}

/**
 * Bind click handlers to message action buttons
 * @param {HTMLElement} el - Message element
 * @param {Object} message - Message object
 */
function bindMessageActions(el, message) {
  const copyBtn = el.querySelector(".msg-copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => handleCopyMessage(message));
  }

  const editBtn = el.querySelector(".msg-edit-btn");
  if (editBtn) {
    editBtn.addEventListener("click", () => handleEditMessage(message));
  }

  const deleteBtn = el.querySelector(".msg-delete-btn");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", () => handleDeleteMessage(message));
  }
}

/**
 * Get message author based on role
 * @param {string} role - Message role
 * @returns {string} Author name
 */
function getMessageAuthor(role) {
  const authors = {
    user: "You",
    assistant: "Assistant",
    system: "System",
  };
  return authors[role] || role.charAt(0).toUpperCase() + role.slice(1);
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Add message to list (with virtual scroll support)
 * @param {Object} message - Message object
 */
export function addMessage(message) {
  const container = document.querySelector(MESSAGES_CONTAINER_SELECTOR);
  if (!container) return;

  const messageEl = createMessageElement(message);
  container.appendChild(messageEl);

  // Update virtual scroll manager
  virtualScrollManager.setTotalMessages(container.children.length);
  virtualScrollManager.measureMessageHeight(message.id, messageEl);

  // Auto-scroll to bottom for new messages
  virtualScrollManager.scrollToBottom();
}

/**
 * Update message in list
 * @param {string} messageId - Message ID
 * @param {Object} updates - Message updates
 */
export function updateMessage(messageId, updates) {
  const messageEl = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!messageEl) return;

  // Update content if provided
  if (updates.content !== undefined) {
    const contentEl = messageEl.querySelector(".message-content");
    if (contentEl) {
      contentEl.innerHTML = escapeHtml(updates.content);
    }
  }

  // Update streaming content
  if (updates.streamingContent !== undefined) {
    const contentEl = messageEl.querySelector(".message-content");
    if (contentEl) {
      contentEl.innerHTML = escapeHtml(updates.streamingContent);
    }
  }

  // Update status if provided
  if (updates.status !== undefined) {
    // Update class
    messageEl.className = messageEl.className
      .replace(/message-status-\w+/g, "")
      .trim();
    messageEl.classList.add(`message-status-${updates.status}`);

    // Update status indicator
    const headerEl = messageEl.querySelector(".message-header");
    if (headerEl) {
      const existingStatus = headerEl.querySelector(".message-status");
      if (existingStatus) existingStatus.remove();
      const newIndicator = document.createElement("span");
      newIndicator.innerHTML = buildStatusIndicator(updates.status);
      const indicator = newIndicator.firstElementChild;
      if (indicator) headerEl.appendChild(indicator);
    }
  }

  // Invalidate height cache if content changed
  if (updates.content !== undefined || updates.streamingContent !== undefined) {
    virtualScrollManager.invalidateHeightCache(messageId);
  }
}

/**
 * Remove message from list
 * @param {string} messageId - Message ID
 */
export function removeMessage(messageId) {
  const messageEl = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!messageEl) return;

  messageEl.remove();

  // Update virtual scroll manager
  const container = document.querySelector(MESSAGES_CONTAINER_SELECTOR);
  virtualScrollManager.setTotalMessages(container.children.length);
}

/**
 * Get virtual scroll manager instance
 * @returns {VirtualScrollManager} Virtual scroll manager
 */
export function getVirtualScrollManager() {
  return virtualScrollManager;
}

// ============================================================
// Sidebar Session Management
// Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7
// ============================================================

const SESSION_LIST_SELECTOR = ".session-list";
const NEW_SESSION_BTN_SELECTOR = ".new-session-btn";
const CURRENT_SESSION_TITLE_SELECTOR = ".current-session-title";

/**
 * Initialize sidebar with session management
 * Binds event listeners and renders initial session list
 */
export function initSidebar() {
  const newSessionBtn = document.querySelector(NEW_SESSION_BTN_SELECTOR);
  if (newSessionBtn) {
    newSessionBtn.addEventListener("click", handleNewSession);
  }

  // Delegate click events on session list
  const sessionList = document.querySelector(SESSION_LIST_SELECTOR);
  if (sessionList) {
    sessionList.addEventListener("click", handleSessionListClick);
    sessionList.addEventListener("dblclick", handleSessionListDblClick);
  }

  // Subscribe to state changes for session updates
  stateStore.subscribe("sessions", () => renderSessionList());
  stateStore.subscribe("activeSessionId", () => renderSessionList());

  // Initial render
  renderSessionList();
}

/**
 * Render the session list sorted by most recent activity
 * Requirement 2.8: Most recently active session at top
 * Requirement 2.4: Visual indicator for active session
 */
export function renderSessionList() {
  const sessionList = document.querySelector(SESSION_LIST_SELECTOR);
  if (!sessionList) return;

  const sessions = stateStore.getSessions() || [];
  const activeSessionId = stateStore.get("activeSessionId");

  // Sort by updatedAt descending (most recent first)
  const sorted = [...sessions].sort(
    (a, b) =>
      (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0),
  );

  sessionList.innerHTML = "";

  if (sorted.length === 0) {
    const emptyItem = document.createElement("li");
    emptyItem.className = "session-item session-empty";
    emptyItem.setAttribute("role", "listitem");
    emptyItem.textContent = "No sessions yet";
    sessionList.appendChild(emptyItem);
    return;
  }

  sorted.forEach((session) => {
    const li = createSessionListItem(session, session.id === activeSessionId);
    sessionList.appendChild(li);
  });
}

/**
 * Create a session list item element
 * @param {Object} session - Session object
 * @param {boolean} isActive - Whether this is the active session
 * @returns {HTMLElement} Session list item
 */
function createSessionListItem(session, isActive) {
  const li = document.createElement("li");
  li.className = `session-item${isActive ? " active" : ""}`;
  li.dataset.sessionId = session.id;
  li.setAttribute("role", "listitem");
  li.setAttribute("tabindex", "0");
  li.setAttribute("aria-current", isActive ? "true" : "false");
  li.setAttribute(
    "aria-label",
    `Session: ${escapeHtml(session.name || "Untitled")}`,
  );

  const timeLabel = formatSessionTime(session.updatedAt || session.createdAt);

  li.innerHTML = `
    <div class="session-preview">
      <span class="session-name">${escapeHtml(session.name || "Untitled")}</span>
      <span class="session-meta">${timeLabel}</span>
    </div>
    <div class="session-actions">
      <button type="button" class="session-rename-btn" aria-label="Rename session" title="Rename">✏️</button>
      <button type="button" class="session-delete-btn" aria-label="Delete session" title="Delete">🗑️</button>
    </div>
  `;

  // Keyboard support for session switching
  li.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleSwitchSession(session.id);
    }
  });

  return li;
}

/**
 * Format session timestamp for display
 * @param {number} timestamp - Unix timestamp in seconds
 * @returns {string} Formatted time string
 */
function formatSessionTime(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp * 1000);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

/**
 * Handle click events on session list (delegation)
 * @param {Event} e - Click event
 */
function handleSessionListClick(e) {
  const deleteBtn = e.target.closest(".session-delete-btn");
  if (deleteBtn) {
    e.stopPropagation();
    const sessionItem = deleteBtn.closest(".session-item");
    if (sessionItem) {
      handleDeleteSession(sessionItem.dataset.sessionId);
    }
    return;
  }

  const renameBtn = e.target.closest(".session-rename-btn");
  if (renameBtn) {
    e.stopPropagation();
    const sessionItem = renameBtn.closest(".session-item");
    if (sessionItem) {
      startInlineRename(sessionItem.dataset.sessionId);
    }
    return;
  }

  const sessionItem = e.target.closest(".session-item");
  if (sessionItem && sessionItem.dataset.sessionId) {
    handleSwitchSession(sessionItem.dataset.sessionId);
  }
}

/**
 * Handle double-click on session list for inline rename
 * @param {Event} e - Double-click event
 */
function handleSessionListDblClick(e) {
  const sessionItem = e.target.closest(".session-item");
  if (sessionItem && sessionItem.dataset.sessionId) {
    e.preventDefault();
    startInlineRename(sessionItem.dataset.sessionId);
  }
}

/**
 * Create a new session
 * Requirement 2.1: Unlimited concurrent sessions
 * Requirement 2.2: Add to sidebar and make active within 50ms
 */
async function handleNewSession() {
  const now = getTimestamp();

  // Create session on backend first to get the real ID
  let sessionId;
  try {
    const res = await fetch(getApiUrl("/sessions"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Chat" }),
    });
    if (!res.ok) throw new Error(`Server responded with ${res.status}`);
    const data = await res.json();
    sessionId = data.id;
  } catch (err) {
    console.warn("Failed to create session on backend:", err);
  }

  // Clear message area for new session
  updateMessageList([]);
  updateCurrentSessionTitle("New Chat");

  showSuccess("New session created");
}

/**
 * Switch to a different session and load its messages
 * Requirement 2.3: Switch and display messages within 100ms
 * Requirement 2.4: Visual indicator for active session
 */
async function handleSwitchSession(sessionId) {
  const activeSessionId = stateStore.get("activeSessionId");
  if (sessionId === activeSessionId) return;

  stateStore.setActiveSession(sessionId);

  const session = stateStore.getSession(sessionId);
  if (!session) return;

  // Update title
  updateCurrentSessionTitle(session.name || "Untitled");

  // Load messages from state first for instant display
  let messages = session.messages || [];

  // If no messages in state, fetch from backend
  if (messages.length === 0) {
    try {
      const res = await fetch(getApiUrl(`/sessions/${sessionId}/messages`));
      if (res.ok) {
        const data = await res.json();
        const fetched = data.messages || data || [];
        messages = fetched.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          status: "complete",
          timestamp: m.created_at || 0,
          createdAt: m.created_at || 0,
        }));
        stateStore.updateSession(sessionId, { messages });
      }
    } catch (err) {
      console.warn("Failed to load messages:", err);
    }
  }

  updateMessageList(messages);
  virtualScrollManager.scrollToBottom();
}

/**
 * Delete a session with confirmation dialog
 * Requirement 2.5: Remove from sidebar, delete messages, show confirmation toast
 */
async function handleDeleteSession(sessionId) {
  const session = stateStore.getSession(sessionId);
  const sessionName = session ? session.name || "Untitled" : "this session";

  const confirmed = window.confirm(
    `Delete "${sessionName}"? This will remove all messages and cannot be undone.`,
  );
  if (!confirmed) return;

  const activeSessionId = stateStore.get("activeSessionId");

  stateStore.deleteSession(sessionId);

  // Persist deletion to backend
  try {
    await fetch(getApiUrl(`/sessions/${sessionId}`), {
      method: "DELETE",
    });
  } catch (err) {
    console.warn("Failed to delete session from backend:", err);
  }

  // If we deleted the active session, switch to the most recent one
  if (sessionId === activeSessionId) {
    const remaining = stateStore.getSessions() || [];
    if (remaining.length > 0) {
      const sorted = [...remaining].sort(
        (a, b) =>
          (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0),
      );
      handleSwitchSession(sorted[0].id);
    } else {
      updateMessageList([]);
      updateCurrentSessionTitle("No Active Session");
    }
  }

  showInfo(`Session "${sessionName}" deleted`);
}

/**
 * Start inline rename for a session
 * Requirement 2.7: Update sidebar label and persist within 50ms
 * @param {string} sessionId - Session ID to rename
 */
function startInlineRename(sessionId) {
  const sessionItem = document.querySelector(
    `.session-item[data-session-id="${sessionId}"]`,
  );
  if (!sessionItem) return;

  const nameSpan = sessionItem.querySelector(".session-name");
  if (!nameSpan) return;

  const currentName = nameSpan.textContent;

  // Replace span with input
  const input = document.createElement("input");
  input.type = "text";
  input.className = "session-rename-input";
  input.value = currentName;
  input.setAttribute("aria-label", "Rename session");

  nameSpan.replaceWith(input);
  input.focus();
  input.select();

  const commitRename = () => {
    const newName = input.value.trim() || "Untitled";
    finishRename(sessionId, newName, input);
  };

  input.addEventListener("blur", commitRename);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      input.removeEventListener("blur", commitRename);
      commitRename();
    } else if (e.key === "Escape") {
      e.preventDefault();
      input.removeEventListener("blur", commitRename);
      finishRename(sessionId, currentName, input);
    }
  });
}

/**
 * Finish inline rename and persist
 * @param {string} sessionId - Session ID
 * @param {string} newName - New session name
 * @param {HTMLInputElement} input - Input element to replace
 */
async function finishRename(sessionId, newName, input) {
  // Replace input with span
  const span = document.createElement("span");
  span.className = "session-name";
  span.textContent = newName;
  if (input.parentNode) {
    input.replaceWith(span);
  }

  // Update state
  stateStore.updateSession(sessionId, {
    name: newName,
    updatedAt: getTimestamp(),
  });

  // Update title if this is the active session
  const activeSessionId = stateStore.get("activeSessionId");
  if (sessionId === activeSessionId) {
    updateCurrentSessionTitle(newName);
  }

  // Persist to backend
  try {
    await fetch(getApiUrl(`/sessions/${sessionId}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName }),
    });
  } catch (err) {
    console.warn("Failed to persist session rename to backend:", err);
  }
}

/**
 * Update the current session title in the chat area header
 * @param {string} title - Session title
 */
function updateCurrentSessionTitle(title) {
  const titleEl = document.querySelector(CURRENT_SESSION_TITLE_SELECTOR);
  if (titleEl) {
    titleEl.textContent = title;
  }
}

// ============================================================
// Message Composer
// Requirements: 5.7 - Auto-resizing textarea, character/token counter,
// attachment preview/removal, keyboard shortcuts
// ============================================================

const MESSAGE_INPUT_SELECTOR = "#message-input";
const SEND_BTN_SELECTOR = ".send-btn";
const CLEAR_BTN_SELECTOR = ".clear-btn";
const ATTACHMENT_BTN_SELECTOR = ".attachment-btn";
const ATTACHMENT_PREVIEW_SELECTOR = ".attachment-preview";
const COMPOSER_FOOTER_SELECTOR = ".composer-footer";

// Rough token estimate: ~4 chars per token for English text
const CHARS_PER_TOKEN = 4;
const TEXTAREA_MAX_HEIGHT = 200; // px
const TEXTAREA_MIN_ROWS = 1;

/** Pending attachments for the current message */
let pendingAttachments = [];

/**
 * Initialize the message composer
 * Binds auto-resize, keyboard shortcuts, counters, and attachment handling
 */
export function initComposer() {
  const input = document.querySelector(MESSAGE_INPUT_SELECTOR);
  if (!input) return;

  // Auto-resize on input
  input.addEventListener("input", handleComposerInput);

  // Keyboard shortcuts
  input.addEventListener("keydown", handleComposerKeydown);

  // Send button
  const sendBtn = document.querySelector(SEND_BTN_SELECTOR);
  if (sendBtn) {
    sendBtn.addEventListener("click", handleSendMessage);
  }

  // Clear button
  const clearBtn = document.querySelector(CLEAR_BTN_SELECTOR);
  if (clearBtn) {
    clearBtn.addEventListener("click", handleClearComposer);
  }

  // Attachment button
  const attachBtn = document.querySelector(ATTACHMENT_BTN_SELECTOR);
  if (attachBtn) {
    attachBtn.addEventListener("click", handleAttachmentClick);
  }

  // Create hidden file input for attachment selection
  _ensureFileInput();

  // Insert counter element into composer footer
  _ensureCounterElement();

  // Initial sizing
  autoResizeTextarea(input);
}

/**
 * Ensure the hidden file input exists in the DOM
 */
function _ensureFileInput() {
  if (document.getElementById("attachment-file-input")) return;
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.id = "attachment-file-input";
  fileInput.multiple = true;
  fileInput.accept = ".txt,.md,.json,.csv";
  fileInput.style.display = "none";
  fileInput.addEventListener("change", handleFileSelected);
  document.body.appendChild(fileInput);
}

/**
 * Ensure the character/token counter element exists
 */
function _ensureCounterElement() {
  const footer = document.querySelector(COMPOSER_FOOTER_SELECTOR);
  if (!footer || footer.querySelector(".composer-counter")) return;

  const counter = document.createElement("div");
  counter.className = "composer-counter";
  counter.setAttribute("aria-live", "polite");
  counter.setAttribute("aria-atomic", "true");
  counter.innerHTML = `<span class="char-count">0</span> chars · <span class="token-count">0</span> tokens`;
  // Insert at the beginning of footer
  footer.insertBefore(counter, footer.firstChild);
}

// ---- Auto-resize ----

/**
 * Auto-resize textarea to fit content up to a max height
 * @param {HTMLTextAreaElement} textarea
 */
function autoResizeTextarea(textarea) {
  // Reset height to recalculate
  textarea.style.height = "auto";
  const newHeight = Math.min(textarea.scrollHeight, TEXTAREA_MAX_HEIGHT);
  textarea.style.height = `${newHeight}px`;
  // Show scrollbar only when content exceeds max
  textarea.style.overflowY =
    textarea.scrollHeight > TEXTAREA_MAX_HEIGHT ? "auto" : "hidden";
}

// ---- Counter ----

/**
 * Update the character and token counter display
 * @param {string} text - Current textarea content
 */
function updateCounter(text) {
  const footer = document.querySelector(COMPOSER_FOOTER_SELECTOR);
  if (!footer) return;

  const charEl = footer.querySelector(".char-count");
  const tokenEl = footer.querySelector(".token-count");
  if (!charEl || !tokenEl) return;

  const charCount = text.length;
  const tokenCount = Math.ceil(charCount / CHARS_PER_TOKEN);

  charEl.textContent = charCount;
  tokenEl.textContent = tokenCount;
}

// ---- Event Handlers ----

/**
 * Handle input events on the composer textarea
 * @param {Event} e
 */
function handleComposerInput(e) {
  const textarea = e.target;
  autoResizeTextarea(textarea);
  updateCounter(textarea.value);
}

/**
 * Handle keydown events for keyboard shortcuts
 * Enter to send, Shift+Enter for new line
 * @param {KeyboardEvent} e
 */
function handleComposerKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSendMessage();
  }
  // Shift+Enter falls through to default (inserts newline)
}

/**
 * Send the current message
 */
async function handleSendMessage() {
  const input = document.querySelector(MESSAGE_INPUT_SELECTOR);
  if (!input) return;

  const content = input.value.trim();
  if (content.length === 0 && pendingAttachments.length === 0) return;

  const sessionId = stateStore.get("activeSessionId");
  if (!sessionId) {
    showError("No active session. Create a new chat first.");
    return;
  }

  const messageId = generateId();
  const now = getTimestamp();

  // Build attachment references
  const attachmentRefs = pendingAttachments.map((a) => ({
    id: a.id,
    filename: a.file.name,
    fileSize: a.file.size,
  }));

  // Create message object
  const message = {
    id: messageId,
    role: "user",
    content,
    attachments: attachmentRefs,
    status: "sending",
    timestamp: now,
    createdAt: now,
  };

  // Optimistic UI update
  stateStore.addMessage(sessionId, message);
  addMessage(message);

  // Clear composer
  clearComposer();

  // Send via WebSocket if connected, otherwise fall back to REST
  if (streamHandler.isConnected()) {
    streamHandler.sendSendMessage(sessionId, content, true);
  } else {
    // Show typing indicator while waiting for LLM response
    showTypingIndicator();
    try {
      const res = await fetch(getApiUrl(`/sessions/${sessionId}/messages`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          attachments: attachmentRefs,
        }),
      });
      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}`);
      }
      const data = await res.json();
      stateStore.updateMessageStatus(sessionId, messageId, "complete");

      // Add assistant response to UI
      if (data.response) {
        const assistantMsg = {
          id: data.response.id,
          role: "assistant",
          content: data.response.content || "",
          status: "complete",
          timestamp: data.response.created_at || getTimestamp(),
          createdAt: data.response.created_at || getTimestamp(),
        };
        stateStore.addMessage(sessionId, assistantMsg);
        addMessage(assistantMsg);
      }
    } catch (err) {
      console.error("Failed to send message:", err);
      stateStore.updateMessageStatus(sessionId, messageId, "error");
      showError("Failed to send message. Please try again.");
    } finally {
      hideTypingIndicator();
    }
  }
}

/**
 * Clear the composer textarea, counter, and attachments
 */
function handleClearComposer() {
  clearComposer();
}

/**
 * Reset the composer to its empty state
 */
function clearComposer() {
  const input = document.querySelector(MESSAGE_INPUT_SELECTOR);
  if (input) {
    input.value = "";
    autoResizeTextarea(input);
    input.focus();
  }
  updateCounter("");
  clearAllAttachments();
}

// ---- Attachment Handling ----

/**
 * Open the file picker dialog
 */
function handleAttachmentClick() {
  const fileInput = document.getElementById("attachment-file-input");
  if (fileInput) {
    fileInput.value = ""; // Reset so same file can be re-selected
    fileInput.click();
  }
}

/**
 * Handle files selected from the file picker
 * @param {Event} e
 */
async function handleFileSelected(e) {
  const files = Array.from(e.target.files || []);
  if (files.length === 0) return;

  // Enforce max 10 attachments per message
  const maxAttachments = 10;
  const remaining = maxAttachments - pendingAttachments.length;
  if (remaining <= 0) {
    showError(`Maximum of ${maxAttachments} attachments per message.`);
    return;
  }

  const filesToAdd = files.slice(0, remaining);
  if (filesToAdd.length < files.length) {
    showInfo(
      `Only ${filesToAdd.length} of ${files.length} files added (limit: ${maxAttachments}).`,
    );
  }

  for (const file of filesToAdd) {
    const validation = validateFile(file);
    if (!validation.success) {
      showError(`${file.name}: ${validation.error}`);
      continue;
    }

    const id = generateId();
    const preview = await generatePreview(file);

    const attachment = { id, file, preview };
    pendingAttachments.push(attachment);
    renderAttachmentPreview(attachment);
  }
}

/**
 * Render a single attachment preview chip in the composer
 * @param {Object} attachment - { id, file, preview }
 */
function renderAttachmentPreview(attachment) {
  const container = document.querySelector(ATTACHMENT_PREVIEW_SELECTOR);
  if (!container) return;

  const chip = document.createElement("div");
  chip.className = "attachment-chip";
  chip.dataset.attachmentId = attachment.id;
  chip.setAttribute("role", "listitem");

  const sizeStr = formatFileSize(attachment.file.size);

  chip.innerHTML = `
    <span class="attachment-name" title="${escapeHtml(attachment.file.name)}">${escapeHtml(attachment.file.name)}</span>
    <span class="attachment-size">${sizeStr}</span>
    <button type="button" class="attachment-remove-btn" aria-label="Remove ${escapeHtml(attachment.file.name)}" title="Remove">×</button>
  `;

  // Remove handler
  chip.querySelector(".attachment-remove-btn").addEventListener("click", () => {
    removeAttachment(attachment.id);
  });

  container.appendChild(chip);
}

/**
 * Remove a single attachment by ID
 * @param {string} attachmentId
 */
function removeAttachment(attachmentId) {
  pendingAttachments = pendingAttachments.filter((a) => a.id !== attachmentId);

  const chip = document.querySelector(
    `.attachment-chip[data-attachment-id="${attachmentId}"]`,
  );
  if (chip) chip.remove();
}

/**
 * Clear all pending attachments
 */
function clearAllAttachments() {
  pendingAttachments = [];
  const container = document.querySelector(ATTACHMENT_PREVIEW_SELECTOR);
  if (container) container.innerHTML = "";
}

/**
 * Get current pending attachments
 * @returns {Array} Pending attachment objects
 */
export function getPendingAttachments() {
  return [...pendingAttachments];
}

// ============================================================
// Message Actions: Copy, Edit, Delete
// Requirements: 6.7 - Copy with attribution; 5.9 - Typing indicator
// ============================================================

/**
 * Copy message content to clipboard with attribution
 * Requirement 6.7: Include proper attribution formatting and timestamp
 * @param {Object} message - Message object
 */
async function handleCopyMessage(message) {
  const ts = message.timestamp || message.createdAt || 0;
  const date = new Date(ts * 1000);
  const author = getMessageAuthor(message.role);
  const content = message.streamingContent || message.content || "";

  const formatted = `[${author} – ${date.toLocaleString()}]\n${content}`;

  try {
    await navigator.clipboard.writeText(formatted);
    showSuccess("Message copied to clipboard");
  } catch (err) {
    // Fallback for older browsers
    const textarea = document.createElement("textarea");
    textarea.value = formatted;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
      showSuccess("Message copied to clipboard");
    } catch {
      showError("Failed to copy message");
    }
    document.body.removeChild(textarea);
  }
}

/**
 * Edit a user message – replaces content in the composer for re-sending
 * @param {Object} message - Message object
 */
function handleEditMessage(message) {
  if (message.role !== "user") return;

  const input = document.querySelector(MESSAGE_INPUT_SELECTOR);
  if (!input) return;

  input.value = message.content || "";
  autoResizeTextarea(input);
  updateCounter(input.value);
  input.focus();

  // Store the message id being edited so send can update instead of create
  input.dataset.editingMessageId = message.id;

  showInfo("Editing message – press Enter to resend");
}

/**
 * Delete a message with confirmation
 * @param {Object} message - Message object
 */
async function handleDeleteMessage(message) {
  const confirmed = window.confirm("Delete this message?");
  if (!confirmed) return;

  const sessionId = stateStore.get("activeSessionId");
  if (!sessionId) return;

  // Remove from DOM
  removeMessage(message.id);

  // Remove from state
  const session = stateStore.getSession(sessionId);
  if (session && session.messages) {
    const updated = session.messages.filter((m) => m.id !== message.id);
    stateStore.updateSession(sessionId, { messages: updated });
  }

  // Persist to backend
  try {
    await fetch(getApiUrl(`/sessions/${sessionId}/messages/${message.id}`), {
      method: "DELETE",
    });
  } catch (err) {
    console.warn("Failed to delete message from backend:", err);
  }

  showInfo("Message deleted");
}

// ============================================================
// Typing Indicator
// Requirement 5.9: Three dots cycling with 600ms period
// ============================================================

/**
 * Show the typing indicator animation
 */
export function showTypingIndicator() {
  const indicator = document.querySelector(".typing-indicator");
  if (!indicator) return;
  indicator.classList.add("visible");
  indicator.setAttribute("aria-hidden", "false");
  indicator.setAttribute("aria-label", "Assistant is typing");

  // Auto-scroll so the indicator is visible
  virtualScrollManager.scrollToBottom();
}

/**
 * Hide the typing indicator animation
 */
export function hideTypingIndicator() {
  const indicator = document.querySelector(".typing-indicator");
  if (!indicator) return;
  indicator.classList.remove("visible");
  indicator.setAttribute("aria-hidden", "true");
  indicator.removeAttribute("aria-label");
}

// ============================================================
// Streaming Content Display
// ============================================================

/**
 * Append a streaming token to a message element without full re-render
 * @param {string} messageId - Message ID
 * @param {string} token - New token to append
 */
export function appendStreamingToken(messageId, token) {
  const messageEl = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!messageEl) return;

  const contentEl = messageEl.querySelector(".message-content");
  if (!contentEl) return;

  // Append escaped token text
  contentEl.textContent += token;

  // Invalidate cached height
  virtualScrollManager.invalidateHeightCache(messageId);

  // Keep scrolled to bottom during streaming
  virtualScrollManager.scrollToBottom();
}

/**
 * Finalize a streaming message – mark complete and update status
 * @param {string} messageId - Message ID
 * @param {string} finalContent - Final complete content
 */
export function finalizeStreamingMessage(messageId, finalContent) {
  updateMessage(messageId, {
    content: finalContent,
    status: "complete",
  });
  hideTypingIndicator();
}

// Export for use in other modules
export default {
  initUI,
  initSidebar,
  initComposer,
  renderSessionList,
  updateMessageList,
  addMessage,
  updateMessage,
  removeMessage,
  getVirtualScrollManager,
  getPendingAttachments,
  showTypingIndicator,
  hideTypingIndicator,
  appendStreamingToken,
  finalizeStreamingMessage,
  VirtualScrollManager,
};
