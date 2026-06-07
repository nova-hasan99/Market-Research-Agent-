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
    console.log('🚀 SPA Router initialized');

    // Handle initial page load
    const initialPath = window.location.pathname;
    this.currentPage = initialPath;
    console.log('📄 Initial page:', initialPath);

    // Handle browser back/forward buttons
    window.addEventListener('popstate', (e) => {
      console.log('⏪ Popstate event:', e.state);
      this.loadPage(e.state?.path || '/', false);
    });

    // Intercept all navigation links
    this.setupLinkInterception();
  }

  setupLinkInterception() {
    document.addEventListener('click', (e) => {
      let link = e.target.closest('a');
      if (!link) return;

      const href = link.getAttribute('href');
      if (!href) return;

      // Skip if it's not a relative link
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

      console.log('🔗 SPA Navigation to:', href);
      e.preventDefault();
      this.navigateTo(href);
    }, true);
  }

  navigateTo(path) {
    if (this.currentPage === path) {
      console.log('⚠️ Already on page:', path);
      return;
    }
    console.log('➡️ Navigate to:', path);
    this.loadPage(path);
  }

  async loadPage(path, addHistory = true) {
    if (this.isLoading) {
      console.log('⏳ Already loading, skipping');
      return;
    }

    // Normalize path
    if (!path) path = '/';
    if (path !== '/' && path.endsWith('/')) path = path.slice(0, -1);

    console.log('📥 Loading page:', path);

    try {
      this.isLoading = true;
      this.showLoadingState();

      // Check cache first
      let html;
      if (this.pageCache[path]) {
        console.log('💾 Using cached version of:', path);
        html = this.pageCache[path];
      } else {
        console.log('🌐 Fetching from server:', path);
        const response = await fetch(path, {
          method: 'GET',
          credentials: 'include',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/html'
          }
        });

        console.log('📊 Response status:', response.status);

        // Handle redirects
        if (response.status === 302 || response.status === 301 || response.status === 307) {
          console.log('🔄 Redirect detected, full page navigation');
          window.location.href = path;
          return;
        }

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

      // Find main content - try multiple selectors
      let mainContent = null;

      // Try to find all possible main content containers
      const mainElement = document.querySelector('main') ||
                         document.querySelector('.db-main') ||
                         document.querySelector('.privacy-container') ||
                         document.querySelector('.auth-main');

      if (mainElement) {
        // Try multiple selectors in the fetched document
        let sourceContent = null;

        if (doc.querySelector('main')) {
          sourceContent = doc.querySelector('main').innerHTML;
        } else if (doc.querySelector('.db-main')) {
          sourceContent = doc.querySelector('.db-main').innerHTML;
        } else if (doc.querySelector('.privacy-container')) {
          sourceContent = doc.querySelector('.privacy-container').innerHTML;
        } else if (doc.querySelector('.auth-main')) {
          sourceContent = doc.querySelector('.auth-main').innerHTML;
        }

        if (sourceContent) {
          console.log('✅ Found content to update');

          // Fade out
          mainElement.style.transition = 'opacity 0.2s ease';
          mainElement.style.opacity = '0';

          // Wait for fade
          await new Promise(resolve => setTimeout(resolve, 200));

          // Update content
          mainElement.innerHTML = sourceContent;

          // Fade in
          mainElement.style.opacity = '1';

          console.log('🎨 Content updated and faded in');
        } else {
          console.error('❌ Could not find source content in fetched page');
        }
      } else {
        console.error('❌ Could not find main element on current page');
      }

      // Update page title
      const pageTitle = doc.querySelector('title')?.textContent;
      if (pageTitle) {
        console.log('📝 Title updated:', pageTitle);
        document.title = pageTitle;
      }

      // Update current page
      this.currentPage = path;

      // Update history
      if (addHistory) {
        console.log('📚 Adding to history:', path);
        window.history.pushState({ path }, '', path);
      } else {
        console.log('🔀 Replacing history:', path);
        window.history.replaceState({ path }, '', path);
      }

      // Scroll to top
      window.scrollTo(0, 0);

      // Re-setup link interception for new content
      this.setupLinkInterception();

    } catch (error) {
      console.error('❌ Error loading page:', error);
      this.showErrorMessage(error.message);
    } finally {
      this.isLoading = false;
      this.hideLoadingState();
    }
  }

  showLoadingState() {
    const mainElement = document.querySelector('main') ||
                       document.querySelector('.db-main') ||
                       document.querySelector('.privacy-container');
    if (mainElement) {
      mainElement.style.pointerEvents = 'none';
    }
  }

  hideLoadingState() {
    const mainElement = document.querySelector('main') ||
                       document.querySelector('.db-main') ||
                       document.querySelector('.privacy-container');
    if (mainElement) {
      mainElement.style.pointerEvents = 'auto';
    }
  }

  show404() {
    const mainElement = document.querySelector('main') ||
                       document.querySelector('.db-main');
    if (mainElement) {
      mainElement.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;gap:2rem;text-align:center">
          <h1 style="font-size:4rem;font-weight:800;margin:0">404</h1>
          <h2 style="font-size:1.5rem;margin:0;color:var(--muted)">Page Not Found</h2>
          <p style="color:var(--muted);max-width:400px">The page you're looking for doesn't exist.</p>
          <a href="/" class="nav-btn-primary" style="padding:0.6rem 1.5rem;border-radius:8px;background:var(--primary);color:white;text-decoration:none;font-weight:600">Go Home</a>
        </div>
      `;
    }
  }

  showErrorMessage(message) {
    const mainElement = document.querySelector('main') ||
                       document.querySelector('.db-main');
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

  clearCache() {
    this.pageCache = {};
    console.log('🗑️ Cache cleared');
  }
}

// Initialize router
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.spaRouter = new SPARouter();
  });
} else {
  window.spaRouter = new SPARouter();
}
