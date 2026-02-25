/**
 * WebSocket Stream Handler
 * Implements WebSocket connection management with automatic reconnection,
 * state recovery, streaming response parsing, and backpressure handling
 * Requirements: 3.1, 3.2, 3.6, Property 3
 */

// Configuration
const WS_RECONNECT_DELAY = 1000; // 1 second
const WS_MAX_RECONNECT_DELAY = 30000; // 30 seconds
const WS_PING_INTERVAL = 30000; // 30 seconds
const WS_PING_TIMEOUT = 5000; // 5 seconds
const BACKPRESSURE_THRESHOLD = 100; // Buffer threshold before applying backpressure
const BACKPRESSURE_DELAY = 50; // Delay when backpressure is applied

// Message types
const MESSAGE_TYPES = {
    SEND_MESSAGE: 'send_message',
    CANCEL_STREAM: 'cancel_stream',
    GET_STATUS: 'get_status'
};

// Event types
const EVENT_TYPES = {
    TOKEN: 'token',
    COMPLETE: 'complete',
    ERROR: 'error',
    STATUS: 'status'
};

/**
 * Stream State
 */
class StreamState {
    constructor() {
        this.connectionStatus = 'disconnected';
        this.lastTokenTime = null;
        this.tokenBuffer = [];
        this.backpressureActive = false;
        this.pendingMessages = [];
        this.streamState = {
            sessionId: null,
            messageId: null,
            content: '',
            tokenCount: 0
        };
    }

    /**
     * Update connection status
     */
    setConnectionStatus(status) {
        this.connectionStatus = status;
    }

    /**
     * Record token arrival time
     */
    recordTokenTime() {
        this.lastTokenTime = Date.now();
    }

    /**
     * Check if backpressure should be applied
     */
    shouldApplyBackpressure() {
        return this.tokenBuffer.length >= BACKPRESSURE_THRESHOLD;
    }

    /**
     * Add token to buffer
     */
    addToken(token) {
        this.tokenBuffer.push(token);
        if (this.tokenBuffer.length > BACKPRESSURE_THRESHOLD * 2) {
            // Buffer overflow - flush immediately
            return true;
        }
        return false;
    }

    /**
     * Get and clear buffer
     */
    flushBuffer() {
        const tokens = [...this.tokenBuffer];
        this.tokenBuffer = [];
        return tokens;
    }

    /**
     * Update stream state
     */
    updateStreamState(sessionId, messageId, content, tokenCount) {
        this.streamState = {
            sessionId,
            messageId,
            content,
            tokenCount
        };
    }

    /**
     * Get current stream state
     */
    getStreamState() {
        return { ...this.streamState };
    }

    /**
     * Clear stream state
     */
    clearStreamState() {
        this.streamState = {
            sessionId: null,
            messageId: null,
            content: '',
            tokenCount: 0
        };
    }
}

/**
 * WebSocket Stream Handler
 */
class StreamHandler {
    constructor() {
        this.state = new StreamState();
        this.ws = null;
        this.reconnectDelay = WS_RECONNECT_DELAY;
        this.reconnectTimer = null;
        this.pingTimer = null;
        this.pingTimeoutTimer = null;
        this.messageQueue = [];
        this.isProcessingQueue = false;
        this.eventListeners = new Map();
        this.sessionId = null;
    }

    /**
     * Connect to WebSocket
     */
    connect(sessionId) {
        this.sessionId = sessionId;
        const wsUrl = this._getWebSocketUrl(sessionId);
        
        this.state.setConnectionStatus('connecting');
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => this._onOpen();
            this.ws.onmessage = (event) => this._onMessage(event);
            this.ws.onclose = (event) => this._onClose(event);
            this.ws.onerror = (error) => this._onError(error);
            
            // Start ping timer
            this._startPing();
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this._handleReconnect();
        }
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        this._stopPing();
        this.state.setConnectionStatus('disconnected');
        this.sessionId = null;
    }

    /**
     * Get WebSocket URL
     */
    _getWebSocketUrl(sessionId) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        return `${protocol}//${host}/api/v1/ws/${sessionId}`;
    }

    /**
     * Handle WebSocket open
     */
    _onOpen() {
        console.log('WebSocket connected');
        this.state.setConnectionStatus('connected');
        this.reconnectDelay = WS_RECONNECT_DELAY;
        
        // Send any pending messages
        this._processMessageQueue();
        
        // Notify listeners
        this._emit('connected', { sessionId: this.sessionId });
    }

    /**
     * Handle WebSocket message
     */
    _onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            this._handleEvent(data);
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    }

    /**
     * Handle incoming event
     */
    _handleEvent(event) {
        const { type } = event;
        
        switch (type) {
            case EVENT_TYPES.TOKEN:
                this._handleToken(event);
                break;
            case EVENT_TYPES.COMPLETE:
                this._handleComplete(event);
                break;
            case EVENT_TYPES.ERROR:
                this._handleError(event);
                break;
            case EVENT_TYPES.STATUS:
                this._handleStatus(event);
                break;
            default:
                console.warn('Unknown event type:', type);
        }
    }

    /**
     * Handle token event
     */
    _handleToken(event) {
        const { token, message_id, content, token_count } = event;
        
        // Record token time for connection health
        this.state.recordTokenTime();
        
        // Check for backpressure
        const shouldFlush = this.state.addToken(token);
        
        if (shouldFlush) {
            this._applyBackpressure();
        }
        
        // Update stream state
        this.state.updateStreamState(
            this.sessionId,
            message_id,
            content,
            token_count
        );
        
        // Emit token event
        this._emit('token', {
            token,
            messageId: message_id,
            content,
            tokenCount: token_count
        });
    }

    /**
     * Handle complete event
     */
    _handleComplete(event) {
        const { message_id, content, token_count } = event;
        
        // Clear backpressure
        this._removeBackpressure();
        
        // Update stream state
        this.state.updateStreamState(
            this.sessionId,
            message_id,
            content,
            token_count
        );
        
        // Flush any remaining tokens
        const bufferedTokens = this.state.flushBuffer();
        if (bufferedTokens.length > 0) {
            this._emit('token', {
                token: bufferedTokens.join(''),
                messageId: message_id,
                content: content,
                tokenCount: token_count
            });
        }
        
        // Emit complete event
        this._emit('complete', {
            messageId: message_id,
            content,
            tokenCount: token_count
        });
        
        // Clear stream state
        this.state.clearStreamState();
    }

    /**
     * Handle error event
     */
    _handleError(event) {
        const { message_id, error, message } = event;
        
        // Clear backpressure
        this._removeBackpressure();
        
        // Emit error event
        this._emit('error', {
            messageId: message_id,
            error,
            message
        });
        
        // Clear stream state
        this.state.clearStreamState();
    }

    /**
     * Handle status event
     */
    _handleStatus(event) {
        const { status, message_id, token_count } = event;
        
        // Emit status event
        this._emit('status', {
            status,
            messageId: message_id,
            tokenCount: token_count
        });
    }

    /**
     * Handle WebSocket close
     */
    _onClose(event) {
        console.log('WebSocket closed:', event.code, event.reason);
        this.state.setConnectionStatus('disconnected');
        this._stopPing();
        
        // Notify listeners
        this._emit('disconnected', { code: event.code, reason: event.reason });
        
        // Attempt reconnection
        this._handleReconnect();
    }

    /**
     * Handle WebSocket error
     */
    _onError(error) {
        console.error('WebSocket error:', error);
        this.state.setConnectionStatus('error');
    }

    /**
     * Handle reconnection with exponential backoff
     */
    _handleReconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }
        
        console.log(`Attempting reconnection in ${this.reconnectDelay}ms`);
        
        this.reconnectTimer = setTimeout(() => {
            if (this.sessionId) {
                this.connect(this.sessionId);
            }
        }, this.reconnectDelay);
        
        // Exponential backoff
        this.reconnectDelay = Math.min(
            this.reconnectDelay * 2,
            WS_MAX_RECONNECT_DELAY
        );
    }

    /**
     * Start ping timer for connection health
     */
    _startPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
        }
        
        this.pingTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                // Send ping
                this.ws.send(JSON.stringify({ type: 'ping' }));
                
                // Set timeout for pong
                if (this.pingTimeoutTimer) {
                    clearTimeout(this.pingTimeoutTimer);
                }
                
                this.pingTimeoutTimer = setTimeout(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        console.warn('Ping timeout - closing connection');
                        this.ws.close(1001, 'Ping timeout');
                    }
                }, WS_PING_TIMEOUT);
            }
        }, WS_PING_INTERVAL);
    }

    /**
     * Stop ping timer
     */
    _stopPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
        
        if (this.pingTimeoutTimer) {
            clearTimeout(this.pingTimeoutTimer);
            this.pingTimeoutTimer = null;
        }
    }

    /**
     * Apply backpressure to prevent UI flooding
     */
    _applyBackpressure() {
        if (!this.state.backpressureActive) {
            this.state.backpressureActive = true;
            console.log('Backpressure applied');
            
            // Emit backpressure event
            this._emit('backpressure', { active: true });
        }
    }

    /**
     * Remove backpressure
     */
    _removeBackpressure() {
        if (this.state.backpressureActive) {
            this.state.backpressureActive = false;
            console.log('Backpressure removed');
            
            // Emit backpressure event
            this._emit('backpressure', { active: false });
        }
    }

    /**
     * Send message to WebSocket
     */
    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            // Queue message for later delivery
            this.messageQueue.push(message);
            this._processMessageQueue();
        }
    }

    /**
     * Process message queue
     */
    _processMessageQueue() {
        if (this.isProcessingQueue || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        this.isProcessingQueue = true;
        
        const processNext = () => {
            if (this.messageQueue.length === 0) {
                this.isProcessingQueue = false;
                return;
            }
            
            const message = this.messageQueue.shift();
            
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(message));
                
                // Process next message with small delay
                setTimeout(processNext, 10);
            } else {
                // Put message back at front
                this.messageQueue.unshift(message);
                this.isProcessingQueue = false;
            }
        };
        
        processNext();
    }

    /**
     * Send send_message message
     */
    sendSendMessage(sessionId, message, stream = true) {
        this.sendMessage({
            type: MESSAGE_TYPES.SEND_MESSAGE,
            session_id: sessionId,
            message,
            stream
        });
    }

    /**
     * Send cancel_stream message
     */
    sendCancelStream(sessionId, messageId) {
        this.sendMessage({
            type: MESSAGE_TYPES.CANCEL_STREAM,
            session_id: sessionId,
            message_id: messageId
        });
    }

    /**
     * Send get_status message
     */
    sendGetStatus(sessionId) {
        this.sendMessage({
            type: MESSAGE_TYPES.GET_STATUS,
            session_id: sessionId
        });
    }

    /**
     * Add event listener
     */
    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, new Set());
        }
        this.eventListeners.get(event).add(callback);
    }

    /**
     * Remove event listener
     */
    off(event, callback) {
        const listeners = this.eventListeners.get(event);
        if (listeners) {
            listeners.delete(callback);
        }
    }

    /**
     * Emit event
     */
    _emit(event, data) {
        const listeners = this.eventListeners.get(event);
        if (listeners) {
            listeners.forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in event listener for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Get connection status
     */
    getConnectionStatus() {
        return this.state.connectionStatus;
    }

    /**
     * Get current stream state
     */
    getStreamState() {
        return this.state.getStreamState();
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.state.connectionStatus === 'connected';
    }

    /**
     * Check if streaming
     */
    isStreaming() {
        return this.state.streamState.messageId !== null;
    }

    /**
     * Get last token time
     */
    getLastTokenTime() {
        return this.state.lastTokenTime;
    }

    /**
     * Check connection health
     */
    checkConnectionHealth() {
        const lastTokenTime = this.state.lastTokenTime;
        if (!lastTokenTime) {
            return { healthy: true, reason: 'No tokens received yet' };
        }
        
        const timeSinceLastToken = Date.now() - lastTokenTime;
        const maxIdleTime = 60000; // 60 seconds
        
        if (timeSinceLastToken > maxIdleTime) {
            return { 
                healthy: false, 
                reason: `No tokens received in ${Math.round(timeSinceLastToken / 1000)}s`,
                timeSinceLastToken
            };
        }
        
        return { 
            healthy: true, 
            reason: 'Connection healthy',
            timeSinceLastToken
        };
    }

    /**
     * Cleanup
     */
    destroy() {
        this.disconnect();
        this.eventListeners.clear();
        this.messageQueue = [];
    }
}

// Create singleton instance
const streamHandler = new StreamHandler();

// Export for use in other modules
export { 
    streamHandler, 
    StreamHandler,
    MESSAGE_TYPES,
    EVENT_TYPES 
};
