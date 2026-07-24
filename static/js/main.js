/**
 * EduGuard AI – Main JavaScript
 * Handles sidebar toggle, dark mode, and utility functions.
 */

document.addEventListener('DOMContentLoaded', () => {

    // ── Sidebar Toggle ─────────────────────────────────────────────────────
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');

    // Create overlay for mobile
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('show');
                overlay.classList.toggle('show');
            } else {
                // Desktop: collapse/expand
                const mainWrapper = document.querySelector('.main-wrapper');
                const isCollapsed = sidebar.style.width === '0px';
                sidebar.style.width = isCollapsed ? '260px' : '0px';
                if (mainWrapper) {
                    mainWrapper.style.marginLeft = isCollapsed ? '260px' : '0px';
                }
            }
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('show');
            overlay.classList.remove('show');
        });
    }

    // ── Dark Mode Toggle ───────────────────────────────────────────────────
    const themeToggle = document.getElementById('themeToggle');
    const htmlEl = document.documentElement;
    const savedTheme = localStorage.getItem('eduguard-theme') || 'light';
    htmlEl.setAttribute('data-bs-theme', savedTheme);
    updateThemeIcon(savedTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const current = htmlEl.getAttribute('data-bs-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            htmlEl.setAttribute('data-bs-theme', next);
            localStorage.setItem('eduguard-theme', next);
            updateThemeIcon(next);
        });
    }

    function updateThemeIcon(theme) {
        if (!themeToggle) return;
        themeToggle.innerHTML = theme === 'dark'
            ? '<i class="bi bi-sun-fill"></i>'
            : '<i class="bi bi-moon-stars"></i>';
        themeToggle.title = theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode';
    }

    // ── Auto-dismiss alerts after 5s ──────────────────────────────────────
    document.querySelectorAll('.alert').forEach(alert => {
        if (!alert.classList.contains('alert-permanent')) {
            setTimeout(() => {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }, 5000);
        }
    });

    // ── Active nav link highlight ─────────────────────────────────────────
    const currentPath = window.location.pathname;
    document.querySelectorAll('.sidebar-nav li a').forEach(link => {
        if (link.getAttribute('href') && currentPath.startsWith(link.getAttribute('href'))) {
            link.closest('li').classList.add('active');
        }
    });

    // ── Confirm delete buttons ─────────────────────────────────────────────
    document.querySelectorAll('[data-confirm]').forEach(btn => {
        btn.addEventListener('click', e => {
            if (!confirm(btn.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // ── Smooth scroll to top ───────────────────────────────────────────────
    const toTopBtn = document.getElementById('toTopBtn');
    if (toTopBtn) {
        window.addEventListener('scroll', () => {
            toTopBtn.style.display = window.scrollY > 300 ? 'block' : 'none';
        });
        toTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    }

    // ── Form validation indicator ─────────────────────────────────────────
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            const btn = form.querySelector('[type="submit"]');
            if (btn && !btn.dataset.noLoading) {
                btn.disabled = true;
                const originalText = btn.innerHTML;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Processing...';
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }, 8000); // re-enable after 8s as safety
            }
        });
    });

    // ── Initialize all Bootstrap tooltips ────────────────────────────────
    document.querySelectorAll('[title]').forEach(el => {
        if (el.closest('.btn') || el.classList.contains('tooltip-target')) {
            new bootstrap.Tooltip(el, { trigger: 'hover', placement: 'top' });
        }
    });

    // ── Handle responsive table overflow ──────────────────────────────────
    document.querySelectorAll('.table-responsive').forEach(wrapper => {
        if (wrapper.scrollWidth > wrapper.clientWidth) {
            wrapper.style.boxShadow = 'inset -5px 0 5px -5px rgba(0,0,0,0.15)';
        }
    });
});
