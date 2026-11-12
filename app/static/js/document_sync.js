/**
 * Document Sync Library — FastAPI Edition
 * Synchronizes between client localStorage cache and FastAPI endpoints
 */

const DocumentSync = {
    async saveDocument(documentName, documentType, items, status = 'saved') {
        try {
            const response = await fetch('/api/documents/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    documentName: documentName,
                    documentType: documentType,
                    items: items,
                    status: status
                })
            });
            const result = await response.json();
            if (result.success) {
                this.saveToLocalStorage(documentName, documentType, items, status);
                return { success: true, message: 'Document saved successfully' };
            } else {
                this.saveToLocalStorage(documentName, documentType, items, status);
                return { success: false, message: 'Saved to local cache only: ' + (result.message || result.detail) };
            }
        } catch (error) {
            this.saveToLocalStorage(documentName, documentType, items, status);
            return { success: false, message: 'Saved to local cache only: ' + error.message };
        }
    },

    async loadDocument(documentName) {
        try {
            const response = await fetch('/api/documents/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ documentName: documentName })
            });
            const result = await response.json();
            if (result.success && result.document) {
                return { success: true, document: result.document };
            }
            const localDoc = this.loadFromLocalStorage(documentName);
            if (localDoc) return { success: true, document: localDoc, source: 'localStorage' };
            return { success: false, message: result.message || 'Document not found' };
        } catch (error) {
            const localDoc = this.loadFromLocalStorage(documentName);
            if (localDoc) return { success: true, document: localDoc, source: 'localStorage' };
            return { success: false, message: error.message };
        }
    },

    async deleteDocument(documentName, status) {
        try {
            const response = await fetch('/api/documents/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ documentName: documentName })
            });
            const result = await response.json();
            this.deleteFromLocalStorage(documentName, status);
            return result;
        } catch (error) {
            this.deleteFromLocalStorage(documentName, status);
            return { success: false, message: error.message };
        }
    },

    async updateStatus(documentName, oldStatus, newStatus) {
        try {
            const response = await fetch('/api/documents/update_status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ documentName: documentName, status: newStatus })
            });
            const result = await response.json();
            this.updateLocalStorageStatus(documentName, oldStatus, newStatus);
            return result;
        } catch (error) {
            this.updateLocalStorageStatus(documentName, oldStatus, newStatus);
            return { success: false, message: error.message };
        }
    },

    async listDocuments(status = null) {
        try {
            const url = status ? `/api/documents/?status=${encodeURIComponent(status)}` : '/api/documents/';
            const response = await fetch(url);
            return await response.json();
        } catch (error) {
            return { success: false, message: error.message };
        }
    },

    async syncFromDatabase() {
        try {
            const response = await fetch('/api/documents/sync/all');
            const result = await response.json();
            if (result.success && result.documents) {
                const docs = result.documents;
                localStorage.setItem('savedBOMBOQDocuments', JSON.stringify(docs.saved || {}));
                localStorage.setItem('postedDocuments', JSON.stringify(docs.posted || {}));
                localStorage.setItem('pendingPriceEditDocuments', JSON.stringify(docs.pending_price_edit || {}));
                localStorage.setItem('unpostedDocuments', JSON.stringify(docs.unposted || {}));
                return { success: true, message: 'Documents synced successfully' };
            }
            return result;
        } catch (error) {
            return { success: false, message: error.message };
        }
    },

    // Local Storage helpers
    saveToLocalStorage(documentName, documentType, items, status) {
        const keys = {
            'saved': 'savedBOMBOQDocuments',
            'posted': 'postedDocuments',
            'pending_price_edit': 'pendingPriceEditDocuments',
            'unposted': 'unpostedDocuments'
        };
        const key = keys[status] || 'savedBOMBOQDocuments';
        const docs = JSON.parse(localStorage.getItem(key) || '{}');
        docs[documentName] = {
            type: documentType,
            [documentType === 'bom' ? 'bomItems' : 'boqItems']: items
        };
        localStorage.setItem(key, JSON.stringify(docs));
    },

    loadFromLocalStorage(documentName) {
        const keys = ['savedBOMBOQDocuments', 'postedDocuments', 'pendingPriceEditDocuments', 'unpostedDocuments'];
        for (let key of keys) {
            const docs = JSON.parse(localStorage.getItem(key) || '{}');
            if (docs[documentName]) {
                const status = key.replace('Documents', '').replace('savedBOMBOQ', 'saved')
                    .replace('pendingPriceEdit', 'pending_price_edit');
                return {
                    name: documentName,
                    type: docs[documentName].type,
                    items: docs[documentName].type === 'bom' ? docs[documentName].bomItems : docs[documentName].boqItems,
                    status: status
                };
            }
        }
        return null;
    },

    deleteFromLocalStorage(documentName, status) {
        const keys = {
            'saved': 'savedBOMBOQDocuments',
            'posted': 'postedDocuments',
            'pending_price_edit': 'pendingPriceEditDocuments',
            'unposted': 'unpostedDocuments'
        };
        const key = keys[status];
        if (key) {
            const docs = JSON.parse(localStorage.getItem(key) || '{}');
            delete docs[documentName];
            localStorage.setItem(key, JSON.stringify(docs));
        }
    },

    updateLocalStorageStatus(documentName, oldStatus, newStatus) {
        const keys = {
            'saved': 'savedBOMBOQDocuments',
            'posted': 'postedDocuments',
            'pending_price_edit': 'pendingPriceEditDocuments',
            'unposted': 'unpostedDocuments'
        };
        const oldKey = keys[oldStatus];
        const newKey = keys[newStatus];
        if (oldKey && newKey) {
            const oldDocs = JSON.parse(localStorage.getItem(oldKey) || '{}');
            const newDocs = JSON.parse(localStorage.getItem(newKey) || '{}');
            if (oldDocs[documentName]) {
                newDocs[documentName] = oldDocs[documentName];
                delete oldDocs[documentName];
                localStorage.setItem(oldKey, JSON.stringify(oldDocs));
                localStorage.setItem(newKey, JSON.stringify(newDocs));
            }
        }
    }
};

window.DocumentSync = DocumentSync;
