document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('portfolio-form')
  const loader = document.getElementById('loader')
  const stocksContainer = document.getElementById('stocks-container')
  const totalValueEl = document.getElementById('total-value')
  const resultsPlaceholder = document.getElementById('results-placeholder')
  const resultsContent = document.getElementById('results-content')
  const notificationContainer = document.getElementById(
    'notification-container'
  )
  let historyChart = null
  let sectorChart = null
  let chatPortfolioContext = null
  let lastRequest = null // { amount, strategies, risk_profile, history_period }
  const chatMessages = []
  const CHAT_STORAGE_KEY = 'investiq-chat-v1'

  const PERIOD_LABELS = {
    '5d': '5-Day Trend',
    '1mo': '1-Month Trend',
    '3mo': '3-Month Trend',
    '1y': '1-Year Trend'
  }
  const SECTOR_COLORS = [
    '#6366f1',
    '#a855f7',
    '#22d3ee',
    '#f59e0b',
    '#10b981',
    '#ef4444',
    '#ec4899',
    '#84cc16',
    '#3b82f6',
    '#eab308'
  ]

  const chatPanel = document.getElementById('chat-panel')
  const chatToggle = document.getElementById('chat-toggle')
  const chatClose = document.getElementById('chat-close')
  const chatMessagesEl = document.getElementById('chat-messages')
  const chatForm = document.getElementById('chat-form')
  const chatInput = document.getElementById('chat-input')
  const chatSend = document.getElementById('chat-send')

  function setChatOpen (open) {
    if (!chatPanel || !chatToggle) return
    chatPanel.classList.toggle('is-open', open)
    chatPanel.setAttribute('aria-hidden', open ? 'false' : 'true')
    chatToggle.setAttribute('aria-expanded', open ? 'true' : 'false')
    if (open) setTimeout(() => chatInput?.focus(), 100)
  }

  function persistChat () {
    try {
      localStorage.setItem(
        CHAT_STORAGE_KEY,
        JSON.stringify(chatMessages.slice(-40))
      )
    } catch (_) {}
  }

  function loadChatFromStorage () {
    try {
      const raw = localStorage.getItem(CHAT_STORAGE_KEY)
      if (!raw) return
      const arr = JSON.parse(raw)
      if (!Array.isArray(arr)) return
      chatMessages.length = 0
      arr.forEach((m) => {
        if (m && m.role && typeof m.content === 'string') {
          chatMessages.push({
            role: m.role,
            content: m.content,
            warn: !!m.warn
          })
        }
      })
      renderChatMessages()
    } catch (_) {}
  }

  async function loadServerHints () {
    const el = document.getElementById('config-server-hint')
    const chatExtra = document.getElementById('chat-panel-hint-extra')
    try {
      const r = await fetch('/api/health')
      const h = await r.json()
      if (el) {
        const rat = h.llm_rationale_configured
          ? `Rationale LLM: on (${h.rationale_model || 'model'})`
          : 'Rationale LLM: off (built-in blurbs)'
        const ch = h.llm_chat_configured
          ? `Chat LLM: on (${h.chat_model || 'model'})`
          : 'Chat LLM: off'
        el.textContent = `${rat}. ${ch}. Prompts ${h.prompt_version}. Limits ~${h.rate_limits?.suggest_per_minute}/min suggest, ~${h.rate_limits?.chat_per_minute}/min chat. Quotes via Yahoo Finance (often USD for U.S. listings).`
      }
      if (chatExtra) {
        chatExtra.textContent = h.llm_chat_configured
          ? 'Streaming replies when your browser connects to /api/chat/stream.'
          : 'Set LLM_BACKEND in .env to enable chat; portfolio blurbs may still be built-in.'
      }
    } catch (_) {
      if (el) {
        el.textContent = 'Could not load /api/health (is the server running?)'
      }
    }
  }

  async function consumeChatStream (payload, onDelta) {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}))
      const d = errBody.detail
      const msg = Array.isArray(d)
        ? d.map((x) => x.msg || JSON.stringify(x)).join('; ')
        : d || response.statusText
      throw new Error(msg)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let acc = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n')
      buffer = parts.pop() || ''
      for (const line of parts) {
        if (!line.startsWith('data:')) continue
        const raw = line.replace(/^data:\s?/, '').trim()
        if (raw === '[DONE]') {
          return { text: acc, noLlm: false, streamError: false }
        }
        try {
          const j = JSON.parse(raw)
          if (j.error === 'no_llm') {
            return { text: '', noLlm: true, streamError: false }
          }
          if (j.error) {
            return {
              text: acc,
              noLlm: false,
              streamError: true,
              errMsg: j.message || String(j.error)
            }
          }
          if (j.t) {
            acc += j.t
            if (onDelta) onDelta(j.t, acc)
          }
        } catch (_) {
          /* ignore partial SSE frames */
        }
      }
    }
    return { text: acc, noLlm: false, streamError: false }
  }

  function renderChatMessages () {
    if (!chatMessagesEl) return
    chatMessagesEl.innerHTML = ''
    chatMessages.forEach((m) => {
      const div = document.createElement('div')
      const base =
        m.role === 'user'
          ? 'chat-bubble chat-bubble-user'
          : 'chat-bubble chat-bubble-assistant'
      const mdCls = m.role === 'assistant' ? ' chat-bubble-md' : ''
      div.className = (m.warn ? `${base} chat-bubble-warn` : base) + mdCls
      if (m.role === 'user') {
        div.innerHTML = escapeHtml(m.content).replace(/\n/g, '<br>')
      } else {
        div.innerHTML = formatAssistantMarkdown(m.content)
      }
      chatMessagesEl.appendChild(div)
    })
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight
    persistChat()
  }

  chatToggle?.addEventListener('click', () => {
    const open = !chatPanel?.classList.contains('is-open')
    setChatOpen(open)
  })
  chatClose?.addEventListener('click', () => setChatOpen(false))

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && chatPanel?.classList.contains('is-open')) {
      setChatOpen(false)
    }
  })

  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      chatForm?.requestSubmit()
    }
  })

  chatForm?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const text = (chatInput?.value || '').trim()
    if (!text || !chatSend) return

    chatInput.value = ''
    chatMessages.push({ role: 'user', content: text })
    renderChatMessages()
    chatSend.disabled = true

    const payload = {
      messages: chatMessages.slice(-24)
    }
    if (chatPortfolioContext) payload.portfolio_context = chatPortfolioContext

    const appendAssistant = (content, warn) => {
      chatMessages.push({ role: 'assistant', content, warn })
      renderChatMessages()
    }

    try {
      let usedStream = false
      try {
        const live = document.createElement('div')
        live.className = 'chat-bubble chat-bubble-assistant chat-bubble-md'
        live.textContent = ''
        chatMessagesEl?.appendChild(live)
        try {
          const streamResult = await consumeChatStream(payload, (_t, acc) => {
            // Plain text while streaming avoids half-rendered ** markers; final HTML uses Markdown.
            live.textContent = acc
            if (chatMessagesEl) {
              chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight
            }
          })

          if (streamResult.noLlm) {
            usedStream = false
          } else if (streamResult.streamError) {
            appendAssistant(
              streamResult.text ||
                streamResult.errMsg ||
                'Stream ended with an error.',
              true
            )
            usedStream = true
          } else {
            appendAssistant(streamResult.text || '(Empty stream.)', false)
            usedStream = true
          }
        } finally {
          live.remove()
        }
      } catch {
        usedStream = false
      }

      if (!usedStream) {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })

        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          const d = data.detail
          const msg = Array.isArray(d)
            ? d.map((x) => x.msg || JSON.stringify(x)).join('; ')
            : d || response.statusText || 'Chat request failed'
          throw new Error(msg)
        }

        appendAssistant(data.reply || '(No reply)', data.ok === false)

        if (data.llm_available === false) {
          showNotification(
            'Chat needs a configured LLM — see terminal or .env.example.',
            'error'
          )
        }
      }
    } catch (err) {
      appendAssistant(String(err.message || err), true)
      showNotification(err.message || 'Chat failed', 'error')
    } finally {
      chatSend.disabled = false
    }
  })

  function escapeHtml (text) {
    if (text == null) return ''
    const div = document.createElement('div')
    div.textContent = String(text)
    return div.innerHTML
  }

  /** Assistant replies often use Markdown (**bold**, lists); sanitize before innerHTML. */
  function formatAssistantMarkdown (text) {
    if (text == null || text === '') return ''
    const s = String(text)
    try {
      if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
        const html = marked.parse(s)
        return DOMPurify.sanitize(html)
      }
    } catch (_) {}
    return escapeHtml(s).replace(/\n/g, '<br>')
  }

  function formatRationaleBanner (data) {
    if (
      data.rationale_origin === undefined &&
      (data.stocks?.length ?? 0) > 0 &&
      !data.stocks.some((s) => s.rationale_source !== undefined)
    ) {
      return 'Saved history — explanation source was not recorded for this run.'
    }

    const origin = data.rationale_origin || 'fallback'
    const be = data.rationale_llm_backend
    const model = data.rationale_llm_model
    const cfg =
      be && model ? `${be} · ${model}` : model || (be ? String(be) : '')

    if (origin === 'all_llm') {
      return cfg
        ? `Explanations generated by your LLM (${cfg}).`
        : 'Explanations generated by your LLM.'
    }
    if (origin === 'partial_llm') {
      return cfg
        ? `Mixed: some picks use your LLM (${cfg}); others use built-in text — see tags on each row.`
        : 'Mixed LLM and built-in explanations — see tags on each row.'
    }
    if (cfg) {
      return `Built-in explanations only. LLM was configured (${cfg}) but did not return usable text — is the model running?`
    }
    return 'Built-in explanations (LLM disabled or not configured).'
  }

  function showNotification (message, type = 'success') {
    const toast = document.createElement('div')
    toast.className = `toast ${type}`
    toast.innerHTML = `
            <span>${type === 'success' ? '✅' : '❌'}</span>
            <span>${message}</span>
        `
    notificationContainer.appendChild(toast)

    setTimeout(() => {
      toast.style.animation =
        'slideOut 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards'
      setTimeout(() => toast.remove(), 400)
    }, 4000)
  }

  function getActivePeriod () {
    const active = document.querySelector('.period-btn.is-active')
    return active?.dataset.period || '5d'
  }

  function setActivePeriod (period) {
    document.querySelectorAll('.period-btn').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.period === period)
    })
  }

  async function requestSuggestion (payload) {
    loader.style.display = 'flex'
    try {
      const response = await fetch('/api/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        const d = error.detail
        const msg = Array.isArray(d)
          ? d.map((x) => x.msg || JSON.stringify(x)).join('; ')
          : d || 'Failed to fetch suggestions'
        throw new Error(msg)
      }

      const data = await response.json()
      lastRequest = payload
      renderResults(data)
      resultsPlaceholder.style.display = 'none'
      resultsContent.style.display = 'flex'
      loadHistory()
    } catch (error) {
      showNotification(error.message, 'error')
    } finally {
      loader.style.display = 'none'
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault()

    const amount = parseFloat(document.getElementById('amount').value)
    const selectedCheckboxes = document.querySelectorAll(
      'input[name="strategies"]:checked'
    )

    if (selectedCheckboxes.length === 0 || selectedCheckboxes.length > 2) {
      showNotification('Please select 1 or 2 investment strategies.', 'error')
      return
    }

    const strategies = Array.from(selectedCheckboxes).map((cb) => cb.value)
    const riskRadio = document.querySelector(
      'input[name="risk_profile"]:checked'
    )
    const risk_profile = riskRadio?.value || 'Moderate'
    const history_period = getActivePeriod()

    await requestSuggestion({
      amount,
      strategies,
      risk_profile,
      history_period
    })
  })

  document.querySelectorAll('.period-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const period = btn.dataset.period
      if (!period || btn.classList.contains('is-active')) return
      setActivePeriod(period)
      if (!lastRequest) return // nothing generated yet
      await requestSuggestion({ ...lastRequest, history_period: period })
    })
  })

  function formatPct (v) {
    if (v == null || Number.isNaN(v)) return ''
    const sign = v > 0 ? '+' : ''
    return `${sign}${Number(v).toFixed(2)}%`
  }

  function renderResults (data) {
    // Update Total Value
    totalValueEl.textContent = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(data.total_value)

    const returnEl = document.getElementById('portfolio-return')
    if (returnEl) {
      const r = data.period_return_pct
      if (r == null || Number.isNaN(r)) {
        returnEl.textContent = ''
        returnEl.className = 'portfolio-return'
      } else {
        const cls = r >= 0 ? 'is-up' : 'is-down'
        const periodLabel =
          PERIOD_LABELS[data.history_period] || PERIOD_LABELS['5d']
        returnEl.className = `portfolio-return ${cls}`
        returnEl.textContent = `${formatPct(r)} · ${periodLabel}`
      }
    }

    if (data.history_period) setActivePeriod(data.history_period)

    const bannerEl = document.getElementById('rationale-origin-banner')
    if (bannerEl) {
      bannerEl.textContent = formatRationaleBanner(data)
      bannerEl.style.display = 'block'
    }

    const warnEl = document.getElementById('portfolio-warnings')
    if (warnEl) {
      const warns = data.warnings || []
      if (warns.length) {
        warnEl.style.display = 'block'
        warnEl.innerHTML = warns.map((w) => `<p>${escapeHtml(w)}</p>`).join('')
      } else {
        warnEl.style.display = 'none'
        warnEl.innerHTML = ''
      }
    }

    chatPortfolioContext = {
      total_value: data.total_value,
      stocks: (data.stocks || []).map((s) => ({
        symbol: s.symbol,
        name: s.name,
        allocation_amount: s.allocation_amount,
        selection_rationale: s.selection_rationale,
        sector: s.sector,
        period_return_pct: s.period_return_pct
      })),
      rationale_origin: data.rationale_origin,
      risk_profile: data.risk_profile,
      history_period: data.history_period,
      period_return_pct: data.period_return_pct,
      sector_allocations: (data.sector_allocations || []).map((s) => ({
        sector: s.sector,
        pct: s.pct
      }))
    }

    // Update Stock List
    stocksContainer.innerHTML = ''
    data.stocks.forEach((stock) => {
      const item = document.createElement('div')
      item.className = 'stock-item'
      const rationale = stock.selection_rationale
      const src = stock.rationale_source
      const pill =
        src === undefined
          ? ''
          : src === 'llm'
            ? '<span class="rationale-pill rationale-pill-llm">LLM</span>'
            : '<span class="rationale-pill rationale-pill-fallback">Built-in</span>'
      const rationaleBlock =
        rationale && String(rationale).trim()
          ? `<p class="stock-rationale"><span class="stock-rationale-heading"><span class="stock-rationale-label">Why this pick</span>${pill}</span> ${escapeHtml(rationale)}</p>`
          : ''
      const sym = escapeHtml(stock.symbol)
      const fallbackLogo = `https://ui-avatars.com/api/?name=${encodeURIComponent(stock.symbol)}`
      const logoSrc = escapeHtml(stock.logo_url || fallbackLogo)
      const sectorBadge = stock.sector
        ? `<span class="stock-sector-badge" title="Sector">${escapeHtml(stock.sector)}</span>`
        : ''
      const r = stock.period_return_pct
      let returnBlock = ''
      if (r != null && !Number.isNaN(r)) {
        const cls = r >= 0 ? 'is-up' : 'is-down'
        returnBlock = `<div class="stock-return ${cls}">${formatPct(r)}</div>`
      }
      item.innerHTML = `
                <div class="stock-main">
                    <div class="stock-info">
                        <img src="${logoSrc}"
                             alt="${sym}"
                             class="stock-logo"
                             onerror="this.src='${fallbackLogo}'">
                        <div>
                            <h4>${sym} ${sectorBadge}</h4>
                            <p>${escapeHtml(stock.name)}</p>
                        </div>
                    </div>
                    ${rationaleBlock}
                </div>
                <div class="stock-stats">
                    <div class="stock-price">${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(stock.price)}</div>
                    ${returnBlock}
                    <div class="stock-shares">${stock.shares.toFixed(4)} shares</div>
                    <div class="stock-allocation">Allocated: ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(stock.allocation_amount)}</div>
                </div>
            `
      stocksContainer.appendChild(item)
    })

    // Update Charts
    renderChart(data.weekly_history, data.history_period)
    renderSectorChart(data.sector_allocations || [])

    // Show Results
    resultsPlaceholder.style.display = 'none'
    resultsContent.style.display = 'block'
  }

  function renderChart (history, period) {
    const ctx = document.getElementById('historyChart').getContext('2d')

    if (historyChart) {
      historyChart.destroy()
    }

    const labels = history.map((h) => h.date)
    const values = history.map((h) => h.value)
    const periodLabel = PERIOD_LABELS[period] || PERIOD_LABELS['5d']
    // Long ranges crowd the x-axis; let Chart.js auto-thin tick labels.
    const ptRadius = values.length > 30 ? 0 : 4

    historyChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: `Portfolio Value (${periodLabel})`,
            data: values,
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#6366f1',
            pointRadius: ptRadius
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (item) =>
                new Intl.NumberFormat('en-US', {
                  style: 'currency',
                  currency: 'USD'
                }).format(item.parsed.y)
            }
          }
        },
        scales: {
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              callback: function (value) {
                return '$' + value.toLocaleString()
              }
            }
          },
          x: {
            grid: { display: false },
            ticks: {
              color: '#94a3b8',
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8
            }
          }
        }
      }
    })
  }

  function renderSectorChart (sectors) {
    const canvas = document.getElementById('sectorChart')
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (sectorChart) {
      sectorChart.destroy()
      sectorChart = null
    }
    if (!sectors || sectors.length === 0) return

    const labels = sectors.map((s) => s.sector)
    const data = sectors.map((s) => Number(s.pct))
    const colors = sectors.map(
      (_, i) => SECTOR_COLORS[i % SECTOR_COLORS.length]
    )

    sectorChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [
          {
            data,
            backgroundColor: colors,
            borderColor: 'rgba(15, 23, 42, 0.85)',
            borderWidth: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: '#cbd5e1',
              boxWidth: 10,
              font: { size: 10 }
            }
          },
          tooltip: {
            callbacks: {
              label: (item) => `${item.label}: ${item.parsed.toFixed(2)}%`
            }
          }
        }
      }
    })
  }

  loadChatFromStorage()
  loadServerHints()

  // Initial history load
  loadHistory()

  async function loadHistory () {
    const historyContainer = document.getElementById('history-container')
    try {
      const response = await fetch('/api/history')
      const history = await response.json()

      if (history.length === 0) {
        historyContainer.innerHTML =
          '<p class="hint">No recent history available.</p>'
        return
      }

      historyContainer.innerHTML = ''
      history.forEach((item) => {
        const date = new Date(item.timestamp)
        const el = document.createElement('div')
        el.className = 'history-item'
        el.innerHTML = `
                    <span class="history-date">${date.toLocaleString()}</span>
                    <div class="history-summary">${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(item.data.total_value)}</div>
                `
        el.onclick = () => {
          const d = item.data || {}
          renderResults(d)
          // Let the period toggle replay this saved run if all params survived.
          if (
            d.amount_requested != null &&
            Array.isArray(d.selected_strategies) &&
            d.selected_strategies.length
          ) {
            lastRequest = {
              amount: d.amount_requested,
              strategies: d.selected_strategies,
              risk_profile: d.risk_profile || 'Moderate',
              history_period: d.history_period || '5d'
            }
          }
        }
        historyContainer.appendChild(el)
      })
    } catch (error) {
      console.error('Failed to load history:', error)
    }
  }
})
