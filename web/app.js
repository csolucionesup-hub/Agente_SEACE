// ── Auth: adjunta el token de Supabase (login con Google) o la API key, y maneja 401 ──
(function () {
  function getKey() { return (window.localStorage && localStorage.getItem('licitascan_api_key')) || ''; }
  function getToken() { return (window.__supabaseSession && window.__supabaseSession.access_token) || ''; }

  const originalFetch = window.fetch.bind(window);
  window.__rawFetch = originalFetch;
  window._apiFetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.startsWith('/api')) {
      const token = getToken();
      const key = getKey();
      if (token) {
        init = { ...init, headers: { ...(init.headers || {}), 'Authorization': 'Bearer ' + token } };
      } else if (key) {
        init = { ...init, headers: { ...(init.headers || {}), 'X-API-Key': key } };
      }
    }
    const response = await originalFetch(input, init);
    if (response.status === 401) {
      if (window.__authEnabled) {
        // Sesión vencida o ausente: volver a pedir login con Google.
        showLoginGate();
        return response;
      }
      await showAuthModal();
      const newKey = getKey();
      if (newKey) {
        init = { ...init, headers: { ...(init.headers || {}), 'X-API-Key': newKey } };
      }
      return originalFetch(input, init);
    }
    return response;
  };
  window.fetch = window._apiFetch;
})();

// ── Login con Google vía Supabase ──
function showLoginGate() {
  const gate = document.getElementById('login-gate');
  if (gate) gate.hidden = false;
  document.body.classList.add('locked');
}
function hideLoginGate() {
  const gate = document.getElementById('login-gate');
  if (gate) gate.hidden = true;
  document.body.classList.remove('locked');
}

async function initAuth() {
  let config;
  try {
    config = await window.__rawFetch('/api/config').then(r => r.json());
  } catch {
    return; // sin /api/config seguimos como app abierta (dev/local)
  }
  window.__authEnabled = !!config.auth_enabled;
  if (!config.auth_enabled) return;

  if (!window.supabase || !window.supabase.createClient) {
    console.error('supabase-js no cargó; la app continúa sin login.');
    window.__authEnabled = false;
    return;
  }
  const client = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
  window.__supabaseClient = client;
  client.auth.onAuthStateChange((_event, session) => { window.__supabaseSession = session || null; });

  const loginBtn = document.getElementById('google-login-btn');
  if (loginBtn) {
    loginBtn.addEventListener('click', async () => {
      const errorEl = document.getElementById('login-error');
      errorEl && (errorEl.hidden = true);
      const { error } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: window.location.origin },
      });
      if (error && errorEl) errorEl.hidden = false;
    });
  }
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await client.auth.signOut();
      window.location.reload();
    });
  }

  const { data } = await client.auth.getSession();
  window.__supabaseSession = data.session || null;

  if (!window.__supabaseSession) {
    showLoginGate();
    // Bloquea el arranque hasta que haya sesión: el login redirige a Google y, al
    // volver, getSession ya trae la sesión en una nueva carga de la página.
    await new Promise(() => {});
  }

  hideLoginGate();
  const email = (window.__supabaseSession.user && window.__supabaseSession.user.email) || '';
  const emailEl = document.getElementById('user-email');
  const bar = document.getElementById('user-bar');
  if (emailEl) emailEl.textContent = email;
  if (bar) bar.hidden = false;
}

function showAuthModal() {
  return new Promise(resolve => {
    const modal = document.getElementById('auth-modal');
    const form = document.getElementById('auth-form');
    const errorEl = document.getElementById('auth-error');
    if (!modal) { resolve(); return; }
    errorEl && (errorEl.hidden = true);
    modal.showModal();
    const handler = async (event) => {
      event.preventDefault();
      const key = document.getElementById('auth-key-input')?.value?.trim() || '';
      if (!key) return;
      // Verify the key works
      try {
        const res = await fetch('/api/settings', { headers: { 'X-API-Key': key } });
        if (res.ok) {
          localStorage.setItem('licitascan_api_key', key);
          modal.close();
          form.removeEventListener('submit', handler);
          resolve();
        } else {
          if (errorEl) errorEl.hidden = false;
        }
      } catch {
        if (errorEl) errorEl.hidden = false;
      }
    };
    form.addEventListener('submit', handler);
  });
}

const state = {
  dashboard: null,
  filtered: [],
  searchResults: [],
  searchPage: 1,
  searchPageSize: 25,
  settings: null,
  lastSearchAdvice: [],
  lastRecommendedRelaxation: null,
  documentCache: {},
};

const currency = new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN', maximumFractionDigits: 0 });

function byId(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}
function formatMoney(value) { return value === null || value === undefined || value === '' ? '—' : currency.format(Number(value)); }
function formatDate(value) {
  if (!value) return 'Sin fecha';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('es-PE', { day: '2-digit', month: 'short', year: 'numeric' });
}
function normalizeLabel(value) { return String(value || 'sin_estado').replaceAll('_', ' '); }
function statusLabel(value) {
  return ({ completed: 'completado', current: 'actual', pending: 'pendiente', event: 'evento detectado' })[value] || normalizeLabel(value);
}
function badge(value) { return `<span class="badge ${escapeHtml(value)}">${escapeHtml(normalizeLabel(value))}</span>`; }
function urgency(opportunity) {
  if (opportunity.urgency_label) return { label: opportunity.urgency_label, level: opportunity.urgency_level || 'low', days: opportunity.days_to_critical_date ?? null };
  const dateText = opportunity.next_critical_date;
  if (!dateText) return { label: 'Sin fecha crítica', level: 'low', days: null };
  const today = new Date();
  const date = new Date(dateText);
  const diffDays = Math.ceil((date.setHours(0,0,0,0) - today.setHours(0,0,0,0)) / 86400000);
  if (diffDays < 0) return { label: `Venció hace ${Math.abs(diffDays)} días`, level: 'high', days: diffDays };
  if (diffDays === 0) return { label: 'Vence hoy', level: 'high', days: diffDays };
  if (diffDays === 1) return { label: 'Vence mañana', level: 'medium', days: diffDays };
  if (diffDays <= 5) return { label: `Faltan ${diffDays} días`, level: 'medium', days: diffDays };
  return { label: `Faltan ${diffDays} días`, level: 'low', days: diffDays };
}
function recommendedAction(opportunity) {
  if (opportunity.recommended_action) return opportunity.recommended_action;
  if (opportunity.stage === 'contrato_suscrito') return 'Registrar ganador y alimentar inteligencia competitiva';
  if (opportunity.stage === 'buena_pro_otorgada') return 'Revisar ganador y preparar contacto comercial';
  if (opportunity.stage === 'proximo_buena_pro') return 'Monitorear buena pro esta semana';
  if (['cancelado', 'desierto', 'nulo'].includes(opportunity.outcome)) return 'Esperar reinicio o nueva convocatoria';
  if (opportunity.stage === 'reiniciado') return 'Revisar bases actualizadas hoy';
  return 'Revisar si aplica al rubro del cliente';
}
function priority(opportunity) {
  if (opportunity.priority_label) return opportunity.priority_label;
  if (opportunity.stage === 'contrato_suscrito' || opportunity.stage === 'buena_pro_otorgada') return 'Alta';
  const u = urgency(opportunity);
  if (u.level === 'high' || u.level === 'medium') return 'Alta';
  if (Number(opportunity.amount || 0) >= 500000) return 'Media';
  return 'Media';
}

function setView(viewId) {
  document.querySelectorAll('.view').forEach(view => view.classList.remove('active-view'));
  document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
  byId(viewId).classList.add('active-view');
  document.querySelectorAll(`[data-view="${viewId}"], [data-view-target="${viewId}"]`).forEach(link => link.classList.add('active'));
}

function renderMetricCards(opportunities) {
  const reviewToday = opportunities.filter(item => ['high', 'medium'].includes(urgency(item).level)).length;
  const nextAward = opportunities.filter(item => item.stage === 'proximo_buena_pro' || item.stage === 'convocado').length;
  const winners = opportunities.filter(item => item.winner_name).length;
  const restarted = opportunities.filter(item => item.stage === 'reiniciado' || item.outcome === 'reiniciado').length;
  byId('priority-cards').innerHTML = [
    ['Revisar hoy', reviewToday, 'Procesos con fecha cercana o vencida', 'high'],
    ['Buena pro próxima', nextAward, 'Procesos activos que requieren seguimiento', 'warning'],
    ['Ganador detectado', winners, 'Adjudicaciones para inteligencia competitiva', 'success'],
    ['Proceso reiniciado', restarted, 'Nuevas oportunidades luego de caída', 'warning'],
  ].map(([title, value, text, tone]) => `
    <article class="metric-card ${tone}">
      <span>${title}</span><strong>${value}</strong><span>${text}</span>
    </article>`).join('');
}

function renderPriorityList(opportunities) {
  byId('priority-list').innerHTML = opportunities.slice(0, 6).map(item => {
    const u = urgency(item);
    return `<article class="opportunity-card">
      <div>
        <button class="link-button" data-open-ocid="${escapeHtml(item.ocid)}"><h3>${escapeHtml(item.process_code)}</h3></button>
        <p>${escapeHtml(item.entity_name)} · ${escapeHtml(item.description)}</p>
        <div class="meta">${badge(item.stage)} ${badge(item.outcome)} <span class="badge ${u.level}">${escapeHtml(u.label)}</span> <span class="badge">Score ${escapeHtml(item.commercial_score ?? '—')}</span></div>
      </div>
      <strong>${formatMoney(item.amount)}</strong>
    </article>`;
  }).join('');
}

function renderAlerts(events) {
  const cards = events.slice(0, 6).map(event => `<article class="alert-card">
    <div class="meta">${badge(event.severity)} ${badge(event.event_type)}</div>
    <h3>${escapeHtml(event.title)}</h3>
    <p>${escapeHtml(event.message)}</p>
    <small>${formatDate(event.occurred_at)}</small>
  </article>`).join('');
  byId('recent-alerts').innerHTML = cards || '<p>No hay alertas recientes.</p>';

  const groups = [
    ['Críticas', events.filter(e => e.severity === 'high')],
    ['Importantes', events.filter(e => e.severity === 'medium')],
    ['Informativas', events.filter(e => !['high', 'medium'].includes(e.severity))],
  ];
  byId('alerts-groups').innerHTML = groups.map(([title, items]) => `<section class="panel">
    <h2>${title}</h2>
    <div class="alert-list">${items.map(event => `<article class="alert-card">
      <div class="meta">${badge(event.severity)} ${badge(event.event_type)}</div>
      <h3>${escapeHtml(event.title)}</h3>
      <p>${escapeHtml(event.message)}</p>
      <button class="ghost" data-open-ocid="${escapeHtml(event.ocid)}">Ver expediente</button>
    </article>`).join('') || '<p>Sin alertas.</p>'}</div>
  </section>`).join('');
}

function renderBars(containerId, counts) {
  const max = Math.max(1, ...Object.values(counts || {}));
  byId(containerId).innerHTML = Object.entries(counts || {}).map(([key, value]) => `<div class="bar-row">
    <span>${escapeHtml(normalizeLabel(key))}</span><div class="bar-track"><div class="bar-fill" style="width:${(value / max) * 100}%"></div></div><strong>${value}</strong>
  </div>`).join('') || '<p>Sin datos.</p>';
}

function setupFilters(data) {
  const stages = ['Todas las etapas', ...new Set(data.opportunities.map(item => item.stage).filter(Boolean))];
  const outcomes = ['Todos los resultados', ...new Set(data.opportunities.map(item => item.outcome).filter(Boolean))];
  byId('stage-filter').innerHTML = stages.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(normalizeLabel(item))}</option>`).join('');
  byId('outcome-filter').innerHTML = outcomes.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(normalizeLabel(item))}</option>`).join('');
}

function applyFilters() {
  const query = byId('search-input').value.toLowerCase();
  const stage = byId('stage-filter').value;
  const outcome = byId('outcome-filter').value;
  state.filtered = state.dashboard.opportunities.filter(item => {
    const haystack = `${item.process_code} ${item.entity_name} ${item.description}`.toLowerCase();
    return haystack.includes(query)
      && (stage === 'Todas las etapas' || item.stage === stage)
      && (outcome === 'Todos los resultados' || item.outcome === outcome);
  });
  renderTable(state.filtered);
}

function renderTable(opportunities) {
  byId('opportunities-table').innerHTML = opportunities.map(item => {
    const u = urgency(item);
    return `<tr>
      <td><span class="badge ${priority(item).toLowerCase()}">${priority(item)}</span><br><small>Score ${escapeHtml(item.commercial_score ?? '—')}</small></td>
      <td><button class="link-button" data-open-ocid="${escapeHtml(item.ocid)}">${escapeHtml(item.process_code)}</button><br><small>${escapeHtml(item.description)}</small></td>
      <td>${escapeHtml(item.entity_name)}</td>
      <td>${badge(item.stage)} ${badge(item.outcome)}</td>
      <td>${formatMoney(item.amount)}</td>
      <td>${badge(u.level)} ${escapeHtml(u.label)}</td>
      <td>${item.winner_name ? `${escapeHtml(item.winner_name)}<br><small>RUC ${escapeHtml(item.winner_ruc)} · ${formatMoney(item.awarded_amount)}</small>` : '—'}</td>
      <td>${escapeHtml(recommendedAction(item))}</td>
    </tr>`;
  }).join('');
}

function technicalSignalsSummary(analysis) {
  const signals = analysis?.technical_signals || {};
  if (!analysis || analysis.analysis_status !== 'analyzed') return '';
  const labels = {
    pilotes: 'Pilotes', zapatas: 'Zapatas', estribos: 'Estribos', tablero: 'Tablero',
    vigas: 'Vigas', planos: 'Planos', metrados: 'Metrados', presupuesto: 'Presupuesto', expediente_tecnico: 'Expediente técnico', cimentacion: 'Cimentación',
  };
  const items = Object.entries(labels).map(([key, label]) => {
    const status = signals[key]?.status;
    const css = status === 'detected' ? 'detected' : 'not-detected';
    const text = status === 'detected' ? 'detectado' : 'no detectado';
    return `<span class="signal ${css}">${label}: ${text}</span>`;
  });
  return items.length ? `<div class="technical-signals">${items.join('')}</div>` : '';
}

function documentStatus(document) {
  const verification = document.verification || {};
  if (verification.ok === true) return '<span class="doc-status available">Verificado</span>';
  if (verification.ok === false) return '<span class="doc-status unavailable">No verificado</span>';
  return '<span class="doc-status pending">Pendiente</span>';
}

function renderOfficialDocuments(item, documentsOverride = null) {
  const documents = documentsOverride || item.official_documents || [];
  if (!documents.length) {
    return `<div class="document-help">
      <p>No hay documentos oficiales publicados en el record OCDS de este expediente.</p>
      <p class="muted-copy">Si SEACE muestra anexos en navegador, puede requerir captura/evidencia manual.</p>
    </div>`;
  }
  return `<div class="document-help">
    <p>Ver documentos y verificar enlaces no consume créditos ni descargas. La descarga debe descontarse solo si el archivo baja correctamente.</p>
  </div><div class="document-list">${documents.map((document, index) => {
    const url = document.download_url || document.preview_url || '';
    const proxyUrl = `/api/documents/download?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(document.suggested_filename || document.title || 'documento-oficial')}`;
    const analysis = document.analysis || {};
    return `<article class="document-card ${analysis.analysis_status === 'analyzed' ? 'analyzed' : ''}">
      <div>
        <div class="doc-title-row"><strong>${escapeHtml(document.title || 'Documento oficial')}</strong>${documentStatus(document)}</div>
        <p>${escapeHtml(document.section || 'record')} · ${escapeHtml(document.document_type || 'documento')} · ${escapeHtml((document.format || '').toUpperCase() || 'archivo')} · ${formatDate(document.date_published)}</p>
        <small>${escapeHtml(document.verification?.message || 'Pendiente de verificar antes de descargar.')}</small>
        ${analysis.message ? `<p class="muted-copy">${escapeHtml(analysis.message)}</p>` : ''}
        ${technicalSignalsSummary(analysis)}
      </div>
      <div class="document-actions">
        <a class="ghost action-link" href="${escapeHtml(url || '#')}" target="_blank" rel="noopener noreferrer">Ver</a>
        <button class="ghost" data-doc-action="verify" data-doc-ocid="${escapeHtml(item.ocid)}">Verificar</button>
        <button class="ghost" data-doc-action="analyze" data-doc-ocid="${escapeHtml(item.ocid)}">Analizar señales</button>
        <a class="download-link" href="${escapeHtml(proxyUrl)}" download>Descargar verificada</a>
      </div>
    </article>`;
  }).join('')}</div>`;
}

function renderTechnicalSummary(summary = {}) {
  const labels = {
    pilotes: 'Pilotes', zapatas: 'Zapatas', estribos: 'Estribos', tablero: 'Tablero',
    vigas: 'Vigas', planos: 'Planos', metrados: 'Metrados', presupuesto: 'Presupuesto', expediente_tecnico: 'Expediente técnico', cimentacion: 'Cimentación',
  };
  return `<div class="technical-signals eto-summary">${Object.entries(labels).map(([key, label]) => {
    const status = summary[key] || 'not_analyzed';
    const text = status === 'detected' ? 'detectado' : status === 'not_detected' ? 'no detectado' : 'pendiente';
    const css = status === 'detected' ? 'detected' : status === 'not_detected' ? 'not-detected' : 'pending';
    return `<span class="signal ${css}">${label}: ${text}</span>`;
  }).join('')}</div>`;
}

function renderTechnicalFile(item, payload = null) {
  if (!payload) return '<p>Consultando Expediente Técnico de Obra (ETO)…</p>';
  const documents = payload.documents || [];
  const guides = payload.official_guides || [];
  return `<div class="document-help eto-help">
    <p><strong>Expediente Técnico de Obra:</strong> capa separada para obras. Según OECE, aparece en la Ficha de Selección cuando el procedimiento de Obra tiene registrada la opción “Ver Expediente Técnico de Obra”.</p>
    <p class="muted-copy">Estado: ${escapeHtml(payload.status)} · ${escapeHtml(payload.message || '')}</p>
  </div>
  ${renderTechnicalSummary(payload.technical_summary)}
  <details class="eto-sections" open>
    <summary>Secciones oficiales del ETO</summary>
    ${(payload.sections || []).map(section => `<div class="eto-section"><strong>${escapeHtml(section.title)}</strong><ul>${(section.official_components || []).map(component => `<li>${escapeHtml(component)}</li>`).join('')}</ul></div>`).join('')}
  </details>
  ${documents.length ? `<div class="document-list">${documents.map(document => {
    const url = document.download_url || document.preview_url || '';
    const proxyUrl = `/api/documents/download?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(document.suggested_filename || document.title || 'eto-documento')}`;
    return `<article class="document-card eto-card">
      <div>
        <div class="doc-title-row"><strong>${escapeHtml(document.title || 'Documento ETO')}</strong>${documentStatus(document)}</div>
        <p>${escapeHtml(document.eto_component || 'eto')} · ${escapeHtml((document.format || '').toUpperCase() || 'archivo')} · ${formatDate(document.date_published)}</p>
        <small>${escapeHtml(document.verification?.message || 'Pendiente de verificar antes de descargar.')}</small>
        ${document.analysis?.message ? `<p class="muted-copy">${escapeHtml(document.analysis.message)}</p>` : ''}
        ${technicalSignalsSummary(document.analysis)}
      </div>
      <div class="document-actions">
        <a class="ghost action-link" href="${escapeHtml(url || '#')}" target="_blank" rel="noopener noreferrer">Ver</a>
        <button class="ghost" data-eto-action="verify" data-eto-ocid="${escapeHtml(item.ocid)}">Verificar ETO</button>
        <button class="ghost" data-eto-action="analyze" data-eto-ocid="${escapeHtml(item.ocid)}">Analizar ETO</button>
        <a class="download-link" href="${escapeHtml(proxyUrl)}" download>Descargar verificada</a>
      </div>
    </article>`;
  }).join('')}</div>` : `<div class="document-help"><p>No se detectaron archivos ETO en OCDS. Revisa la <strong>Ficha de Selección</strong> oficial y busca el ícono “Ver Expediente Técnico de Obra”.</p></div>`}
  ${guides.map(guide => `<p class="muted-copy"><a href="${escapeHtml(guide.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(guide.title)}</a></p>`).join('')}`;
}

async function openDetail(ocid) {
  const response = await fetch(`/api/opportunities/${encodeURIComponent(ocid)}`);
  if (!response.ok) return;
  const detail = await response.json();
  const item = detail.opportunity;
  const officialSourceUrl = item.official_source_url || 'https://prodapp2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml';
  const exportUrl = `/api/opportunities/${encodeURIComponent(item.ocid)}/export`;
  byId('detail-content').innerHTML = `<section class="detail-hero">
    <div class="panel detail-title">
      <p class="eyebrow">Expediente SEACE/OECE</p>
      <h1>${escapeHtml(item.process_code)}</h1>
      <p>${escapeHtml(item.description)}</p>
      <div class="meta">${badge(item.stage)} ${badge(item.outcome)} ${badge(urgency(item).level)} <span class="badge">${escapeHtml(urgency(item).label)}</span> <span class="badge">Score ${escapeHtml(item.commercial_score ?? '—')}</span></div>
      <div class="action-row">
        <a class="primary-action action-link" href="${escapeHtml(officialSourceUrl)}" target="_blank" rel="noopener noreferrer">Ver fuente oficial</a>
        <button class="ghost" data-ficha-ocid="${escapeHtml(item.ocid)}">Ver ficha SEACE</button>
        <a class="ghost action-link" href="${escapeHtml(exportUrl)}" download>Exportar expediente</a>
        <button class="ghost">Marcar como revisado</button>
      </div>
    </div>
    <aside class="panel">
      <h2>Acción recomendada</h2>
      <p>${escapeHtml(recommendedAction(item))}</p>
      <p class="meta">Razones: ${(item.commercial_reasons || []).map(escapeHtml).join(' · ') || 'Sin razones comerciales calculadas'}</p>
      <div class="kv">
        <div><span>Entidad</span><strong>${escapeHtml(item.entity_name)}</strong></div>
        <div><span>Monto ref.</span><strong>${formatMoney(item.amount)}</strong></div>
        <div><span>OCID</span><strong>${escapeHtml(item.ocid)}</strong></div>
        <div><span>Fecha crítica</span><strong>${formatDate(item.next_critical_date)}</strong></div>
      </div>
    </aside>
  </section>
  <section class="dashboard-grid two">
    <div class="panel">
      <h2>Inteligencia competitiva</h2>
      ${item.winner_name ? `<div class="kv">
        <div><span>Ganador</span><strong>${escapeHtml(item.winner_name)}</strong></div>
        <div><span>RUC</span><strong>${escapeHtml(item.winner_ruc)}</strong></div>
        <div><span>Monto adjudicado</span><strong>${formatMoney(item.awarded_amount)}</strong></div>
        <div><span>Fecha buena pro</span><strong>${formatDate(item.award_date)}</strong></div>
      </div>` : '<p>Aún no hay ganador. Mantener seguimiento hasta buena pro.</p>'}
    </div>
    <div class="panel" id="official-documents-panel">
      <h2>Documentos oficiales</h2>
      <div id="official-documents-content">${renderOfficialDocuments(item)}</div>
    </div>
    <div class="panel" id="technical-file-panel">
      <h2>Expediente Técnico de Obra</h2>
      <div id="technical-file-content">${renderTechnicalFile(item)}</div>
    </div>
  </section>
  <section class="dashboard-grid two">
    <div class="panel wide-panel" id="ficha-viewer-panel" hidden>
      <h2>Ficha de Selección SEACE</h2>
      <div id="ficha-viewer-content"></div>
    </div>
  </section>
  <section class="dashboard-grid two">
    <div class="panel wide-panel">
      <h2>Timeline del proceso</h2>
      <div class="timeline">${detail.timeline.map(event => `<div class="timeline-item ${escapeHtml(event.status)}">
        <span class="timeline-dot"></span><div><strong>${escapeHtml(event.title)}</strong><br><small>${formatDate(event.date)} · ${escapeHtml(event.description || statusLabel(event.status))}</small></div>
      </div>`).join('')}</div>
    </div>
  </section>`;
  setView('detail-view');
  loadOfficialDocuments(item.ocid, false);
  loadTechnicalFile(item.ocid, false);
}

async function loadOfficialDocuments(ocid, analyze = false) {
  const container = byId('official-documents-content');
  if (!container || !ocid) return;
  container.innerHTML = '<p>Verificando documentos oficiales SEACE/OECE…</p>';
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(ocid)}/documents?verify=true&analyze=${analyze ? 'true' : 'false'}`);
    if (!response.ok) throw new Error('No se pudieron consultar documentos');
    const payload = await response.json();
    state.documentCache[ocid] = payload.documents || [];
    const item = { ocid, official_documents: state.documentCache[ocid] };
    container.innerHTML = renderOfficialDocuments(item, state.documentCache[ocid]);
    if (payload.browser_help) {
      container.insertAdjacentHTML('beforeend', `<p class="muted-copy browser-help">${escapeHtml(payload.browser_help)}</p>`);
    }
  } catch (error) {
    container.innerHTML = `<p>No se pudieron verificar documentos. No debe consumirse descarga. ${escapeHtml(error.message)}</p>`;
  }
}

async function loadTechnicalFile(ocid, analyze = false) {
  const container = byId('technical-file-content');
  if (!container || !ocid) return;
  container.innerHTML = '<p>Consultando Expediente Técnico de Obra (ETO)…</p>';
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(ocid)}/eto?verify=true&analyze=${analyze ? 'true' : 'false'}`);
    if (!response.ok) throw new Error('No se pudo consultar el ETO');
    const payload = await response.json();
    container.innerHTML = renderTechnicalFile({ ocid }, payload);
  } catch (error) {
    container.innerHTML = `<p>No se pudo consultar el ETO. ${escapeHtml(error.message)}</p>`;
  }
}

function renderFichaViewer(payload) {
  const embedUrl = payload.embed_url || payload.source_url || '#';
  return `<div class="document-help ficha-help">
    <p><strong>Buscador Público SEACE:</strong> ${escapeHtml(payload.message || '')}</p>
    <div class="kv compact-kv">
      <div><span>Nomenclatura</span><strong>${escapeHtml(payload.process_code || '—')}</strong></div>
      <div><span>Entidad</span><strong>${escapeHtml(payload.entity_name || '—')}</strong></div>
      <div><span>Modo de visor</span><strong>Vista oficial embebida</strong></div>
    </div>
    <ol>${(payload.steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ol>
    <div class="action-row">
      <button class="primary-action" type="button" data-capture-ficha-ocid="${escapeHtml(payload.ocid || '')}">Buscar ficha automáticamente</button>
      <a class="ghost action-link" href="${escapeHtml(payload.source_url || '#')}" target="_blank" rel="noopener noreferrer">Abrir en pestaña externa</a>
      <button class="ghost" type="button" data-copy-process="${escapeHtml(payload.process_code || '')}">Copiar nomenclatura</button>
    </div>
    <div id="ficha-capture-content"></div>
    <p class="muted-copy">${escapeHtml(payload.note || '')}</p>
  </div>
  <div class="seace-iframe-wrap">
    <div class="iframe-toolbar">
      <strong>Vista oficial embebida SEACE</strong>
      <span class="muted-copy">Si el portal no carga por bloqueo del navegador, usa “Abrir en pestaña externa”.</span>
    </div>
    <iframe class="seace-iframe" src="${escapeHtml(embedUrl)}" title="Ficha de Selección SEACE" loading="lazy" referrerpolicy="no-referrer-when-downgrade" sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-downloads"></iframe>
  </div>`;
}

async function loadFichaViewer(ocid) {
  const panel = byId('ficha-viewer-panel');
  const container = byId('ficha-viewer-content');
  if (!panel || !container || !ocid) return;
  panel.hidden = false;
  container.innerHTML = '<p>Preparando acceso a la Ficha de Selección SEACE…</p>';
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(ocid)}/ficha`);
    if (!response.ok) throw new Error('No se pudo preparar la ficha');
    const payload = await response.json();
    container.innerHTML = renderFichaViewer(payload);
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    container.innerHTML = `<p>No se pudo preparar la ficha SEACE. ${escapeHtml(error.message)}</p>`;
  }
}

function renderFichaCapture(payload) {
  const steps = payload.steps_completed || [];
  return `<div class="ficha-capture-result">
    <div class="doc-title-row">
      <strong>${escapeHtml(payload.message || 'Captura de ficha generada')}</strong>
      <span class="doc-status ${payload.status === 'captured' ? 'available' : 'pending'}">${escapeHtml(payload.status || 'captured')}</span>
    </div>
    <p class="muted-copy">Capturado: ${escapeHtml(payload.captured_at || '—')} · Nomenclatura: ${escapeHtml(payload.process_code || '—')}</p>
    ${steps.length ? `<p class="muted-copy">Pasos: ${steps.map(escapeHtml).join(' → ')}</p>` : ''}
    ${payload.image_url ? `<a href="${escapeHtml(payload.image_url)}" target="_blank" rel="noopener noreferrer"><img class="ficha-capture-image" src="${escapeHtml(payload.image_url)}" alt="Captura automática de la Ficha de Selección SEACE"></a>` : ''}
  </div>`;
}

async function loadFichaCapture(ocid) {
  const container = byId('ficha-capture-content');
  if (!container || !ocid) return;
  container.innerHTML = '<p>Buscando automáticamente en SEACE y capturando ficha… Esto puede demorar.</p>';
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(ocid)}/ficha/capture`, { method: 'POST' });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'No se pudo capturar la ficha');
    container.innerHTML = renderFichaCapture(payload);
  } catch (error) {
    container.innerHTML = `<div class="document-help"><p>No se pudo automatizar la ficha SEACE. Mantén el visor manual como respaldo.</p><p class="muted-copy">${escapeHtml(error.message)}</p></div>`;
  }
}

function renderNoResultsAdvice() {
  const advice = state.lastSearchAdvice || [];
  const list = advice.length
    ? `<ul>${advice.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
    : '<p>Prueba con una palabra más general o menor monto mínimo.</p>';
  return `<div class="panel no-results-advice">
    <h2>Sin resultados por ahora</h2>
    <p>No significa que no existan oportunidades. Probablemente los filtros están demasiado cerrados.</p>
    ${list}
    <div class="search-card-actions">
      <button class="primary-action" type="button" id="relax-search-filters">Ampliar búsqueda automáticamente</button>
      <button class="ghost" type="button" id="recommended-search-preset-inline">Usar configuración recomendada</button>
    </div>
  </div>`;
}

function renderSearchResults(results) {
  const container = byId('search-results');
  if (!results.length) {
    byId('search-pagination').innerHTML = '';
    container.innerHTML = renderNoResultsAdvice();
    return;
  }
  container.innerHTML = results.map(item => `<article class="panel search-result-card">
    <div>
      <p class="eyebrow">${escapeHtml(item.keyword || 'SEACE')}</p>
      <h2>${escapeHtml(item.process_code || 'Sin nomenclatura')}</h2>
      <p>${escapeHtml(item.description || '')}</p>
      <div class="meta">${badge(item.priority_label || 'Prioridad')} <span class="badge probability-badge">Probabilidad ${escapeHtml(item.commercial_score ?? 0)}/100</span> ${badge(item.category || 'obra')} <span class="badge">${formatMoney(item.amount)}</span> <span class="badge">${formatDate(item.tender_end_date)}</span></div>
      <p><strong>Acción recomendada:</strong> ${escapeHtml(item.recommended_action || 'Revisar expediente y documentos oficiales.')}</p>
      <p class="muted-copy"><strong>Por qué:</strong> ${escapeHtml((item.commercial_reasons || []).join(', ') || 'Coincidencia por búsqueda y reglas guardadas.')}</p>
      <div class="kv compact-kv">
        <div><span>Entidad</span><strong>${escapeHtml(item.entity_name || '—')}</strong></div>
        <div><span>OCID</span><strong>${escapeHtml(item.ocid || '—')}</strong></div>
      </div>
    </div>
    <div class="search-card-actions">
      <a class="ghost action-link" href="${escapeHtml(item.record_url || item.api_url || '#')}" target="_blank" rel="noopener noreferrer">Ver record API</a>
      <button class="primary-action" data-tooltip-id="tooltip-track-action" data-track-ocid="${escapeHtml(item.ocid)}" data-tooltip="¿Qué significa? Guarda este proceso en la bandeja para vigilar buena pro, contrato, desierto, cancelación o cambios." aria-label="Agregar a seguimiento: guarda este proceso para vigilar cambios" title="Guarda este proceso en la bandeja para vigilar cambios.">Agregar a seguimiento</button>
      <button class="ghost" data-tooltip-id="tooltip-dismiss-action" data-dismiss-ocid="${escapeHtml(item.ocid)}" data-tooltip="¿Qué significa? Oculta este resultado de futuras búsquedas. Puedes restaurarlo desde Configuración." aria-label="Descartar: oculta este resultado de futuras búsquedas" title="Oculta este resultado de futuras búsquedas; puedes restaurarlo.">Descartar</button>
    </div>
  </article>`).join('');
}

function renderSearchPagination() {
  const total = state.searchResults.length;
  const totalPages = Math.max(1, Math.ceil(total / state.searchPageSize));
  byId('search-pagination').innerHTML = total ? `
    <button class="ghost" id="searchPrevPage" ${state.searchPage <= 1 ? 'disabled' : ''}>Anterior</button>
    <span>Página ${state.searchPage} de ${totalPages}</span>
    <button class="ghost" id="searchNextPage" ${state.searchPage >= totalPages ? 'disabled' : ''}>Siguiente</button>
  ` : '';
}

function renderSearchPage() {
  const start = (state.searchPage - 1) * state.searchPageSize;
  const pageItems = state.searchResults.slice(start, start + state.searchPageSize);
  renderSearchResults(pageItems);
  renderSearchPagination();
}

function applyRecommendedSearchPreset() {
  byId('new-search-keywords').value = 'puente';
  byId('new-search-contract-object').value = 'obra';
  byId('new-search-entity').value = '';
  byId('new-search-selection-type').value = '';
  byId('new-search-description').value = 'puente';
  byId('new-search-min-amount').value = '3000000';
  byId('new-search-publication-from').value = '';
  byId('new-search-publication-to').value = '';
  byId('new-search-convocatoria-from').value = '';
  byId('new-search-convocatoria-to').value = '';
  byId('search-status').textContent = 'Configuración recomendada para puentes aplicada (monto mínimo S/ 3.000.000). Si salen muy pocos, baja el monto o cambia el año.';
}

function applyRelaxedSearchFilters() {
  const relaxed = state.lastRecommendedRelaxation || {};
  if ('contract_object' in relaxed) byId('new-search-contract-object').value = relaxed.contract_object || '';
  if ('entity_name' in relaxed) byId('new-search-entity').value = relaxed.entity_name || '';
  if ('selection_type' in relaxed) byId('new-search-selection-type').value = relaxed.selection_type || '';
  if ('description_filter' in relaxed) byId('new-search-description').value = relaxed.description_filter || '';
  if ('min_amount' in relaxed) byId('new-search-min-amount').value = String(relaxed.min_amount ?? 0);
  if ('publication_from' in relaxed) byId('new-search-publication-from').value = relaxed.publication_from || '';
  if ('publication_to' in relaxed) byId('new-search-publication-to').value = relaxed.publication_to || '';
  if ('convocatoria_from' in relaxed) byId('new-search-convocatoria-from').value = relaxed.convocatoria_from || '';
  if ('convocatoria_to' in relaxed) byId('new-search-convocatoria-to').value = relaxed.convocatoria_to || '';
  byId('search-status').textContent = 'Filtros ampliados. Presiona Buscar en todo SEACE para probar de nuevo.';
}

async function runNewSearch(event) {
  event.preventDefault();
  const status = byId('search-status');
  const keywords = byId('new-search-keywords').value.trim();
  const minAmount = byId('new-search-min-amount').value || '0';
  const contractObject = byId('new-search-contract-object').value;
  const entityName = byId('new-search-entity').value.trim();
  const selectionType = byId('new-search-selection-type').value.trim();
  const descriptionFilter = byId('new-search-description').value.trim();
  const publicationFrom = byId('new-search-publication-from').value;
  const publicationTo = byId('new-search-publication-to').value;
  const convocatoriaFrom = byId('new-search-convocatoria-from').value;
  const convocatoriaTo = byId('new-search-convocatoria-to').value;
  status.textContent = 'Buscando en todo SEACE/OECE con filtros… puede tardar unos segundos.';
  byId('search-results').innerHTML = '';
  byId('search-pagination').innerHTML = '';
  const params = new URLSearchParams({
    keywords,
    min_amount: minAmount,
    max_pages: '20',
    paginate_by: '50',
    result_limit: '100',
    contract_object: contractObject,
    entity_name: entityName,
    selection_type: selectionType,
    description_filter: descriptionFilter,
    publication_from: publicationFrom,
    publication_to: publicationTo,
    convocatoria_from: convocatoriaFrom,
    convocatoria_to: convocatoriaTo,
  });
  const response = await fetch(`/api/search?${params}`);
  if (!response.ok) {
    status.textContent = 'No se pudo completar la búsqueda.';
    return;
  }
  const data = await response.json();
  state.lastSearchAdvice = data.search_advice || [];
  state.lastRecommendedRelaxation = data.recommended_relaxation || null;
  const shown = data.count || 0;
  const total = data.total_found ?? shown;
  const ignored = data.ignored_count || 0;
  const filteredOut = data.filtered_out_count || 0;
  const ignoredText = ignored ? ` (${ignored} descartado(s) ocultos)` : '';
  const filteredText = filteredOut ? ` Filtros SEACE ocultaron ${filteredOut} resultado(s) no pertinentes.` : '';
  status.textContent = total > shown
    ? `Encontré ${total} resultado(s). Te muestro los mejores ${shown} para revisar primero.${ignoredText}${filteredText}`
    : `${shown} resultado(s) encontrados para ${data.keywords.join(', ')}.${ignoredText}${filteredText}`;
  state.searchResults = (data.results || []).sort((a, b) => ((b.commercial_score || 0) - (a.commercial_score || 0)) || ((b.amount || 0) - (a.amount || 0)));
  state.searchPage = 1;
  state.searchPageSize = Number(byId('search-page-size').value || 25);
  renderSearchPage();
}

async function trackOcid(ocid, button) {
  if (!ocid) return;
  button.disabled = true;
  button.textContent = 'Agregando…';
  const response = await fetch('/api/track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ocids: [ocid] }),
  });
  if (!response.ok) {
    button.disabled = false;
    button.textContent = 'Agregar a seguimiento';
    byId('search-status').textContent = 'No se pudo agregar al seguimiento.';
    return;
  }
  state.dashboard = await (await fetch('/api/dashboard')).json();
  state.filtered = state.dashboard.opportunities;
  renderMetricCards(state.dashboard.opportunities);
  renderPriorityList(state.dashboard.opportunities);
  renderAlerts(state.dashboard.recent_events);
  renderBars('stage-bars', state.dashboard.counts_by_stage);
  renderBars('outcome-bars', state.dashboard.counts_by_outcome);
  setupFilters(state.dashboard);
  renderTable(state.filtered);
  button.textContent = 'Agregado ✓';
  byId('search-status').textContent = 'Expediente agregado al seguimiento y dashboard actualizado.';
}

async function dismissOcid(ocid, button) {
  if (!ocid) return;
  button.disabled = true;
  button.textContent = 'Descartando…';
  const response = await fetch('/api/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ocid }),
  });
  if (!response.ok) {
    button.disabled = false;
    button.textContent = 'Descartar';
    byId('search-status').textContent = 'No se pudo descartar este resultado.';
    return;
  }
  state.settings = await response.json();
  state.searchResults = state.searchResults.filter(item => item.ocid !== ocid);
  const totalPages = Math.max(1, Math.ceil(state.searchResults.length / state.searchPageSize));
  state.searchPage = Math.min(state.searchPage, totalPages);
  renderSearchPage();
  byId('search-status').textContent = 'Resultado descartado. Ya no aparecerá en búsquedas futuras mientras esté oculto.';
}

async function restoreDismissedOcid(ocid, button) {
  if (!ocid) return;
  button.disabled = true;
  button.textContent = 'Restaurando…';
  const response = await fetch('/api/dismiss/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ocid }),
  });
  if (!response.ok) {
    button.disabled = false;
    button.textContent = 'Restaurar';
    byId('settings-status').textContent = 'No se pudo restaurar este resultado.';
    return;
  }
  state.settings = await response.json();
  renderSettings();
  byId('settings-status').textContent = 'Resultado restaurado. Volverá a aparecer si coincide con tu búsqueda.';
}

function renderEditableList(containerId, items, deleteAttribute) {
  const container = byId(containerId);
  container.innerHTML = (items || []).map((item, index) => `
    <span class="editable-chip">${escapeHtml(item)} <button type="button" ${deleteAttribute}="${index}" aria-label="Eliminar ${escapeHtml(item)}">×</button></span>
  `).join('');
}

function renderCustomVariables(items) {
  byId('settings-custom-list').innerHTML = (items || []).map((item, index) => `
    <div class="custom-variable-item">
      <strong>${escapeHtml(item.name)}</strong>
      <span>${escapeHtml(item.value)}</span>
      <button class="ghost" type="button" data-delete-custom="${index}">Borrar</button>
    </div>
  `).join('') || '<p class="muted-copy">Sin variables personalizadas todavía.</p>';
}

function renderIgnoredOcids(items) {
  byId('settings-ignored-list').innerHTML = (items || []).map(ocid => `
    <div class="custom-variable-item ignored-item">
      <strong>${escapeHtml(ocid)}</strong>
      <span>Oculto en búsqueda</span>
      <button class="ghost" type="button" data-restore-ocid="${escapeHtml(ocid)}">Restaurar</button>
    </div>
  `).join('') || '<p class="muted-copy">No hay resultados descartados.</p>';
}

function renderSettings() {
  const settings = state.settings;
  if (!settings) return;
  byId('settings-client-name').value = settings.client_name || '';
  byId('settings-business-line').value = settings.business_line || '';
  byId('settings-min-amount').value = settings.min_amount ?? 0;
  byId('settings-frequency').value = settings.frequency || 'diario';
  byId('new-search-keywords').value = (settings.keywords || []).join(', ');
  byId('new-search-min-amount').value = settings.min_amount ?? 0;
  renderEditableList('settings-keyword-list', settings.keywords || [], 'data-delete-keyword');
  renderEditableList('settings-channel-list', settings.channels || [], 'data-delete-channel');
  renderCustomVariables(settings.custom_variables || []);
  renderIgnoredOcids(settings.ignored_ocids || []);
}

function addListValue(listName, inputId) {
  syncSettingsFromInputs();
  const value = byId(inputId).value.trim();
  if (!value) return;
  state.settings[listName] = Array.from(new Set([...(state.settings[listName] || []), value]));
  byId(inputId).value = '';
  renderSettings();
}

function syncSettingsFromInputs() {
  if (!state.settings) return;
  state.settings.client_name = byId('settings-client-name').value.trim();
  state.settings.business_line = byId('settings-business-line').value.trim();
  state.settings.min_amount = Number(byId('settings-min-amount').value || 0);
  state.settings.frequency = byId('settings-frequency').value;
}

function collectSettingsFromForm() {
  syncSettingsFromInputs();
  return {
    client_name: byId('settings-client-name').value.trim(),
    business_line: byId('settings-business-line').value.trim(),
    keywords: state.settings.keywords || [],
    min_amount: Number(byId('settings-min-amount').value || 0),
    frequency: byId('settings-frequency').value,
    channels: state.settings.channels || [],
    custom_variables: state.settings.custom_variables || [],
    ignored_ocids: state.settings.ignored_ocids || [],
  };
}

async function saveSettings(event) {
  event.preventDefault();
  const status = byId('settings-status');
  status.textContent = 'Guardando…';
  const response = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectSettingsFromForm()),
  });
  if (!response.ok) {
    status.textContent = 'No se pudo guardar la configuración.';
    return;
  }
  state.settings = await response.json();
  renderSettings();
  status.textContent = 'Configuración guardada. Ya se usa como búsqueda por defecto.';
}

async function loadSettings() {
  const response = await fetch('/api/settings');
  state.settings = await response.json();
  renderSettings();
}

function bindEvents() {
  document.addEventListener('click', event => {
    const viewTarget = event.target.closest('[data-view-target]');
    const navTarget = event.target.closest('[data-view]');
    const ocidTarget = event.target.closest('[data-open-ocid]');
    const trackTarget = event.target.closest('[data-track-ocid]');
    const dismissTarget = event.target.closest('[data-dismiss-ocid]');
    const restoreTarget = event.target.closest('[data-restore-ocid]');
    const docActionTarget = event.target.closest('[data-doc-action]');
    const etoActionTarget = event.target.closest('[data-eto-action]');
    const fichaTarget = event.target.closest('[data-ficha-ocid]');
    const captureFichaTarget = event.target.closest('[data-capture-ficha-ocid]');
    const copyProcessTarget = event.target.closest('[data-copy-process]');
    if (viewTarget) setView(viewTarget.dataset.viewTarget);
    if (navTarget) setView(navTarget.dataset.view);
    if (ocidTarget) openDetail(ocidTarget.dataset.openOcid);
    if (trackTarget) trackOcid(trackTarget.dataset.trackOcid, trackTarget);
    if (dismissTarget) dismissOcid(dismissTarget.dataset.dismissOcid, dismissTarget);
    if (restoreTarget) restoreDismissedOcid(restoreTarget.dataset.restoreOcid, restoreTarget);
    if (docActionTarget) loadOfficialDocuments(docActionTarget.dataset.docOcid, docActionTarget.dataset.docAction === 'analyze');
    if (etoActionTarget) loadTechnicalFile(etoActionTarget.dataset.etoOcid, etoActionTarget.dataset.etoAction === 'analyze');
    if (fichaTarget) loadFichaViewer(fichaTarget.dataset.fichaOcid);
    if (captureFichaTarget) loadFichaCapture(captureFichaTarget.dataset.captureFichaOcid);
    if (copyProcessTarget && copyProcessTarget.dataset.copyProcess) {
      navigator.clipboard?.writeText(copyProcessTarget.dataset.copyProcess);
      copyProcessTarget.textContent = 'Nomenclatura copiada';
    }
    if (event.target.id === 'relax-search-filters') applyRelaxedSearchFilters();
    if (event.target.id === 'recommended-search-preset-inline') applyRecommendedSearchPreset();
    if (event.target.id === 'searchPrevPage' && state.searchPage > 1) {
      state.searchPage -= 1;
      renderSearchPage();
    }
    if (event.target.id === 'searchNextPage') {
      const totalPages = Math.ceil(state.searchResults.length / state.searchPageSize);
      if (state.searchPage < totalPages) {
        state.searchPage += 1;
        renderSearchPage();
      }
    }
    const deleteKeyword = event.target.closest('[data-delete-keyword]');
    const deleteChannel = event.target.closest('[data-delete-channel]');
    const deleteCustom = event.target.closest('[data-delete-custom]');
    if (deleteKeyword) {
      syncSettingsFromInputs();
      state.settings.keywords.splice(Number(deleteKeyword.dataset.deleteKeyword), 1);
      renderSettings();
    }
    if (deleteChannel) {
      syncSettingsFromInputs();
      state.settings.channels.splice(Number(deleteChannel.dataset.deleteChannel), 1);
      renderSettings();
    }
    if (deleteCustom) {
      syncSettingsFromInputs();
      state.settings.custom_variables.splice(Number(deleteCustom.dataset.deleteCustom), 1);
      renderSettings();
    }
    if (event.target.id === 'settings-add-keyword') addListValue('keywords', 'settings-new-keyword');
    if (event.target.id === 'settings-add-channel') addListValue('channels', 'settings-new-channel');
    if (event.target.id === 'settings-add-custom') {
      syncSettingsFromInputs();
      const name = byId('settings-custom-name').value.trim();
      const value = byId('settings-custom-value').value.trim();
      if (name) {
        state.settings.custom_variables.push({ name, value });
        byId('settings-custom-name').value = '';
        byId('settings-custom-value').value = '';
        renderSettings();
      }
    }
  });
  byId('new-search-form').addEventListener('submit', runNewSearch);
  byId('recommended-search-preset').addEventListener('click', applyRecommendedSearchPreset);
  byId('settings-form').addEventListener('submit', saveSettings);
  byId('market-intel-form')?.addEventListener('submit', runMarketIntel);
  byId('search-page-size').addEventListener('change', event => {
    state.searchPageSize = Number(event.target.value || 25);
    state.searchPage = 1;
    renderSearchPage();
  });
  ['search-input', 'stage-filter', 'outcome-filter'].forEach(id => byId(id).addEventListener('input', applyFilters));
}

// ── Market Intelligence ───────────────────────────────────────────────────────
async function runMarketIntel(event) {
  event && event.preventDefault();
  const status = byId('market-intel-status');
  const resultsEl = byId('market-intel-results');
  const keyword = byId('market-intel-keyword')?.value?.trim() || '';
  const year = byId('market-intel-year')?.value || '';
  if (status) status.textContent = 'Consultando CONOSCE… puede tardar si el archivo no está en caché.';
  if (resultsEl) resultsEl.innerHTML = '';

  try {
    const params = new URLSearchParams({ keyword, year });
    const response = await fetch(`/api/market-intel?${params}`);
    const data = await response.json();

    if (status) {
      status.textContent = data.status === 'unavailable'
        ? data.message || 'No disponible.'
        : `${data.total_records.toLocaleString('es-PE')} convocatorias encontradas · S/ ${(data.total_amount || 0).toLocaleString('es-PE', { maximumFractionDigits: 0 })} total`;
    }

    if (resultsEl) {
      resultsEl.innerHTML = `
        <div class="dashboard-grid">
          ${renderRankingPanel('Entidades que más compran', data.top_entities || [], 'name', 'count', 'procesos')}
          ${renderRankingPanel('Categorías de contratación', data.top_categories || [], 'name', 'count', 'procesos')}
          ${renderRankingPanel('Ganadores recurrentes', data.top_winners || [], 'name', 'count', 'adj.')}
        </div>
        ${data.sample_records?.length ? `<div class="panel">
          <h2>Muestra de registros</h2>
          <div class="table-wrap"><table>
            <thead><tr><th>Entidad</th><th>Descripción</th><th>Monto</th><th>Código</th></tr></thead>
            <tbody>${data.sample_records.map(r => `<tr>
              <td>${escapeHtml(r.entity || '')}</td>
              <td>${escapeHtml(r.description || '')}</td>
              <td>${formatMoney(r.amount)}</td>
              <td>${escapeHtml(r.process_code || '')}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>` : ''}
      `;
    }
  } catch (error) {
    if (status) status.textContent = `Error: ${escapeHtml(error.message)}`;
  }
}

function renderRankingPanel(title, items, nameKey, countKey, unit = '') {
  if (!items.length) return `<div class="panel"><h2>${escapeHtml(title)}</h2><p>Sin datos.</p></div>`;
  const max = Math.max(1, ...items.map(item => item[countKey] || 0));
  return `<div class="panel">
    <h2>${escapeHtml(title)}</h2>
    <div class="bars">${items.map(item => `<div class="bar-row">
      <span title="${escapeHtml(item[nameKey])}">${escapeHtml(String(item[nameKey] || '').slice(0, 35))}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${((item[countKey] || 0) / max) * 100}%"></div></div>
      <strong>${item[countKey]} ${escapeHtml(unit)}</strong>
    </div>`).join('')}</div>
  </div>`;
}

async function start() {
  const response = await fetch('/api/dashboard');
  state.dashboard = await response.json();
  await loadSettings();
  state.filtered = state.dashboard.opportunities;
  renderMetricCards(state.dashboard.opportunities);
  renderPriorityList(state.dashboard.opportunities);
  renderAlerts(state.dashboard.recent_events);
  renderBars('stage-bars', state.dashboard.counts_by_stage);
  renderBars('outcome-bars', state.dashboard.counts_by_outcome);
  setupFilters(state.dashboard);
  renderTable(state.filtered);
  bindEvents();
}

async function bootstrap() {
  await initAuth();
  await start();
}

bootstrap().catch(error => {
  document.body.insertAdjacentHTML('beforeend', `<pre class="fatal-error">No se pudo cargar el dashboard: ${escapeHtml(error.message)}</pre>`);
});
