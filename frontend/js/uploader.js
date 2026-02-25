/** File Uploader Module for Local LLM Chat Interface.
 * 
 * Implements chunked file uploads with progress tracking, file validation,
 * and preview generation for supported file types.
 * 
 * Requirements: 4.2, 4.4
 */

import { getApiUrl, formatFileSize as formatFileSizeUtil } from './core.js';

// =============================================================================
// Configuration
// =============================================================================

const CHUNK_SIZE = 1024 * 1024; // 1MB chunks
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const SUPPORTED_EXTENSIONS = ['.txt', '.md', '.json', '.csv'];
const SUPPORTED_MIME_TYPES = [
    'text/plain',
    'text/markdown',
    'application/json',
    'text/csv'
];

// =============================================================================
// File Validation
// =============================================================================

/**
 * Validate file type and size
 * @param {File} file - File to validate
 * @returns {Object} Validation result with success flag and error message
 */
export function validateFile(file) {
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    const mimeType = file.type || '';
    
    // Check file size
    if (file.size > MAX_FILE_SIZE) {
        return {
            success: false,
            error: `File size (${formatFileSizeUtil(file.size)}) exceeds maximum (${formatFileSizeUtil(MAX_FILE_SIZE)})`
        };
    }
    
    // Check extension
    if (!SUPPORTED_EXTENSIONS.includes(extension)) {
        return {
            success: false,
            error: `File type '${extension}' is not supported. Supported types: ${SUPPORTED_EXTENSIONS.join(', ')}`
        };
    }
    
    // Check MIME type
    if (!SUPPORTED_MIME_TYPES.includes(mimeType) && mimeType !== '') {
        return {
            success: false,
            error: `MIME type '${mimeType}' is not supported`
        };
    }
    
    return { success: true };
}

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
export function formatFileSize(bytes) {
    return formatFileSizeUtil(bytes);
}

// =============================================================================
// File Preview Generation
// =============================================================================

/**
 * Generate preview for supported file types
 * @param {File} file - File to preview
 * @param {number} maxChars - Maximum characters to preview (default: 500)
 * @returns {Promise<Object>} Preview data with content and metadata
 */
export async function generatePreview(file, maxChars = 500) {
    const validation = validateFile(file);
    if (!validation.success) {
        throw new Error(validation.error);
    }
    
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    const text = await readFileAsText(file);
    
    // Extract preview content
    let previewContent = text.substring(0, maxChars);
    let isTruncated = text.length > maxChars;
    
    // Format based on file type
    if (extension === '.json') {
        try {
            const jsonData = JSON.parse(text);
            previewContent = JSON.stringify(jsonData, null, 2).substring(0, maxChars);
            isTruncated = JSON.stringify(jsonData, null, 2).length > maxChars;
        } catch (e) {
            // Invalid JSON, use raw text
        }
    } else if (extension === '.csv') {
        // Limit to first 10 lines for CSV
        const lines = text.split('\n').slice(0, 10);
        previewContent = lines.join('\n');
        isTruncated = lines.length < text.split('\n').length;
    }
    
    return {
        filename: file.name,
        fileSize: file.size,
        fileType: file.type || getMimeType(extension),
        previewContent: previewContent,
        isTruncated: isTruncated,
        totalCharacters: text.length,
        extension: extension
    };
}

/**
 * Read file as text
 * @param {File} file - File to read
 * @returns {Promise<string>} File content as text
 */
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(e);
        reader.readAsText(file);
    });
}

/**
 * Get MIME type for file extension
 * @param {string} extension - File extension
 * @returns {string} MIME type
 */
function getMimeType(extension) {
    const mimeMap = {
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.json': 'application/json',
        '.csv': 'text/csv'
    };
    return mimeMap[extension] || 'application/octet-stream';
}

// =============================================================================
// File Upload with Progress Tracking
// =============================================================================

/**
 * Upload file with progress tracking
 * @param {File} file - File to upload
 * @param {Object} options - Upload options
 * @param {function(number): void} options.onProgress - Progress callback (percentage)
 * @param {function(Object): void} options.onComplete - Completion callback (file data)
 * @param {function(string): void} options.onError - Error callback (error message)
 * @returns {Object} Upload controller with abort method
 */
export function uploadFile(file, options) {
    const { onProgress, onComplete, onError } = options;
    
    // Validate file
    const validation = validateFile(file);
    if (!validation.success) {
        onError(validation.error);
        return { abort: () => {} };
    }
    
    let aborted = false;
    const controller = {
        abort: () => {
            aborted = true;
            onError('Upload aborted by user');
        }
    };
    
    // Calculate chunks
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    let currentChunk = 0;
    
    // Read file in chunks
    const readChunk = (start, end) => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(e);
            reader.readAsArrayBuffer(file.slice(start, end));
        });
    };
    
    // Upload chunks sequentially
    const uploadChunks = async () => {
        try {
            // First, create the file record
            const fileRecord = await createFileRecord(file);
            
            // Upload each chunk
            for (let i = 0; i < totalChunks; i++) {
                if (aborted) return;
                
                const start = i * CHUNK_SIZE;
                const end = Math.min(start + CHUNK_SIZE, file.size);
                const chunkData = await readChunk(start, end);
                
                await uploadChunk(fileRecord.id, i + 1, totalChunks, chunkData);
                
                currentChunk = i + 1;
                const progress = Math.round((currentChunk / totalChunks) * 100);
                onProgress(progress);
            }
            
            // Complete upload
            const completedFile = await completeFileUpload(fileRecord.id);
            onComplete(completedFile);
            
        } catch (error) {
            if (!aborted) {
                onError(error.message || 'Upload failed');
            }
        }
    };
    
    uploadChunks();
    return controller;
}

/**
 * Create file record on server
 * @param {File} file - File to create record for
 * @returns {Promise<Object>} File record
 */
async function createFileRecord(file) {
    const formData = new FormData();
    formData.append('filename', file.name);
    formData.append('file_type', file.type || 'text/plain');
    
    const response = await fetch(getApiUrl('/api/v1/files'), {
        method: 'POST',
        body: formData
    });
    
    if (!response.ok) {
        throw new Error(`Failed to create file record: ${response.statusText}`);
    }
    
    return await response.json();
}

/**
 * Upload a chunk
 * @param {string} fileId - File ID
 * @param {number} chunkNumber - Chunk number (1-indexed)
 * @param {number} totalChunks - Total number of chunks
 * @param {ArrayBuffer} chunkData - Chunk data
 * @returns {Promise<void>}
 */
async function uploadChunk(fileId, chunkNumber, totalChunks, chunkData) {
    const blob = new Blob([chunkData], { type: 'application/octet-stream' });
    const formData = new FormData();
    formData.append('chunk', blob);
    formData.append('chunk_number', chunkNumber);
    formData.append('total_chunks', totalChunks);
    
    const response = await fetch(getApiUrl(`/api/v1/files/${fileId}/chunk`), {
        method: 'POST',
        body: formData
    });
    
    if (!response.ok) {
        throw new Error(`Failed to upload chunk ${chunkNumber}: ${response.statusText}`);
    }
}

/**
 * Complete file upload
 * @param {string} fileId - File ID
 * @returns {Promise<Object>} Completed file record
 */
async function completeFileUpload(fileId) {
    const response = await fetch(getApiUrl(`/api/v1/files/${fileId}/complete`), {
        method: 'POST'
    });
    
    if (!response.ok) {
        throw new Error(`Failed to complete file upload: ${response.statusText}`);
    }
    
    return await response.json();
}

// =============================================================================
// File Preview UI Component
// =============================================================================

/**
 * Create file preview element
 * @param {Object} previewData - Preview data from generatePreview
 * @returns {HTMLElement} Preview DOM element
 */
export function createFilePreviewElement(previewData) {
    const container = document.createElement('div');
    container.className = 'file-preview';
    
    // File info
    const fileInfo = document.createElement('div');
    fileInfo.className = 'file-info';
    
    const fileName = document.createElement('span');
    fileName.className = 'file-name';
    fileName.textContent = previewData.filename;
    
    const fileSize = document.createElement('span');
    fileSize.className = 'file-size';
    fileSize.textContent = formatFileSize(previewData.fileSize);
    
    fileInfo.appendChild(fileName);
    fileInfo.appendChild(fileSize);
    
    // Preview content
    const previewContent = document.createElement('div');
    previewContent.className = 'file-preview-content';
    previewContent.textContent = previewData.previewContent;
    
    if (previewData.isTruncated) {
        const truncatedMsg = document.createElement('div');
        truncatedMsg.className = 'truncated-message';
        truncatedMsg.textContent = '... (truncated)';
        previewContent.appendChild(truncatedMsg);
    }
    
    container.appendChild(fileInfo);
    container.appendChild(previewContent);
    
    return container;
}

// =============================================================================
// Module exports
// =============================================================================

export default {
    validateFile,
    formatFileSize,
    generatePreview,
    uploadFile,
    createFilePreviewElement,
    CHUNK_SIZE,
    MAX_FILE_SIZE,
    SUPPORTED_EXTENSIONS
};
