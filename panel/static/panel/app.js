(function () {
  'use strict';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const money = (n) => Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const data = (id) => { const el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; };

  /* ---------- menú móvil, avisos, selector de empresa ---------- */
  const menuBtn = $('#menu-btn'), sidebar = $('#sidebar');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== menuBtn) sidebar.classList.remove('open');
    });
  }
  $$('.toast').forEach((toast) => {
    const close = () => toast.remove();
    $('button', toast).addEventListener('click', close);
    setTimeout(close, toast.classList.contains('error') ? 9000 : 4500);
  });
  $$('[data-autosubmit]').forEach((el) => el.addEventListener('change', () => el.form.submit()));

  /* ---------- confirmaciones ---------- */
  document.addEventListener('submit', (e) => {
    const msg = e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
    const ask = e.target.dataset.prompt;
    if (ask) {
      const reason = window.prompt(ask);
      if (!reason || !reason.trim()) { e.preventDefault(); return; }
      const hidden = e.target.querySelector('input[name=reason]');
      if (hidden) hidden.value = reason.trim();
    }
  });

  /* ---------- búsqueda y orden en tablas ---------- */
  $$('[data-filter]').forEach((input) => {
    const table = $(input.dataset.filter);
    if (!table) return;
    const counter = input.dataset.count ? $(input.dataset.count) : null;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0;
      $$('tbody tr[data-row]', table).forEach((row) => {
        const hit = !q || row.textContent.toLowerCase().includes(q);
        row.hidden = !hit;
        if (hit) shown += 1;
      });
      if (counter) counter.textContent = shown;
    });
  });

  const cellValue = (row, index) => {
    const cell = row.children[index];
    if (!cell) return '';
    const raw = cell.dataset.sort !== undefined ? cell.dataset.sort : cell.textContent.trim();
    const num = parseFloat(String(raw).replace(/[^0-9.\-]/g, ''));
    return cell.dataset.sort !== undefined || (/^-?[\d,]+(\.\d+)?/.test(String(raw)) && !isNaN(num)) ? num : String(raw).toLowerCase();
  };
  $$('table').forEach((table) => {
    $$('th[data-sort]', table).forEach((th, _i, all) => {
      th.addEventListener('click', () => {
        const index = Array.from(th.parentElement.children).indexOf(th);
        const dir = th.classList.contains('asc') ? -1 : 1;
        all.forEach((h) => h.classList.remove('asc', 'desc'));
        th.classList.add(dir === 1 ? 'asc' : 'desc');
        const body = $('tbody', table);
        const rows = $$('tr[data-row]', body);
        rows.sort((a, b) => {
          const x = cellValue(a, index), y = cellValue(b, index);
          return (x > y ? 1 : x < y ? -1 : 0) * dir;
        });
        rows.forEach((r) => body.appendChild(r));
      });
    });
  });

  /* ---------- filas dinámicas del formulario de presupuesto ---------- */
  const lines = $('#lines');
  if (lines) {
    const total = $('input[name$="-TOTAL_FORMS"]', lines.parentElement);
    const template = $('#line-template');
    $('#add-line').addEventListener('click', () => {
      const index = parseInt(total.value, 10);
      const holder = document.createElement('div');
      holder.innerHTML = template.innerHTML.replace(/__prefix__/g, index).trim();
      const row = holder.firstElementChild;
      lines.appendChild(row);
      total.value = index + 1;
      const first = $('select, input:not([type=hidden])', row);
      if (first) first.focus();
    });
    lines.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-remove-line]');
      if (!btn) return;
      const row = btn.closest('.line-row');
      const del = $('input[name$="-DELETE"]', row);
      if (del) { del.checked = true; } else {
        $$('select, input[type=text], input[type=number]', row).forEach((f) => { f.value = ''; f.required = false; });
      }
      row.classList.add('deleted');
    });
    const updateSum = () => {
      $$('[data-total-for]').forEach((out) => {
        let sum = 0;
        $$(`.line-row:not(.deleted) input${out.dataset.totalFor}`, lines).forEach((i) => { sum += parseFloat(i.value) || 0; });
        out.textContent = money(sum);
        out.dataset.value = sum;
      });
      const diff = $('#sum-diff'), d = $('[data-total-for*="debit"]'), c = $('[data-total-for*="credit"]');
      if (diff && d && c) {
        const delta = (parseFloat(d.dataset.value) || 0) - (parseFloat(c.dataset.value) || 0);
        diff.textContent = money(Math.abs(delta));
        diff.parentElement.classList.toggle('bad-total', Math.abs(delta) > 0.004);
      }
    };
    lines.addEventListener('input', updateSum);
    lines.addEventListener('click', () => setTimeout(updateSum, 0));
    updateSum();
  }

  /* ---------- gráficos ---------- */
  if (!window.Chart) return;
  const palette = () => [css('--green-bright'), css('--navy-2'), css('--fuchsia-bright'), '#5fd0a5', '#4f7fb5', '#f08cc4', '#9ab6d3', '#e0a100'];
  const setup = () => {
    Chart.defaults.color = css('--muted');
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.borderColor = css('--line');
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
  };
  const tooltipMoney = (currency) => ({
    callbacks: {
      label: (ctx) => {
        const value = ctx.chart.options.indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y;
        return ` ${ctx.dataset.label ? ctx.dataset.label + ': ' : ''}${money(value)} ${currency}`;
      },
    },
  });
  const make = (canvasId, config) => { const el = document.getElementById(canvasId); if (el) return new Chart(el, config); };
  setup();

  const exec = data('chart-execution');
  if (exec) {
    const over = exec.spent.map((s, i) => exec.planned[i] === 0 || s > exec.planned[i]);
    make('c-execution', {
      type: 'bar',
      data: {
        labels: exec.labels,
        datasets: [
          { label: 'Planificado', data: exec.planned, backgroundColor: css('--navy-2'), borderRadius: 6 },
          { label: 'Gastado', data: exec.spent, backgroundColor: over.map((o) => (o ? css('--fuchsia-bright') : css('--green-bright'))), borderRadius: 6 },
        ],
      },
      options: { indexAxis: 'y', scales: { x: { beginAtZero: true, grid: { display: true } }, y: { grid: { display: false } } },
                 plugins: { tooltip: tooltipMoney(exec.currency) } },
    });
  }

  const monthly = data('chart-monthly');
  if (monthly) {
    make('c-monthly', {
      type: 'bar',
      data: { labels: monthly.labels, datasets: [{ label: 'Gasto', data: monthly.values, backgroundColor: css('--green-bright'), borderRadius: 6 }] },
      options: { scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
                 plugins: { legend: { display: false }, tooltip: tooltipMoney(monthly.currency) } },
    });
  }

  const portfolio = data('chart-portfolio');
  const select = $('#portfolio-currency');
  if (portfolio && Object.keys(portfolio).length && document.getElementById('c-portfolio')) {
    let chart;
    const draw = (currency) => {
      const d = portfolio[currency];
      if (chart) chart.destroy();
      chart = make('c-portfolio', {
        type: 'doughnut',
        data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: palette(), borderWidth: 2, borderColor: css('--surface') }] },
        options: { cutout: '62%', plugins: { legend: { position: 'bottom' },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${money(ctx.parsed)} ${currency}` } } } },
      });
    };
    const currencies = Object.keys(portfolio);
    if (select) {
      currencies.forEach((c) => select.add(new Option(c, c)));
      select.hidden = currencies.length < 2;
      select.addEventListener('change', () => draw(select.value));
    }
    draw(currencies[0]);
  }

  const timeline = data('chart-timeline');
  if (timeline) {
    make('c-timeline', {
      type: 'line',
      data: { labels: timeline.labels, datasets: [{ label: 'Saldo', data: timeline.values, borderColor: css('--green-bright'),
        backgroundColor: css('--green-soft'), fill: true, tension: .25, pointRadius: 4, pointBackgroundColor: css('--fuchsia-bright'), borderWidth: 2.5 }] },
      options: { scales: { y: { beginAtZero: false }, x: { grid: { display: false } } },
                 plugins: { legend: { display: false }, tooltip: tooltipMoney(timeline.currency) } },
    });
  }

  /* ---------- graficos genericos (data-chart) ---------- */
  const colorOf = (name) => ({ green: css('--green-bright'), navy: css('--navy-2'), fuchsia: css('--fuchsia-bright'),
    amber: '#e0a100', muted: css('--muted'), mint: '#5fd0a5', sky: '#4f7fb5', pink: '#f08cc4' }[name] || name);
  $$('canvas[data-chart]').forEach((canvas) => {
    const cfg = data(canvas.dataset.chart);
    if (!cfg) return;
    const pie = cfg.type === 'doughnut' || cfg.type === 'pie';
    const datasets = cfg.datasets.map((d) => {
      const out = Object.assign({}, d);
      const col = Array.isArray(d.color) ? d.color.map(colorOf) : colorOf(d.color);
      if (pie) { out.backgroundColor = col || palette(); out.borderColor = css('--surface'); out.borderWidth = 2; }
      else if (cfg.type === 'line') { out.borderColor = col; out.backgroundColor = col; out.tension = .25; }
      else { out.backgroundColor = col; out.borderRadius = 6; }
      return out;
    });
    const money2 = (v) => `${money(v)} ${cfg.currency || ''}`.trim();
    new Chart(canvas, {
      type: cfg.type,
      data: { labels: cfg.labels, datasets },
      options: pie
        ? { cutout: cfg.type === 'doughnut' ? '60%' : 0, plugins: { legend: { position: 'bottom' },
            tooltip: { callbacks: { label: (c) => ` ${c.label}: ${money2(c.parsed)}` } } } }
        : { indexAxis: cfg.horizontal ? 'y' : 'x',
            scales: { x: { stacked: cfg.stacked, grid: { display: false } }, y: { stacked: cfg.stacked, beginAtZero: true } },
            plugins: { legend: { display: datasets.length > 1 },
              tooltip: { callbacks: { label: (c) => ` ${c.dataset.label ? c.dataset.label + ': ' : ''}${money2(cfg.horizontal ? c.parsed.x : c.parsed.y)}` } } } },
    });
  });
})();
