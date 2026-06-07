/**
 * SPA Router - Single Page Application Router
 * Provides smooth navigation without full page reloads
 */

class SPARouter {
  constructor() {
    this.currentPage = null;
    this.isLoading = false;
    this.pageCache = {};
    this.init();
  }

  init() {
    // Handle initial page load
    this.loadPage(window.location.pathname);

    // Handle browser back/forward buttons
    window.addEventListener('popstate', (e) => {
      this.loadPage(e.state?.path || '/', false);
    });

    // Intercept all navigation links
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href]');
      if (!link) return;

      const href = link.getAttribute('href');

      // Skip external links, anchors, and special links
      if (
        href.startsWith('http') ||
        href.startsWith('mailto:') ||
        href.startsWith('tel:') ||
        href.startsWith('#') ||
        href.startsWith('javascript:') ||
        link.target === '_blank' ||
        link.hasAttribute('download')
      ) {
        return;
      }

      e.preventDefault();
      this.navigateTo(href);
    });

    // Close mobile menu on navigation
    document.addEventListener('click', (e) => {
      const closeMobileNav = window.closeMobileNav;
      if (typeof closeMobileNav === 'function') {
        const link = e.target.closest('a[href]');
        if (link && !link.href.startsWith('http')) {
          closeMobileNav();
        }
      }
    });
  }

  navigateTo(path) {
    if (this.currentPage === path) return;
    this.loadPage(path);
  }

  async loadPage(path, addHistory = true) {
    if (this.isLoading) return;

    // Normalize path
    if (!path) path = '/';
    if (path !== '/' && path.endsWith('/')) path = path.slice(0, -1);

    try {
      this.isLoading = true;
      this.showLoadingState();

      // Check cache first
      let html;
      if (this.pageCache[path]) {
        html = this.pageCache[path];
      } else {
        const response = await fetch(path, {
          headers: {
            'X-Requested-With': 'XMLHttpRequest'
          }
        });

        if (!response.ok) {
          if (response.status === 404) {
            this.show404();
          } else {
            throw new Error(`Failed to load page: ${response.status}`);
          }
          return;
        }

        html = await response.text();
        this.pageCache[path] = html;
      }

      // Extract main content
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');

      // Get the main content area
      let mainContent = null;

      // Try different main content selectors
      if (doc.querySelector('main')) {
        mainContent = doc.querySelector('main').innerHTML;
      } else if (doc.querySelector('.db-main')) {
        mainContent = doc.querySelector('.db-main').innerHTML;
      } else if (doc.querySelector('.privacy-container')) {
        mainContent = doc.querySelector('.privacy-container').innerHTML;
      } else if (doc.querySelector('.hero')) {
        // For landing page, get hero and features
        const hero = doc.querySelector('.hero');
        const features = doc.querySelector('.features');
        mainContent = (hero?.innerHTML || '') + (features?.innerHTML || '');
      }

      if (!mainContent) {
        throw new Error('Could not find main content');
      }

      // Add transition animation
      const mainElement = document.querySelector('main') || document.querySelector('.db-main') || document.querySelector('.privacy-container');
      if (mainElement) {
        mainElement.style.opacity = '0';
        mainElement.style.transform = 'translateY(10px)';
        mainElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';

        // Wait for transition to start
        await new Promise(resolve => setTimeout(resolve, 10));

        // Update content
        mainElement.innerHTML = mainContent;

        // Trigger animation in
        await new Promise(resolve => setTimeout(resolve, 10));
        mainElement.style.opacity = '1';
        mainElement.style.transform = 'translateY(0)';
      }

      // Update page title
      const pageTitle = doc.querySelector('title')?.textContent;
      if (pageTitle) {
        document.title = pageTitle;
      }

      // Update current page
      this.currentPage = path;

      // Update history
      if (addHistory) {
        window.history.pushState({ path }, '', path);
      } else {
        window.history.replaceState({ path }, '', path);
      }

      // Scroll to top
      window.scrollTo(0, 0);

      // Re-initialize any page-specific scripts
      this.reinitializePageScripts(path);

    } catch (error) {
      console.error('Page load error:', error);
      this.showErrorMessage(error.message);
    } finally {
      this.isLoading = false;
      this.hideLoadingState();
    }
  }

  reinitializePageScripts(path) {
    // Re-bind event listeners and initialize page-specific functionality
    if (path === '/research') {
      if (typeof window.initializeResearchPage === 'function') {
        window.initializeResearchPage();
      }
    } else if (path === '/dashboard') {
      if (typeof window.initializeDashboardPage === 'function') {
        window.initializeDashboardPage();
      }
    } else if (path === '/admin/users') {
      if (typeof loadAdminUsers === 'function') {
        loadAdminUsers();
      }
    }
  }

  showLoadingState() {
    const mainElement = document.querySelector('main') || document.querySelector('.db-main') || document.querySelector('.privacy-container');
    if (mainElement) {
      mainElement.style.opacity = '0.5';
      mainElement.style.pointerEvents = 'none';
    }
  }

  hideLoadingState() {
    const mainElement = document.querySelector('main') || document.querySelector('.db-main') || document.querySelector('.privacy-container');
    if (mainElement) {
      mainElement.style.opacity = '1';
      mainElement.style.pointerEvents = 'auto';
    }
  }

  show404() {
    const mainElement = document.querySelector('main') || document.querySelector('.db-main');
    if (mainElement) {
      mainElement.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;gap:2rem;text-align:center">
          <h1 style="font-size:4rem;font-weight:800;margin:0">404</h1>
          <h2 style="font-size:1.5rem;margin:0;color:var(--muted)">Page Not Found</h2>
          <p style="color:var(--muted);max-width:400px">The page you're looking for doesn't exist or has been moved.</p>
          <a href="/" class="nav-btn-primary" style="padding:0.6rem 1.5rem;border-radius:8px;background:var(--primary);color:white;text-decoration:none;font-weight:600">Go Home</a>
        </div>
      `;
    }
    this.currentPage = null;
  }

  showErrorMessage(message) {
    const mainElement = document.querySelector('main') || document.querySelector('.db-main');
    if (mainElement) {
      mainElement.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;gap:2rem;text-align:center">
          <h1 style="color:#ef4444;font-size:2rem;margin:0">⚠️ Error</h1>
          <p style="color:var(--muted);max-width:500px">${message}</p>
          <a href="/" class="nav-btn-primary" style="padding:0.6rem 1.5rem;border-radius:8px;background:var(--primary);color:white;text-decoration:none;font-weight:600">Go Home</a>
        </div>
      `;
    }
  }

  // Manual cache clear
  clearCache() {
    this.pageCache = {};
  }

  // Cache specific path
  preloadPage(path) {
    if (this.pageCache[path]) return Promise.resolve();

    return fetch(path, {
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(res => res.text())
      .then(html => {
        this.pageCache[path] = html;
      })
      .catch(err => console.warn(`Failed to preload ${path}:`, err));
  }
}

// Initialize router when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.spaRouter = new SPARouter();
  });
} else {
  window.spaRouter = new SPARouter();
}
