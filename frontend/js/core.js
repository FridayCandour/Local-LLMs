/** Core Module - Utility functions and shared helpers.
 *  No imports from other app modules to avoid circular deps.
 */

// API Configuration
const API_BASE_URL = "/api/v1";

/** Get full API URL for endpoint */
export function getApiUrl(endpoint) {
  return `${API_BASE_URL}${endpoint}`;
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

export default {
  getApiUrl,
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
