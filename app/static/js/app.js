/**
 * BOM / BOQ Studio Pro — Core Client Utilities
 */

/* --------------------------------------------------------------------------
 * Department API key
 * Every /api request must carry the department's key in the X-API-Key header.
 * The server renders the signed-in user's key into <meta name="api-key">; this
 * shim attaches it to all same-origin /api calls made with fetch() or XHR, so
 * page scripts don't need to know about it.
 * ------------------------------------------------------------------------ */
(function () {
    'use strict';
    const HEADER = 'X-API-Key';

    function apiKey() {
        const meta = document.querySelector('meta[name="api-key"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function isApiUrl(url) {
        try {
            const u = new URL(url, window.location.href);
            return u.origin === window.location.origin && u.pathname.startsWith('/api/');
        } catch (e) {
            return false;
        }
    }

    let notified = false;
    function reportKeyProblem(res) {
        if (notified || !res || (res.status !== 401 && res.status !== 403)) return;
        res.clone().json().then(data => {
            if (!data || typeof data.error !== 'string' || data.error.indexOf('api_key') !== 0) return;
            notified = true;
            const msg = (data.message || 'API access was denied.') + ' Some features may not work until an Administrator restores your department\'s API key.';
            if (window.App && App.toast) App.toast(msg, 'error', 8000);
        }).catch(() => {});
    }

    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const url = (typeof Request !== 'undefined' && input instanceof Request) ? input.url : String(input);
        const key = apiKey();
        if (key && isApiUrl(url)) {
            init = Object.assign({}, init);
            const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
            if (!headers.has(HEADER)) headers.set(HEADER, key);
            init.headers = headers;
            return nativeFetch(input, init).then(res => { reportKeyProblem(res); return res; });
        }
        return nativeFetch(input, init);
    };

    const nativeOpen = XMLHttpRequest.prototype.open;
    const nativeSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        this._bomApiUrl = isApiUrl(url);
        return nativeOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
        const key = apiKey();
        if (this._bomApiUrl && key) {
            try { this.setRequestHeader(HEADER, key); } catch (e) { /* already sent */ }
        }
        return nativeSend.apply(this, arguments);
    };

    window.BomApiKey = { get: apiKey, header: HEADER };
})();

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
                const data = await res.clone().json().catch(() => ({}));
                // API key problems are not session problems: don't bounce to the login page.
                if (data && typeof data.error === 'string' && data.error.indexOf('api_key') === 0) {
                    return data;
                }
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

/* --------------------------------------------------------------------------
 * App shell: sidebar (collapsible on desktop, off-canvas on mobile) and
 * the account menu in the top bar.
 * ------------------------------------------------------------------------ */
const AppShell = {
    MOBILE_QUERY: '(max-width: 1023px)',

    isMobile() {
        return window.matchMedia(this.MOBILE_QUERY).matches;
    },

    shell() {
        return document.getElementById('appShell');
    },

    toggleSidebar() {
        if (this.isMobile()) {
            const shell = this.shell();
            if (shell && shell.classList.contains('sidebar-open')) this.closeSidebar();
            else this.openSidebar();
            return;
        }
        const collapsed = document.documentElement.classList.toggle('sidebar-collapsed');
        try { localStorage.setItem('bom_sidebar', collapsed ? 'collapsed' : 'expanded'); } catch (e) {}
    },

    openSidebar() {
        const shell = this.shell();
        if (!shell) return;
        shell.classList.add('sidebar-open');
        document.body.classList.add('no-scroll');
        const first = shell.querySelector('.side-link');
        if (first) first.focus({ preventScroll: true });
    },

    closeSidebar() {
        const shell = this.shell();
        if (!shell) return;
        shell.classList.remove('sidebar-open');
        document.body.classList.remove('no-scroll');
    }
};
window.AppShell = AppShell;

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    AppShell.closeSidebar();
    document.querySelectorAll('details.user-menu[open]').forEach(d => d.removeAttribute('open'));
});

document.addEventListener('click', (e) => {
    document.querySelectorAll('details.user-menu[open]').forEach(d => {
        if (!d.contains(e.target)) d.removeAttribute('open');
    });
});

window.addEventListener('resize', () => {
    if (!AppShell.isMobile()) AppShell.closeSidebar();
});
