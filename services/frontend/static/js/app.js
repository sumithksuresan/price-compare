/* ===================== STATE ===================== */
let currentUser = null;
let currentResults = [];
let selectedPlatforms = new Set(['all']);
let watchlistItems = [];

const PLATFORM_COLORS = {
  blinkit: '#f8d012',
  swiggy_instamart: '#fc8019',
  zepto: '#a78bfa',
  bigbasket: '#84cc16',
};

/* ===================== INIT ===================== */
document.addEventListener('DOMContentLoaded', () => {
  // Restore session from localStorage
  const token = localStorage.getItem('token');
  if (token) {
    verifyToken(token);
  }

  // Check for token in URL (SSO redirect)
  const urlParams = new URLSearchParams(window.location.search);
  const urlToken = urlParams.get('token');
  if (urlToken) {
    localStorage.setItem('token', urlToken);
    window.history.replaceState({}, '', '/');
    verifyToken(urlToken);
  }

  loadTrending();
  loadWatchlist();
});

/* ===================== AUTH ===================== */
async function verifyToken(token) {
  try {
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const user = await res.json();
      setUser(user);
    } else {
      localStorage.removeItem('token');
    }
  } catch (_) {}
}

function setUser(user) {
  currentUser = user;
  document.getElementById('authArea').style.display = 'none';
  document.getElementById('userArea').style.display = 'flex';
  document.getElementById('userName').textContent = user.name || user.email;
  document.getElementById('watchlistBtn').style.display = 'inline-flex';
  loadWatchlist();
}

function logout() {
  currentUser = null;
  localStorage.removeItem('token');
  document.getElementById('authArea').style.display = 'flex';
  document.getElementById('userArea').style.display = 'none';
  document.getElementById('watchlistBtn').style.display = 'none';
  watchlistItems = [];
}

async function submitLogin(e) {
  e.preventDefault();
  const email = document.getElementById('loginEmail').value;
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  errEl.textContent = '';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Login failed'; return; }
    localStorage.setItem('token', data.token);
    setUser(data.user);
    closeModal();
  } catch (_) {
    errEl.textContent = 'Network error. Please try again.';
  }
}

async function submitRegister(e) {
  e.preventDefault();
  const name = document.getElementById('regName').value;
  const email = document.getElementById('regEmail').value;
  const password = document.getElementById('regPassword').value;
  const errEl = document.getElementById('registerError');
  errEl.textContent = '';

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Registration failed'; return; }
    localStorage.setItem('token', data.token);
    setUser(data.user);
    closeModal();
  } catch (_) {
    errEl.textContent = 'Network error. Please try again.';
  }
}

/* ===================== MODAL ===================== */
function showAuthModal(tab) {
  document.getElementById('modalOverlay').style.display = 'block';
  document.getElementById('authModal').style.display = 'block';
  switchTab(tab);
}

function closeModal() {
  document.getElementById('modalOverlay').style.display = 'none';
  document.getElementById('authModal').style.display = 'none';
}

function switchTab(tab) {
  const isLogin = tab === 'login';
  document.getElementById('loginForm').style.display = isLogin ? 'block' : 'none';
  document.getElementById('registerForm').style.display = isLogin ? 'none' : 'block';
  document.getElementById('loginTab').classList.toggle('active', isLogin);
  document.getElementById('registerTab').classList.toggle('active', !isLogin);
  document.getElementById('loginError').textContent = '';
  document.getElementById('registerError').textContent = '';
}

/* ===================== SEARCH ===================== */
async function doSearch() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;

  showLoading(true);

  const params = new URLSearchParams({ q: query });
  if (!selectedPlatforms.has('all')) {
    selectedPlatforms.forEach(p => params.append('platform', p));
  }
  if (currentUser) params.set('user_id', currentUser.id);

  try {
    const res = await fetch(`/api/search?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Search failed');
    currentResults = data.results || [];
    renderResults(data);
  } catch (err) {
    showToast(`Search error: ${err.message}`, 'error');
  } finally {
    showLoading(false);
  }
}

function renderResults(data) {
  const section = document.getElementById('resultsSection');
  const grid = document.getElementById('cardsGrid');
  const noRes = document.getElementById('noResults');
  const banner = document.getElementById('bestDealBanner');

  section.style.display = 'block';
  document.getElementById('resultsTitle').textContent = `"${data.query}" — ${data.total} result${data.total !== 1 ? 's' : ''}`;

  if (!data.results || data.results.length === 0) {
    grid.innerHTML = '';
    noRes.style.display = 'block';
    banner.style.display = 'none';
    return;
  }

  noRes.style.display = 'none';

  // Best deal banner
  if (data.best_deal && data.best_deal.in_stock) {
    const b = data.best_deal;
    document.getElementById('bestDealText').textContent =
      `${b.platform_display} has the best price: ₹${b.price} for ${b.product_name} (${b.unit})`;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
  }

  renderCards(data.results);
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderCards(results) {
  const grid = document.getElementById('cardsGrid');
  const watchedQueries = new Set(watchlistItems.map(w => w.query));

  grid.innerHTML = results.map((r, i) => {
    const isBest = i === 0 && r.in_stock;
    const isWatched = watchedQueries.has((r.product_name || '').toLowerCase());
    return `
    <div class="price-card ${r.in_stock ? '' : 'out-of-stock'}">
      ${r.discount_pct > 0 ? `<span class="card-badge badge-discount">${r.discount_pct}% OFF</span>` : ''}
      ${isBest && !r.discount_pct ? `<span class="card-badge badge-best">Best</span>` : ''}
      ${!r.in_stock ? `<span class="card-badge badge-oos">Out of Stock</span>` : ''}

      <div class="platform-bar ${r.platform}">
        <span class="platform-dot"></span>
        ${r.platform_display}
      </div>

      <div class="card-body">
        <div class="card-img-wrap">
          <img src="${r.image_url}" alt="${r.product_name}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 60 60%22><text y=%2245%22 font-size=%2240%22>🛒</text></svg>'" />
        </div>

        <div class="card-name">${r.product_name}</div>
        <div class="card-unit">${r.unit}</div>

        <div class="card-price-row">
          <span class="price-current">₹${r.price}</span>
          ${r.original_price ? `<span class="price-original">₹${r.original_price}</span>` : ''}
        </div>

        <div class="delivery-time">⚡ ${r.delivery_time}</div>

        <div class="card-actions">
          <a href="${r.product_url}" target="_blank" rel="noopener" class="btn-view">View on ${r.platform_display}</a>
          ${currentUser ? `
          <button class="btn-watch ${isWatched ? 'watching' : ''}"
            onclick="toggleWatch('${escHtml(r.product_name)}', ${r.price})"
            title="${isWatched ? 'Remove from watchlist' : 'Add to watchlist'}">
            ${isWatched ? '⭐' : '☆'}
          </button>` : ''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function escHtml(str) {
  return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function sortResults() {
  const val = document.getElementById('sortSelect').value;
  const sorted = [...currentResults];
  if (val === 'price_asc') sorted.sort((a, b) => (b.in_stock - a.in_stock) || a.price - b.price);
  if (val === 'price_desc') sorted.sort((a, b) => (b.in_stock - a.in_stock) || b.price - a.price);
  if (val === 'discount') sorted.sort((a, b) => b.discount_pct - a.discount_pct);
  if (val === 'delivery') {
    // parse first number from delivery_time
    sorted.sort((a, b) => {
      const n = s => parseInt(s.match(/\d+/)?.[0] || '999');
      return n(a.delivery_time) - n(b.delivery_time);
    });
  }
  renderCards(sorted);
}

/* ===================== PLATFORM FILTERS ===================== */
function togglePlatform(platform, btn) {
  if (platform === 'all') {
    selectedPlatforms = new Set(['all']);
    document.querySelectorAll('.filter-chip').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
  } else {
    selectedPlatforms.delete('all');
    document.querySelector('[data-platform="all"]').classList.remove('active');

    if (selectedPlatforms.has(platform)) {
      selectedPlatforms.delete(platform);
      btn.classList.remove('active');
    } else {
      selectedPlatforms.add(platform);
      btn.classList.add('active');
    }

    if (selectedPlatforms.size === 0) {
      selectedPlatforms.add('all');
      document.querySelector('[data-platform="all"]').classList.add('active');
    }
  }
}

/* ===================== TRENDING ===================== */
async function loadTrending() {
  try {
    const res = await fetch('/api/trending');
    const data = await res.json();
    const chips = document.getElementById('trendingChips');
    if (!data.trending || data.trending.length === 0) {
      const defaults = ['milk', 'bread', 'eggs', 'rice', 'chips', 'shampoo', 'butter', 'tea'];
      chips.innerHTML = defaults.map(q =>
        `<button class="trending-chip" onclick="quickSearch('${q}')">${q}</button>`
      ).join('');
      return;
    }
    chips.innerHTML = data.trending.map(t =>
      `<button class="trending-chip" onclick="quickSearch('${escHtml(t.query)}')">${t.query} <span style="color:#6060780;font-size:11px">${t.count}</span></button>`
    ).join('');
  } catch (_) {}
}

function quickSearch(query) {
  document.getElementById('searchInput').value = query;
  doSearch();
}

/* ===================== WATCHLIST ===================== */
async function loadWatchlist() {
  if (!currentUser) return;
  try {
    const res = await fetch(`/api/watchlist?user_id=${currentUser.id}`);
    const data = await res.json();
    watchlistItems = data.watchlist || [];
    renderWatchlist();
  } catch (_) {}
}

async function toggleWatch(productName, price) {
  if (!currentUser) { showAuthModal('login'); return; }

  const query = productName.toLowerCase();
  const existing = watchlistItems.find(w => w.query === query);

  if (existing) {
    await fetch(`/api/watchlist/${existing.id}?user_id=${currentUser.id}`, { method: 'DELETE' });
    watchlistItems = watchlistItems.filter(w => w.id !== existing.id);
    showToast('Removed from watchlist');
  } else {
    const res = await fetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUser.id, query, target_price: price }),
    });
    const data = await res.json();
    watchlistItems.push({ id: Date.now(), query, target_price: price });
    showToast('Added to watchlist ⭐');
  }

  renderWatchlist();
  // Re-render cards to update star buttons
  const grid = document.getElementById('cardsGrid');
  if (grid.innerHTML) renderCards(currentResults);
}

function renderWatchlist() {
  const el = document.getElementById('watchlistItems');
  if (!watchlistItems.length) {
    el.innerHTML = '<p class="empty-msg">No items yet. Search for a product and click ☆ to add.</p>';
    return;
  }
  el.innerHTML = watchlistItems.map(w => `
    <div class="watchlist-item">
      <div>
        <div class="watchlist-item-name">${w.query}</div>
        ${w.target_price ? `<div class="watchlist-item-price">Target: ₹${w.target_price}</div>` : ''}
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="trending-chip" style="font-size:12px" onclick="quickSearch('${escHtml(w.query)}')">Search</button>
        <button class="btn-rm" onclick="removeWatch(${w.id})">✕</button>
      </div>
    </div>
  `).join('');
}

async function removeWatch(id) {
  if (!currentUser) return;
  await fetch(`/api/watchlist/${id}?user_id=${currentUser.id}`, { method: 'DELETE' });
  watchlistItems = watchlistItems.filter(w => w.id !== id);
  renderWatchlist();
  if (currentResults.length) renderCards(currentResults);
}

function toggleWatchlist() {
  const panel = document.getElementById('watchlistPanel');
  const overlay = document.getElementById('watchlistOverlay');
  const isOpen = panel.classList.contains('open');
  panel.classList.toggle('open', !isOpen);
  overlay.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) loadWatchlist();
}

/* ===================== HELPERS ===================== */
function showLoading(show) {
  document.getElementById('loadingOverlay').style.display = show ? 'flex' : 'none';
}

let toastTimer;
function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.style.cssText = `
      position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
      background:#1e1e2a; border:1px solid #2a2a3a; color:#e8e8f0;
      padding:12px 24px; border-radius:10px; font-size:14px; z-index:999;
      box-shadow:0 8px 32px rgba(0,0,0,0.5); transition:opacity 0.3s;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}
