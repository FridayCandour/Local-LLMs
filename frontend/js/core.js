/** Core Module for Local LLM Chat Interface.
 * 
 * Application orchestrator and utility functions.
 */

// API Configuration
const API_BASE_URL = '/api/v1';

/**
 * Get full API URL for endpoint
 * @param {string} endpoint - API endpoint path
 * @returns {string} Full API URL
 */
export function getApiUrl(endpoint) {
    return `${API_BASE_URL}${endpoint}`;
}

/**
 * Generate a unique ID
 * @returns {string} UUID
 */
export function generateId() {
    return crypto.randomUUID();
}

/**
 * Get current timestamp
 * @returns {number} Unix timestamp in seconds
 */
export function getTimestamp() {
    return Date.now() / 1000;
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
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

/**
 * Throttle function
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time limit in milliseconds
 * @returns {Function} Throttled function
 */
export function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
export function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Show toast notification
 * @param {string} message - Notification message
 * @param {string} type - Notification type (success, error, info)
 */
export function showToast(message, type = 'info') {
    const container = document.querySelector('.toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/**
 * Show error notification
 * @param {string} message - Error message
 */
export function showError(message) {
    showToast(message, 'error');
}

/**
 * Show success notification
 * @param {string} message - Success message
 */
export function showSuccess(message) {
    showToast(message, 'success');
}

/**
 * Show info notification
 * @param {string} message - Info message
 */
export function showInfo(message) {
    showToast(message, 'info');
}

// Export for use in other modules
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
    showInfo
};
