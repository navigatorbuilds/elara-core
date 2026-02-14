// Command Palette (Cmd+K / Ctrl+K)
// Standalone snippet for docs navigation

(function() {
    'use strict';

    // Doc pages with descriptions
    const docPages = [
        { title: 'Home', path: '/index.html', desc: 'Landing page and quick start' },
        { title: 'Tools', path: '/tools.html', desc: '35 MCP tools documentation' },
        { title: 'Architecture', path: '/architecture.html', desc: 'System structure and modules' },
        { title: 'API', path: '/api.html', desc: 'API reference and usage' },
        { title: 'Quickstart', path: '/quickstart.html', desc: 'Get running in 5 minutes' },
        { title: 'Configure', path: '/configure.html', desc: 'Configuration and setup' },
        { title: 'Personas', path: '/personas.html', desc: 'Personality mode customization' },
        { title: 'Quiz', path: '/quiz.html', desc: 'Interactive decision guide' },
        { title: 'Compare', path: '/compare.html', desc: 'Before & after examples' },
        { title: 'Examples', path: '/examples.html', desc: 'Usage examples and patterns' },
        { title: 'Migration', path: '/migration.html', desc: 'Migration guide' },
        { title: 'FAQ', path: '/faq.html', desc: 'Frequently asked questions' },
        { title: 'Contributing', path: '/contributing.html', desc: 'How to contribute' },
        { title: 'Roadmap', path: '/roadmap.html', desc: 'Future plans and features' },
        { title: 'Changelog', path: '/changelog.html', desc: 'Version history' },
        { title: 'Benchmarks', path: '/benchmarks.html', desc: 'Performance metrics' },
        { title: 'Status', path: '/status.html', desc: 'System status and health' },
        { title: 'Privacy', path: '/privacy.html', desc: 'Privacy policy' },
        { title: 'License', path: '/license.html', desc: 'BSL-1.1 license terms' },
        { title: 'Search', path: '/search.html', desc: 'Search documentation' },
        { title: 'Playground', path: '/playground.html', desc: 'Interactive demo' },
        { title: 'Visualizer', path: '/visualizer.html', desc: 'Memory visualizer' },
        { title: 'Stickers', path: '/stickers.html', desc: 'Brand assets and stickers' },
        { title: 'Cheat Sheet', path: '/cheatsheet.html', desc: 'Quick reference guide' },
        { title: 'Story', path: '/story.html', desc: 'Origin story and motivation' },
        { title: 'Intro', path: '/intro.html', desc: 'Introduction and overview' },
    ];

    // Create palette HTML
    const paletteHTML = `
        <div id="cmd-palette-overlay" class="cmd-palette-overlay">
            <div class="cmd-palette">
                <div class="cmd-palette-header">
                    <input type="text" id="cmd-palette-input" class="cmd-palette-input" placeholder="Search docs..." autocomplete="off" />
                    <div class="cmd-palette-hint">ESC to close</div>
                </div>
                <div id="cmd-palette-results" class="cmd-palette-results"></div>
            </div>
        </div>
    `;

    // Create styles
    const paletteStyles = `
        <style id="cmd-palette-styles">
            .cmd-palette-overlay {
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0, 0, 0, 0.85);
                backdrop-filter: blur(4px);
                z-index: 100000;
                display: none;
                align-items: flex-start;
                justify-content: center;
                padding-top: 15vh;
                animation: cmd-palette-fade-in 0.15s ease-out;
            }

            .cmd-palette-overlay.active {
                display: flex;
            }

            @keyframes cmd-palette-fade-in {
                from {
                    opacity: 0;
                    transform: translateY(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .cmd-palette {
                width: 90%;
                max-width: 600px;
                background: #050505;
                border: 2px solid var(--green, #3b82f6);
                box-shadow: 0 0 30px rgba(59, 130, 246, 0.3), 0 10px 60px rgba(0, 0, 0, 0.8);
                font-family: 'Share Tech Mono', 'Courier New', monospace;
                position: relative;
                max-height: 70vh;
                display: flex;
                flex-direction: column;
            }

            .cmd-palette::before {
                content: '';
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                pointer-events: none;
                background: repeating-linear-gradient(
                    0deg,
                    transparent,
                    transparent 2px,
                    rgba(59, 130, 246, 0.02) 2px,
                    rgba(59, 130, 246, 0.02) 4px
                );
            }

            .cmd-palette-header {
                border-bottom: 1px solid var(--green-dark, #14532d);
                padding: 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                position: relative;
                z-index: 1;
            }

            .cmd-palette-input {
                flex: 1;
                background: transparent;
                border: none;
                outline: none;
                font-family: 'Share Tech Mono', 'Courier New', monospace;
                font-size: 16px;
                color: var(--green, #3b82f6);
                padding: 4px;
            }

            .cmd-palette-input::placeholder {
                color: var(--text-dim, #606060);
            }

            .cmd-palette-hint {
                font-size: 11px;
                color: var(--text-dim, #606060);
                text-transform: uppercase;
                letter-spacing: 1px;
                white-space: nowrap;
            }

            .cmd-palette-results {
                overflow-y: auto;
                max-height: calc(70vh - 60px);
                position: relative;
                z-index: 1;
            }

            .cmd-palette-item {
                padding: 12px 16px;
                border-bottom: 1px solid var(--border, #1a1a1a);
                cursor: pointer;
                transition: all 0.15s ease;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }

            .cmd-palette-item:hover,
            .cmd-palette-item.selected {
                background: rgba(59, 130, 246, 0.08);
                border-left: 3px solid var(--green, #3b82f6);
                padding-left: 13px;
            }

            .cmd-palette-item-title {
                font-size: 14px;
                color: var(--green, #3b82f6);
                font-weight: normal;
            }

            .cmd-palette-item.selected .cmd-palette-item-title {
                text-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
            }

            .cmd-palette-item-desc {
                font-size: 12px;
                color: var(--text-dim, #606060);
                line-height: 1.4;
            }

            .cmd-palette-no-results {
                padding: 32px 16px;
                text-align: center;
                color: var(--text-dim, #606060);
                font-size: 13px;
            }

            /* Scrollbar styling */
            .cmd-palette-results::-webkit-scrollbar {
                width: 8px;
            }

            .cmd-palette-results::-webkit-scrollbar-track {
                background: #050505;
            }

            .cmd-palette-results::-webkit-scrollbar-thumb {
                background: var(--border, #1a1a1a);
                border: 1px solid var(--green-dark, #14532d);
            }

            .cmd-palette-results::-webkit-scrollbar-thumb:hover {
                background: var(--green-dark, #14532d);
            }
        </style>
    `;

    // Initialize on DOM ready
    function init() {
        // Inject styles
        document.head.insertAdjacentHTML('beforeend', paletteStyles);

        // Inject palette HTML
        document.body.insertAdjacentHTML('beforeend', paletteHTML);

        const overlay = document.getElementById('cmd-palette-overlay');
        const input = document.getElementById('cmd-palette-input');
        const results = document.getElementById('cmd-palette-results');
        let selectedIndex = 0;
        let filteredPages = [...docPages];

        // Open/close handlers
        function openPalette() {
            overlay.classList.add('active');
            input.value = '';
            input.focus();
            renderResults(docPages);
            selectedIndex = 0;
        }

        function closePalette() {
            overlay.classList.remove('active');
        }

        // Fuzzy match function
        function fuzzyMatch(str, pattern) {
            pattern = pattern.toLowerCase();
            str = str.toLowerCase();

            let patternIdx = 0;
            let strIdx = 0;
            let score = 0;

            while (strIdx < str.length && patternIdx < pattern.length) {
                if (str[strIdx] === pattern[patternIdx]) {
                    score += 1;
                    patternIdx++;
                }
                strIdx++;
            }

            return patternIdx === pattern.length ? score : 0;
        }

        // Filter and render results
        function renderResults(pages) {
            if (pages.length === 0) {
                results.innerHTML = '<div class="cmd-palette-no-results">No matching pages found</div>';
                return;
            }

            results.innerHTML = pages.map((page, idx) => `
                <div class="cmd-palette-item ${idx === selectedIndex ? 'selected' : ''}" data-index="${idx}">
                    <div class="cmd-palette-item-title">> ${page.title}</div>
                    <div class="cmd-palette-item-desc">${page.desc}</div>
                </div>
            `).join('');

            // Add click handlers
            results.querySelectorAll('.cmd-palette-item').forEach(item => {
                item.addEventListener('click', () => {
                    const index = parseInt(item.dataset.index);
                    navigateToPage(filteredPages[index]);
                });
            });
        }

        // Navigate to selected page
        function navigateToPage(page) {
            window.location.href = page.path;
            closePalette();
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Cmd+K or Ctrl+K to open
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                if (overlay.classList.contains('active')) {
                    closePalette();
                } else {
                    openPalette();
                }
                return;
            }

            // Only handle these keys when palette is open
            if (!overlay.classList.contains('active')) return;

            switch (e.key) {
                case 'Escape':
                    e.preventDefault();
                    closePalette();
                    break;

                case 'ArrowDown':
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, filteredPages.length - 1);
                    renderResults(filteredPages);
                    // Scroll to selected item
                    scrollToSelected();
                    break;

                case 'ArrowUp':
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    renderResults(filteredPages);
                    scrollToSelected();
                    break;

                case 'Enter':
                    e.preventDefault();
                    if (filteredPages.length > 0) {
                        navigateToPage(filteredPages[selectedIndex]);
                    }
                    break;
            }
        });

        // Search input handler
        input.addEventListener('input', (e) => {
            const query = e.target.value.trim();

            if (!query) {
                filteredPages = [...docPages];
            } else {
                // Fuzzy search on title and description
                filteredPages = docPages
                    .map(page => ({
                        ...page,
                        score: Math.max(
                            fuzzyMatch(page.title, query),
                            fuzzyMatch(page.desc, query) * 0.7
                        )
                    }))
                    .filter(page => page.score > 0)
                    .sort((a, b) => b.score - a.score);
            }

            selectedIndex = 0;
            renderResults(filteredPages);
        });

        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closePalette();
            }
        });

        // Scroll to selected item
        function scrollToSelected() {
            const selected = results.querySelector('.cmd-palette-item.selected');
            if (selected) {
                selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
