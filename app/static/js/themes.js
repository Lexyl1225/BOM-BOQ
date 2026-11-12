/* =====================================================
   BOM/BOQ Theme System — Theme Switcher Logic
   Persists theme selection via localStorage.
   Auto-applies theme on every page load.
   ===================================================== */

(function() {
    'use strict';

    var STORAGE_KEY = 'bom_theme';

    // Theme definitions — order matters for UI rendering
    var THEMES = [
        // Standard
        { id: 'default',    name: 'Default',            desc: 'Original look',          category: 'standard', swatch: 'linear-gradient(135deg, #667eea, #764ba2)' },
        { id: 'light',      name: 'Minimalist Light',   desc: 'Clean & bright',         category: 'standard', swatch: 'linear-gradient(135deg, #f8fafc, #e2e8f0)' },
        { id: 'dark',       name: 'Minimalist Dark',    desc: 'Easy on the eyes',       category: 'standard', swatch: 'linear-gradient(135deg, #0f172a, #1e293b)' },
        { id: 'corporate',  name: 'Corporate Blue',     desc: 'Professional & formal',  category: 'standard', swatch: 'linear-gradient(135deg, #1e40af, #3b82f6)' },
        { id: 'glass',      name: 'Glassmorphism',      desc: 'Frosted glass panels',   category: 'standard', swatch: 'linear-gradient(135deg, #302b63, #24243e)' },
        // Sci-Fi
        { id: 'scifi',      name: 'Sci-Fi Hangar',      desc: 'Holographic starship bay', category: 'scifi', swatch: 'linear-gradient(135deg, #0a0a1a, #00d2ff)' },
        // Gaming
        { id: 'neon',       name: 'RGB Neon',           desc: 'Glowing neon outlines',  category: 'gaming', swatch: 'linear-gradient(135deg, #0a0a0a, #00ff88)' },
        { id: 'cyberpunk',  name: 'Cyberpunk',          desc: 'Night-city vibes',       category: 'gaming', swatch: 'linear-gradient(135deg, #0d0221, #f706cf)' },
        { id: 'anime',      name: 'Anime Gaming',       desc: 'Cute & colorful',        category: 'gaming', swatch: 'linear-gradient(135deg, #fdf2f8, #ec4899)' }
    ];

    var CATEGORIES = [
        { id: 'standard', label: 'Standard Themes' },
        { id: 'scifi',    label: 'Futuristic Sci-Fi' },
        { id: 'gaming',   label: 'Gaming Themes' }
    ];

    // ----- Apply theme instantly (called before DOM ready too) -----
    function applyTheme(themeId) {
        if (!themeId || themeId === 'default') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', themeId);
        }
    }

    // Apply saved theme immediately (prevents flash of unstyled content)
    var saved = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch(e) {}
    applyTheme(saved);

    // ----- Build the theme selector panel + overlay -----
    function buildThemePanel() {
        // Overlay
        var overlay = document.createElement('div');
        overlay.className = 'theme-selector-overlay';
        overlay.addEventListener('click', closeThemePanel);

        // Panel
        var panel = document.createElement('div');
        panel.className = 'theme-selector-panel';
        panel.innerHTML = '<button class="theme-close-btn" title="Close">&times;</button>' +
                          '<h2>Select Theme</h2>' +
                          '<p class="theme-subtitle">Choose a look for the entire application</p>';

        panel.querySelector('.theme-close-btn').addEventListener('click', closeThemePanel);

        // Build categories
        CATEGORIES.forEach(function(cat) {
            var catDiv = document.createElement('div');
            catDiv.className = 'theme-category';
            catDiv.innerHTML = '<h3>' + cat.label + '</h3>';
            var grid = document.createElement('div');
            grid.className = 'theme-grid';

            THEMES.filter(function(t) { return t.category === cat.id; }).forEach(function(theme) {
                var card = document.createElement('div');
                card.className = 'theme-card' + (getCurrentTheme() === theme.id ? ' active' : '');
                card.setAttribute('data-theme-id', theme.id);
                card.innerHTML =
                    '<div class="theme-swatch" style="background:' + theme.swatch + ';"></div>' +
                    '<div class="theme-info">' +
                        '<div class="theme-name">' + theme.name + '</div>' +
                        '<div class="theme-desc">' + theme.desc + '</div>' +
                    '</div>';
                card.addEventListener('click', function() {
                    selectTheme(theme.id);
                });
                grid.appendChild(card);
            });

            catDiv.appendChild(grid);
            panel.appendChild(catDiv);
        });

        document.body.appendChild(overlay);
        document.body.appendChild(panel);

        return { overlay: overlay, panel: panel };
    }

    function getCurrentTheme() {
        try { return localStorage.getItem(STORAGE_KEY) || 'default'; } catch(e) { return 'default'; }
    }

    function selectTheme(themeId) {
        try { localStorage.setItem(STORAGE_KEY, themeId); } catch(e) {}
        applyTheme(themeId);

        // Update active state in cards
        var cards = document.querySelectorAll('.theme-card');
        for (var i = 0; i < cards.length; i++) {
            if (cards[i].getAttribute('data-theme-id') === themeId) {
                cards[i].classList.add('active');
            } else {
                cards[i].classList.remove('active');
            }
        }
    }

    var _els = null;
    function getEls() {
        if (!_els) _els = buildThemePanel();
        return _els;
    }

    function openThemePanel() {
        var els = getEls();
        // Refresh active state
        var current = getCurrentTheme();
        var cards = els.panel.querySelectorAll('.theme-card');
        for (var i = 0; i < cards.length; i++) {
            if (cards[i].getAttribute('data-theme-id') === current) {
                cards[i].classList.add('active');
            } else {
                cards[i].classList.remove('active');
            }
        }
        els.overlay.classList.add('open');
        els.panel.classList.add('open');
    }

    function closeThemePanel() {
        var els = getEls();
        els.overlay.classList.remove('open');
        els.panel.classList.remove('open');
    }

    // Expose globally for the index.php button
    window.BomThemes = {
        open: openThemePanel,
        close: closeThemePanel,
        apply: applyTheme,
        select: selectTheme,
        current: getCurrentTheme
    };
})();
