/**
 * BOM / BOQ Studio Pro — Core Client Utilities
 */

const App = {
    // Show modern toast notification
    toast(message, type = 'info', duration = 4000) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        toast.innerHTML = `
            <span>${icons[type] || 'ℹ️'}</span>
            <div style="flex: 1;">${message}</div>
            <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:#94a3b8;font-size:16px;">&times;</button>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentElement) {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    },

    // Confirm dialog
    confirm(title, message, onConfirm) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay open';
        overlay.innerHTML = `
            <div class="modal-box" style="max-width: 440px;">
                <div class="modal-header">
                    <h3 class="modal-title">${title || 'Confirm Action'}</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <p style="font-size: 14px; color: #475569;">${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary btn-sm" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-danger btn-sm" id="confirm-ok-btn">Confirm</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelector('#confirm-ok-btn').addEventListener('click', () => {
            overlay.remove();
            if (typeof onConfirm === 'function') onConfirm();
        });
    },

    // Logout helper
    async logout() {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
        } catch (e) {
            console.error('Logout error:', e);
        }
        window.location.href = '/login';
    },

    // API fetch wrapper
    async api(url, options = {}) {
        options.credentials = 'same-origin';
        if (!options.headers) options.headers = {};
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }

        try {
            const res = await fetch(url, options);
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return await res.json();
        } catch (err) {
            App.toast('Network error: ' + err.message, 'error');
            throw err;
        }
    }
};

// Global shortcuts
window.App = App;
