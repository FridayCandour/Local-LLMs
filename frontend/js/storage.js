/**
 * IndexedDB Storage Module
 * Implements session and message persistence, cache with TTL-based expiration,
 * and LRU eviction for size limits
 * Requirements: 1.2, 1.3, 1.4, 10.5, Property 1
 */

// Database configuration
const DB_NAME = 'LLMChatStorage';
const DB_VERSION = 1;
const SESSION_STORE = 'sessions';
const MESSAGE_STORE = 'messages';
const ATTACHMENT_STORE = 'attachments';
const CACHE_STORE = 'cache';
const LRU_INDEX = 'lru';

// TTL configuration (in milliseconds)
const SESSION_TTL = 30 * 24 * 60 * 60 * 1000; // 30 days
const MESSAGE_TTL = 30 * 24 * 60 * 60 * 1000; // 30 days
const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

// Cache size limits
const MAX_CACHE_SIZE = 50 * 1024 * 1024; // 50MB
const MAX_CACHE_ENTRIES = 1000;

/**
 * Open IndexedDB database
 */
function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            
            // Create sessions store
            if (!db.objectStoreNames.contains(SESSION_STORE)) {
                const sessionStore = db.createObjectStore(SESSION_STORE, { keyPath: 'id' });
                sessionStore.createIndex('updatedAt', 'updatedAt', { unique: false });
            }
            
            // Create messages store
            if (!db.objectStoreNames.contains(MESSAGE_STORE)) {
                const messageStore = db.createObjectStore(MESSAGE_STORE, { keyPath: 'id' });
                messageStore.createIndex('sessionId', 'sessionId', { unique: false });
                messageStore.createIndex('createdAt', 'createdAt', { unique: false });
            }
            
            // Create attachments store
            if (!db.objectStoreNames.contains(ATTACHMENT_STORE)) {
                const attachmentStore = db.createObjectStore(ATTACHMENT_STORE, { keyPath: 'id' });
                attachmentStore.createIndex('messageId', 'messageId', { unique: false });
            }
            
            // Create cache store with TTL support
            if (!db.objectStoreNames.contains(CACHE_STORE)) {
                const cacheStore = db.createObjectStore(CACHE_STORE, { keyPath: 'key' });
                cacheStore.createIndex('expiresAt', 'expiresAt', { unique: false });
                cacheStore.createIndex('lastAccessed', 'lastAccessed', { unique: false });
            }
        };
        
        request.onsuccess = (event) => {
            resolve(event.target.result);
        };
        
        request.onerror = (event) => {
            reject(new Error(`IndexedDB error: ${event.target.error}`));
        };
    });
}

/**
 * Check if data is expired based on TTL
 */
function isExpired(entry, ttl) {
    if (!entry || !entry.expiresAt) {
        return false;
    }
    return Date.now() > entry.expiresAt;
}

/**
 * Update LRU timestamp for cache entries
 */
function updateLRU(db, key) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([CACHE_STORE], 'readwrite');
        const store = transaction.objectStore(CACHE_STORE);
        const request = store.get(key);
        
        request.onsuccess = () => {
            const entry = request.result;
            if (entry) {
                entry.lastAccessed = Date.now();
                const updateRequest = store.put(entry);
                updateRequest.onsuccess = () => resolve();
                updateRequest.onerror = () => reject(updateRequest.error);
            } else {
                resolve();
            }
        };
        
        request.onerror = () => reject(request.error);
    });
}

/**
 * Evict oldest cache entries when size limit exceeded
 */
async function evictLRU(db) {
    const transaction = db.transaction([CACHE_STORE], 'readonly');
    const store = transaction.objectStore(CACHE_STORE);
    const sizeRequest = store.getAll();
    
    return new Promise((resolve, reject) => {
        sizeRequest.onsuccess = async () => {
            const entries = sizeRequest.result;
            
            // Calculate total size
            let totalSize = 0;
            for (const entry of entries) {
                if (entry.value) {
                    totalSize += new TextEncoder().encode(JSON.stringify(entry.value)).length;
                }
            }
            
            // If over limit, evict oldest entries
            if (totalSize > MAX_CACHE_SIZE || entries.length > MAX_CACHE_ENTRIES) {
                // Sort by lastAccessed (oldest first)
                entries.sort((a, b) => a.lastAccessed - b.lastAccessed);
                
                // Calculate how many to evict
                const entriesToRemove = Math.ceil(entries.length * 0.2); // Remove 20%
                const sizeToRemove = Math.ceil(totalSize * 0.2); // Remove 20% of size
                
                let removedCount = 0;
                let removedSize = 0;
                
                for (const entry of entries) {
                    if (removedCount >= entriesToRemove && removedSize >= sizeToRemove) {
                        break;
                    }
                    
                    const entrySize = entry.value ? new TextEncoder().encode(JSON.stringify(entry.value)).length : 0;
                    removedCount++;
                    removedSize += entrySize;
                    
                    await new Promise((resolve, reject) => {
                        const deleteRequest = store.delete(entry.key);
                        deleteRequest.onsuccess = () => resolve();
                        deleteRequest.onerror = () => reject(deleteRequest.error);
                    });
                }
            }
            
            resolve();
        };
        
        sizeRequest.onerror = () => reject(sizeRequest.error);
    });
}

/**
 * Session Storage
 */
const sessionStorage = {
    /**
     * Save session to IndexedDB
     */
    async save(session) {
        const db = await openDB();
        
        const sessionData = {
            ...session,
            expiresAt: Date.now() + SESSION_TTL,
            lastAccessed: Date.now()
        };
        
        const transaction = db.transaction([SESSION_STORE], 'readwrite');
        const store = transaction.objectStore(SESSION_STORE);
        const request = store.put(sessionData);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to save session: ${event.target.error}`));
        });
    },
    
    /**
     * Get session by ID
     */
    async get(sessionId) {
        const db = await openDB();
        await updateLRU(db, sessionId);
        
        const transaction = db.transaction([SESSION_STORE], 'readonly');
        const store = transaction.objectStore(SESSION_STORE);
        const request = store.get(sessionId);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                const entry = request.result;
                if (entry && !isExpired(entry, SESSION_TTL)) {
                    resolve(entry);
                } else {
                    resolve(null);
                }
            };
            request.onerror = (event) => reject(new Error(`Failed to get session: ${event.target.error}`));
        });
    },
    
    /**
     * Get all sessions
     */
    async list() {
        const db = await openDB();
        
        const transaction = db.transaction([SESSION_STORE], 'readonly');
        const store = transaction.objectStore(SESSION_STORE);
        const request = store.getAll();
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                const entries = request.result;
                const validSessions = entries.filter(entry => !isExpired(entry, SESSION_TTL));
                resolve(validSessions);
            };
            request.onerror = (event) => reject(new Error(`Failed to list sessions: ${event.target.error}`));
        });
    },
    
    /**
     * Delete session
     */
    async delete(sessionId) {
        const db = await openDB();
        
        const transaction = db.transaction([SESSION_STORE, MESSAGE_STORE], 'readwrite');
        const sessionStore = transaction.objectStore(SESSION_STORE);
        const messageStore = transaction.objectStore(MESSAGE_STORE);
        
        // Delete session
        const sessionRequest = sessionStore.delete(sessionId);
        
        // Delete associated messages
        const messageIndex = messageStore.index('sessionId');
        const messageRequest = messageIndex.getAll(IDBKeyRange.only(sessionId));
        
        return new Promise((resolve, reject) => {
            messageRequest.onsuccess = () => {
                const messages = messageRequest.result;
                const deletePromises = messages.map(message => 
                    new Promise((resolve, reject) => {
                        const deleteRequest = messageStore.delete(message.id);
                        deleteRequest.onsuccess = () => resolve();
                        deleteRequest.onerror = () => reject(deleteRequest.error);
                    })
                );
                
                Promise.all(deletePromises)
                    .then(() => {
                        sessionRequest.onsuccess = () => resolve();
                        sessionRequest.onerror = (event) => reject(new Error(`Failed to delete session: ${event.target.error}`));
                    })
                    .catch(reject);
            };
            
            messageRequest.onerror = (event) => reject(new Error(`Failed to get messages: ${event.target.error}`));
        });
    },
    
    /**
     * Clear all sessions
     */
    async clear() {
        const db = await openDB();
        
        const transaction = db.transaction([SESSION_STORE, MESSAGE_STORE], 'readwrite');
        const sessionStore = transaction.objectStore(SESSION_STORE);
        const messageStore = transaction.objectStore(MESSAGE_STORE);
        
        const sessionRequest = sessionStore.clear();
        const messageRequest = messageStore.clear();
        
        return new Promise((resolve, reject) => {
            sessionRequest.onsuccess = () => resolve();
            sessionRequest.onerror = (event) => reject(new Error(`Failed to clear sessions: ${event.target.error}`));
        });
    }
};

/**
 * Message Storage
 */
const messageStorage = {
    /**
     * Save message to IndexedDB
     */
    async save(message) {
        const db = await openDB();
        
        const messageData = {
            ...message,
            expiresAt: Date.now() + MESSAGE_TTL,
            lastAccessed: Date.now()
        };
        
        const transaction = db.transaction([MESSAGE_STORE], 'readwrite');
        const store = transaction.objectStore(MESSAGE_STORE);
        const request = store.put(messageData);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to save message: ${event.target.error}`));
        });
    },
    
    /**
     * Get message by ID
     */
    async get(messageId) {
        const db = await openDB();
        await updateLRU(db, messageId);
        
        const transaction = db.transaction([MESSAGE_STORE], 'readonly');
        const store = transaction.objectStore(MESSAGE_STORE);
        const request = store.get(messageId);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                const entry = request.result;
                if (entry && !isExpired(entry, MESSAGE_TTL)) {
                    resolve(entry);
                } else {
                    resolve(null);
                }
            };
            request.onerror = (event) => reject(new Error(`Failed to get message: ${event.target.error}`));
        });
    },
    
    /**
     * Get all messages for a session
     */
    async list(sessionId) {
        const db = await openDB();
        
        const transaction = db.transaction([MESSAGE_STORE], 'readonly');
        const store = transaction.objectStore(MESSAGE_STORE);
        const index = store.index('sessionId');
        const request = index.getAll(IDBKeyRange.only(sessionId));
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                const entries = request.result;
                const validMessages = entries.filter(entry => !isExpired(entry, MESSAGE_TTL));
                // Sort by createdAt for chronological order
                validMessages.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
                resolve(validMessages);
            };
            request.onerror = (event) => reject(new Error(`Failed to list messages: ${event.target.error}`));
        });
    },
    
    /**
     * Delete message
     */
    async delete(messageId) {
        const db = await openDB();
        
        const transaction = db.transaction([MESSAGE_STORE], 'readwrite');
        const store = transaction.objectStore(MESSAGE_STORE);
        const request = store.delete(messageId);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to delete message: ${event.target.error}`));
        });
    },
    
    /**
     * Delete all messages for a session
     */
    async deleteBySession(sessionId) {
        const db = await openDB();
        
        const transaction = db.transaction([MESSAGE_STORE], 'readwrite');
        const store = transaction.objectStore(MESSAGE_STORE);
        const index = store.index('sessionId');
        const request = index.getAll(IDBKeyRange.only(sessionId));
        
        return new Promise((resolve, reject) => {
            request.onsuccess = async () => {
                const messages = request.result;
                const deletePromises = messages.map(message => 
                    new Promise((resolve, reject) => {
                        const deleteRequest = store.delete(message.id);
                        deleteRequest.onsuccess = () => resolve();
                        deleteRequest.onerror = () => reject(deleteRequest.error);
                    })
                );
                
                Promise.all(deletePromises)
                    .then(() => resolve())
                    .catch(reject);
            };
            
            request.onerror = (event) => reject(new Error(`Failed to get messages: ${event.target.error}`));
        });
    }
};

/**
 * Attachment Storage
 */
const attachmentStorage = {
    /**
     * Save attachment to IndexedDB
     */
    async save(attachment) {
        const db = await openDB();
        
        const transaction = db.transaction([ATTACHMENT_STORE], 'readwrite');
        const store = transaction.objectStore(ATTACHMENT_STORE);
        const request = store.put(attachment);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to save attachment: ${event.target.error}`));
        });
    },
    
    /**
     * Get attachment by ID
     */
    async get(attachmentId) {
        const db = await openDB();
        
        const transaction = db.transaction([ATTACHMENT_STORE], 'readonly');
        const store = transaction.objectStore(ATTACHMENT_STORE);
        const request = store.get(attachmentId);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject(new Error(`Failed to get attachment: ${event.target.error}`));
        });
    },
    
    /**
     * Get all attachments for a message
     */
    async listByMessage(messageId) {
        const db = await openDB();
        
        const transaction = db.transaction([ATTACHMENT_STORE], 'readonly');
        const store = transaction.objectStore(ATTACHMENT_STORE);
        const index = store.index('messageId');
        const request = index.getAll(IDBKeyRange.only(messageId));
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject(new Error(`Failed to list attachments: ${event.target.error}`));
        });
    },
    
    /**
     * Delete attachment
     */
    async delete(attachmentId) {
        const db = await openDB();
        
        const transaction = db.transaction([ATTACHMENT_STORE], 'readwrite');
        const store = transaction.objectStore(ATTACHMENT_STORE);
        const request = store.delete(attachmentId);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to delete attachment: ${event.target.error}`));
        });
    }
};

/**
 * Cache Storage with TTL-based expiration and LRU eviction
 */
const cacheStorage = {
    /**
     * Get cached value
     */
    async get(key) {
        const db = await openDB();
        await updateLRU(db, key);
        
        const transaction = db.transaction([CACHE_STORE], 'readonly');
        const store = transaction.objectStore(CACHE_STORE);
        const request = store.get(key);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                const entry = request.result;
                if (entry && !isExpired(entry, CACHE_TTL)) {
                    resolve(entry.value);
                } else {
                    resolve(null);
                }
            };
            request.onerror = (event) => reject(new Error(`Failed to get cache entry: ${event.target.error}`));
        });
    },
    
    /**
     * Set cached value with TTL
     */
    async set(key, value, ttl = CACHE_TTL) {
        const db = await openDB();
        
        // Evict old entries if needed
        await evictLRU(db);
        
        const entry = {
            key,
            value,
            expiresAt: Date.now() + ttl,
            lastAccessed: Date.now()
        };
        
        const transaction = db.transaction([CACHE_STORE], 'readwrite');
        const store = transaction.objectStore(CACHE_STORE);
        const request = store.put(entry);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to set cache entry: ${event.target.error}`));
        });
    },
    
    /**
     * Delete cached value
     */
    async delete(key) {
        const db = await openDB();
        
        const transaction = db.transaction([CACHE_STORE], 'readwrite');
        const store = transaction.objectStore(CACHE_STORE);
        const request = store.delete(key);
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to delete cache entry: ${event.target.error}`));
        });
    },
    
    /**
     * Clear all cache entries
     */
    async clear() {
        const db = await openDB();
        
        const transaction = db.transaction([CACHE_STORE], 'readwrite');
        const store = transaction.objectStore(CACHE_STORE);
        const request = store.clear();
        
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(new Error(`Failed to clear cache: ${event.target.error}`));
        });
    },
    
    /**
     * Check if cache entry exists and is valid
     */
    async has(key) {
        const value = await this.get(key);
        return value !== null;
    }
};

/**
 * Main Storage API
 */
const storage = {
    // Session operations
    saveSession: sessionStorage.save.bind(sessionStorage),
    getSession: sessionStorage.get.bind(sessionStorage),
    listSessions: sessionStorage.list.bind(sessionStorage),
    deleteSession: sessionStorage.delete.bind(sessionStorage),
    clearSessions: sessionStorage.clear.bind(sessionStorage),
    
    // Message operations
    saveMessage: messageStorage.save.bind(messageStorage),
    getMessage: messageStorage.get.bind(messageStorage),
    listMessages: messageStorage.list.bind(messageStorage),
    deleteMessage: messageStorage.delete.bind(messageStorage),
    deleteMessagesBySession: messageStorage.deleteBySession.bind(messageStorage),
    
    // Attachment operations
    saveAttachment: attachmentStorage.save.bind(attachmentStorage),
    getAttachment: attachmentStorage.get.bind(attachmentStorage),
    listAttachmentsByMessage: attachmentStorage.listByMessage.bind(attachmentStorage),
    deleteAttachment: attachmentStorage.delete.bind(attachmentStorage),
    
    // Cache operations
    getCache: cacheStorage.get.bind(cacheStorage),
    setCache: cacheStorage.set.bind(cacheStorage),
    deleteCache: cacheStorage.delete.bind(cacheStorage),
    clearCache: cacheStorage.clear.bind(cacheStorage),
    hasCache: cacheStorage.has.bind(cacheStorage)
};

// Export for use in other modules
export { storage };
