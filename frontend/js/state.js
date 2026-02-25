/**
 * State Management Module
 * Implements reactive state store with observer pattern, optimistic updates, and persistence
 * Requirements: 1.8, 6.10
 */

// State structure constants
const STATE_VERSION = '1.0';
const PERSISTENCE_KEY = 'llm-chat-state';
const PERSISTENCE_INTERVAL = 30000; // 30 seconds

// Initial state
const initialState = {
    sessions: [],
    activeSessionId: null,
    preferences: {
        theme: 'dark',
        accentColor: '#6366f1',
        fontSize: 'medium',
        sidebarWidth: 280,
        language: 'en'
    },
    connectionStatus: 'disconnected',
    isTyping: false,
    pendingUpdates: []
};

/**
 * State Store with Observer Pattern
 */
class StateStore {
    constructor() {
        this.state = this._loadState();
        this.observers = new Map();
        this.pendingUpdates = [];
        this.rollbackStack = [];
        this.persistenceTimer = null;
        
        // Start automatic persistence
        this._startPersistence();
        
        // Save on page unload
        window.addEventListener('beforeunload', () => this.saveState());
    }

    /**
     * Load state from localStorage or initialize with defaults
     */
    _loadState() {
        try {
            const saved = localStorage.getItem(PERSISTENCE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                // Merge with initial state to ensure new fields exist
                return { ...initialState, ...parsed, sessions: parsed.sessions || [] };
            }
        } catch (e) {
            console.warn('Failed to load state from localStorage:', e);
        }
        return JSON.parse(JSON.stringify(initialState));
    }

    /**
     * Save state to localStorage
     */
    saveState() {
        try {
            const stateToSave = {
                ...this.state,
                pendingUpdates: [] // Don't persist pending updates
            };
            localStorage.setItem(PERSISTENCE_KEY, JSON.stringify(stateToSave));
        } catch (e) {
            console.error('Failed to save state to localStorage:', e);
        }
    }

    /**
     * Start automatic persistence timer
     */
    _startPersistence() {
        if (this.persistenceTimer) {
            clearInterval(this.persistenceTimer);
        }
        this.persistenceTimer = setInterval(() => this.saveState(), PERSISTENCE_INTERVAL);
    }

    /**
     * Subscribe to state changes
     * @param {string} key - State key to subscribe to (or '*' for all changes)
     * @param {Function} callback - Callback function called with (newValue, oldValue, key)
     * @returns {Function} Unsubscribe function
     */
    subscribe(key, callback) {
        if (!this.observers.has(key)) {
            this.observers.set(key, new Set());
        }
        this.observers.get(key).add(callback);
        
        // Return unsubscribe function
        return () => {
            const subscribers = this.observers.get(key);
            if (subscribers) {
                subscribers.delete(callback);
                if (subscribers.size === 0) {
                    this.observers.delete(key);
                }
            }
        };
    }

    /**
     * Notify observers of a state change
     * @param {string} key - State key that changed
     * @param {*} newValue - New value
     * @param {*} oldValue - Previous value
     */
    _notify(key, newValue, oldValue) {
        const subscribers = this.observers.get(key);
        if (subscribers) {
            subscribers.forEach(callback => callback(newValue, oldValue, key));
        }
        
        // Notify wildcard subscribers
        const wildcardSubscribers = this.observers.get('*');
        if (wildcardSubscribers) {
            wildcardSubscribers.forEach(callback => callback(newValue, oldValue, key));
        }
    }

    /**
     * Get current state
     */
    getState() {
        return JSON.parse(JSON.stringify(this.state));
    }

    /**
     * Get specific state slice
     * @param {string} key - State key
     */
    get(key) {
        return JSON.parse(JSON.stringify(this.state[key]));
    }

    /**
     * Update state with optimistic update tracking
     * @param {string|Object} updates - Single key or object of updates
     * @param {*} value - Value if updates is a string key
     */
    update(updates, value = undefined) {
        const oldState = JSON.parse(JSON.stringify(this.state));
        
        if (typeof updates === 'string') {
            this.state[updates] = value;
        } else {
            Object.assign(this.state, updates);
        }
        
        // Track optimistic updates
        this._trackOptimisticUpdate(updates, oldState);
        
        // Notify observers for each changed key
        const changedKeys = typeof updates === 'string' ? [updates] : Object.keys(updates);
        changedKeys.forEach(key => {
            this._notify(key, this.state[key], oldState[key]);
        });
        
        // Save state
        this.saveState();
    }

    /**
     * Track optimistic update for potential rollback
     * @param {Object} updates - Updates that were applied
     * @param {Object} oldState - State before updates
     */
    _trackOptimisticUpdate(updates, oldState) {
        const rollbackEntry = {
            timestamp: Date.now(),
            updates: typeof updates === 'string' ? { [updates]: updates } : { ...updates },
            oldState: oldState
        };
        this.rollbackStack.push(rollbackEntry);
        
        // Limit rollback stack size
        if (this.rollbackStack.length > 50) {
            this.rollbackStack.shift();
        }
    }

    /**
     * Create optimistic update (doesn't persist immediately)
     * @param {Object} updates - Updates to apply optimistically
     * @returns {string} Update ID for rollback
     */
    createOptimisticUpdate(updates) {
        const updateId = `update-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const rollbackEntry = {
            id: updateId,
            timestamp: Date.now(),
            updates: { ...updates },
            oldState: JSON.parse(JSON.stringify(this.state))
        };
        this.pendingUpdates.push(rollbackEntry);
        
        // Apply updates
        Object.assign(this.state, updates);
        
        // Notify observers
        Object.keys(updates).forEach(key => {
            this._notify(key, this.state[key], rollbackEntry.oldState[key]);
        });
        
        return updateId;
    }

    /**
     * Commit optimistic update (persist to localStorage)
     * @param {string} updateId - ID of update to commit
     */
    commitOptimisticUpdate(updateId) {
        const index = this.pendingUpdates.findIndex(u => u.id === updateId);
        if (index === -1) {
            throw new Error(`Update with ID ${updateId} not found`);
        }
        
        const update = this.pendingUpdates[index];
        this.pendingUpdates.splice(index, 1);
        
        // Persist to localStorage
        this.saveState();
    }

    /**
     * Rollback optimistic update
     * @param {string} updateId - ID of update to rollback
     */
    rollbackOptimisticUpdate(updateId) {
        const index = this.pendingUpdates.findIndex(u => u.id === updateId);
        if (index === -1) {
            throw new Error(`Update with ID ${updateId} not found`);
        }
        
        const update = this.pendingUpdates[index];
        this.pendingUpdates.splice(index, 1);
        
        // Restore old state
        this.state = update.oldState;
        
        // Notify observers
        Object.keys(update.updates).forEach(key => {
            this._notify(key, this.state[key], update.updates[key]);
        });
        
        // Persist restored state
        this.saveState();
    }

    /**
     * Rollback latest update
     */
    rollbackLatest() {
        if (this.rollbackStack.length === 0) {
            return false;
        }
        
        const lastUpdate = this.rollbackStack.pop();
        this.state = lastUpdate.oldState;
        
        // Notify observers for each key that changed
        Object.keys(lastUpdate.updates).forEach(key => {
            this._notify(key, this.state[key], lastUpdate.updates[key]);
        });
        
        this.saveState();
        return true;
    }

    /**
     * Session management methods
     */
    
    /**
     * Add a new session
     * @param {Object} session - Session data
     * @returns {string} Session ID
     */
    addSession(session) {
        const sessionId = session.id || crypto.randomUUID();
        const newSession = {
            id: sessionId,
            name: session.name || 'New Chat',
            messages: session.messages || [],
            llmConfig: session.llmConfig || {},
            contextTokens: session.contextTokens || 0,
            isTyping: false,
            createdAt: session.createdAt || Date.now(),
            updatedAt: Date.now()
        };
        
        this.update('sessions', [...this.state.sessions, newSession]);
        return sessionId;
    }

    /**
     * Get all sessions
     */
    getSessions() {
        return this.get('sessions');
    }

    /**
     * Get session by ID
     * @param {string} sessionId - Session ID
     */
    getSession(sessionId) {
        const sessions = this.get('sessions');
        return sessions.find(s => s.id === sessionId) || null;
    }

    /**
     * Update session
     * @param {string} sessionId - Session ID
     * @param {Object} updates - Session updates
     */
    updateSession(sessionId, updates) {
        const sessions = [...this.state.sessions];
        const index = sessions.findIndex(s => s.id === sessionId);
        
        if (index === -1) {
            throw new Error(`Session ${sessionId} not found`);
        }
        
        sessions[index] = {
            ...sessions[index],
            ...updates,
            updatedAt: Date.now()
        };
        
        this.update('sessions', sessions);
    }

    /**
     * Delete session
     * @param {string} sessionId - Session ID
     */
    deleteSession(sessionId) {
        const sessions = this.state.sessions.filter(s => s.id !== sessionId);
        this.update('sessions', sessions);
        
        if (this.state.activeSessionId === sessionId) {
            this.update('activeSessionId', sessions.length > 0 ? sessions[0].id : null);
        }
    }

    /**
     * Set active session
     * @param {string} sessionId - Session ID
     */
    setActiveSession(sessionId) {
        this.update('activeSessionId', sessionId);
    }

    /**
     * Message management methods
     */
    
    /**
     * Add message to session
     * @param {string} sessionId - Session ID
     * @param {Object} message - Message data
     * @returns {string} Message ID
     */
    addMessage(sessionId, message) {
        const sessions = [...this.state.sessions];
        const index = sessions.findIndex(s => s.id === sessionId);
        
        if (index === -1) {
            throw new Error(`Session ${sessionId} not found`);
        }
        
        const messageId = message.id || crypto.randomUUID();
        const newMessage = {
            id: messageId,
            role: message.role,
            content: message.content,
            attachments: message.attachments || [],
            status: message.status || 'complete',
            streamingContent: message.streamingContent || '',
            createdAt: message.createdAt || Date.now()
        };
        
        sessions[index].messages = [...sessions[index].messages, newMessage];
        sessions[index].updatedAt = Date.now();
        
        this.update('sessions', sessions);
        return messageId;
    }

    /**
     * Update message status
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     * @param {string} status - New status
     */
    updateMessageStatus(sessionId, messageId, status) {
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex === -1) {
            throw new Error(`Session ${sessionId} not found`);
        }
        
        const messages = [...sessions[sessionIndex].messages];
        const messageIndex = messages.findIndex(m => m.id === messageId);
        
        if (messageIndex === -1) {
            throw new Error(`Message ${messageId} not found`);
        }
        
        messages[messageIndex] = {
            ...messages[messageIndex],
            status: status,
            updatedAt: Date.now()
        };
        
        sessions[sessionIndex].messages = messages;
        sessions[sessionIndex].updatedAt = Date.now();
        
        this.update('sessions', sessions);
    }

    /**
     * Update message content
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     * @param {string} content - New content
     */
    updateMessageContent(sessionId, messageId, content) {
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex === -1) {
            throw new Error(`Session ${sessionId} not found`);
        }
        
        const messages = [...sessions[sessionIndex].messages];
        const messageIndex = messages.findIndex(m => m.id === messageId);
        
        if (messageIndex === -1) {
            throw new Error(`Message ${messageId} not found`);
        }
        
        messages[messageIndex] = {
            ...messages[messageIndex],
            content: content,
            updatedAt: Date.now()
        };
        
        sessions[sessionIndex].messages = messages;
        sessions[sessionIndex].updatedAt = Date.now();
        
        this.update('sessions', sessions);
    }

    /**
     * Streaming methods
     */
    
    /**
     * Start streaming response
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     */
    startStreaming(sessionId, messageId) {
        this.update('isTyping', true);
        
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex !== -1) {
            sessions[sessionIndex].isTyping = true;
            this.update('sessions', sessions);
        }
    }

    /**
     * Update streaming content
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     * @param {string} token - Token to append
     */
    updateStreamingContent(sessionId, messageId, token) {
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex === -1) {
            return;
        }
        
        const messages = [...sessions[sessionIndex].messages];
        const messageIndex = messages.findIndex(m => m.id === messageId);
        
        if (messageIndex === -1) {
            return;
        }
        
        messages[messageIndex] = {
            ...messages[messageIndex],
            streamingContent: (messages[messageIndex].streamingContent || '') + token,
            updatedAt: Date.now()
        };
        
        sessions[sessionIndex].messages = messages;
        this.update('sessions', sessions);
    }

    /**
     * Complete streaming response
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     */
    completeStreaming(sessionId, messageId) {
        this.update('isTyping', false);
        
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex !== -1) {
            sessions[sessionIndex].isTyping = false;
            
            // Merge streaming content into main content
            const messages = [...sessions[sessionIndex].messages];
            const messageIndex = messages.findIndex(m => m.id === messageId);
            
            if (messageIndex !== -1 && messages[messageIndex].streamingContent) {
                messages[messageIndex] = {
                    ...messages[messageIndex],
                    content: messages[messageIndex].streamingContent,
                    streamingContent: '',
                    status: 'complete',
                    updatedAt: Date.now()
                };
                sessions[sessionIndex].messages = messages;
            }
            
            this.update('sessions', sessions);
        }
    }

    /**
     * Error handling
     */
    
    /**
     * Mark streaming as errored
     * @param {string} sessionId - Session ID
     * @param {string} messageId - Message ID
     * @param {string} errorMessage - Error message
     */
    errorStreaming(sessionId, messageId, errorMessage) {
        this.update('isTyping', false);
        
        const sessions = [...this.state.sessions];
        const sessionIndex = sessions.findIndex(s => s.id === sessionId);
        
        if (sessionIndex !== -1) {
            sessions[sessionIndex].isTyping = false;
            
            const messages = [...sessions[sessionIndex].messages];
            const messageIndex = messages.findIndex(m => m.id === messageId);
            
            if (messageIndex !== -1) {
                messages[messageIndex] = {
                    ...messages[messageIndex],
                    status: 'error',
                    errorMessage: errorMessage,
                    updatedAt: Date.now()
                };
                sessions[sessionIndex].messages = messages;
            }
            
            this.update('sessions', sessions);
        }
    }

    /**
     * Preference management methods
     */
    
    /**
     * Update preferences
     * @param {Object} updates - Preference updates
     */
    updatePreferences(updates) {
        this.update('preferences', { ...this.state.preferences, ...updates });
    }

    /**
     * Get preference value
     * @param {string} key - Preference key
     */
    getPreference(key) {
        return this.state.preferences[key];
    }

    /**
     * Connection status methods
     */
    
    /**
     * Set connection status
     * @param {string} status - Connection status
     */
    setConnectionStatus(status) {
        this.update('connectionStatus', status);
    }

    /**
     * Clear all state
     */
    clear() {
        this.state = JSON.parse(JSON.stringify(initialState));
        this.rollbackStack = [];
        this.pendingUpdates = [];
        this.saveState();
        
        // Notify all observers
        Object.keys(initialState).forEach(key => {
            this._notify(key, this.state[key], initialState[key]);
        });
    }
}

// Create singleton instance
const stateStore = new StateStore();

// Export for use in other modules
export { stateStore, StateStore };
