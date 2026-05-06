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

    // Show loader
    loader.style.display = 'flex'

    try {
      const response = await fetch('/api/suggest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ amount, strategies })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to fetch suggestions')
      }

      const data = await response.json()
      renderResults(data)
      resultsPlaceholder.style.display = 'none'
      resultsContent.style.display = 'flex'
      loadHistory()
    } catch (error) {
      showNotification(error.message, 'error')
    } finally {
      loader.style.display = 'none'
    }
  })

  function renderResults (data) {
    // Update Total Value
    totalValueEl.textContent = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(data.total_value)

    // Update Stock List
    stocksContainer.innerHTML = ''
    data.stocks.forEach((stock) => {
      const item = document.createElement('div')
      item.className = 'stock-item'
      item.innerHTML = `
                <div class="stock-info">
                    <img src="${stock.logo_url || 'https://ui-avatars.com/api/?name=' + stock.symbol}" 
                         alt="${stock.symbol}" 
                         class="stock-logo"
                         onerror="this.src='https://ui-avatars.com/api/?name=${stock.symbol}'">
                    <div>
                        <h4>${stock.symbol}</h4>
                        <p>${stock.name}</p>
                    </div>
                </div>
                <div class="stock-stats">
                    <div class="stock-price">${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(stock.price)}</div>
                    <div class="stock-shares">${stock.shares.toFixed(4)} shares</div>
                    <div class="stock-allocation">Allocated: ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(stock.allocation_amount)}</div>
                </div>
            `
      stocksContainer.appendChild(item)
    })

    // Update Chart
    renderChart(data.weekly_history)

    // Show Results
    resultsPlaceholder.style.display = 'none'
    resultsContent.style.display = 'block'
  }

  function renderChart (history) {
    const ctx = document.getElementById('historyChart').getContext('2d')

    if (historyChart) {
      historyChart.destroy()
    }

    const labels = history.map((h) => h.date)
    const values = history.map((h) => h.value)

    historyChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Portfolio Value (5-Day Trend)',
            data: values,
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#6366f1',
            pointRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.05)'
            },
            ticks: {
              color: '#94a3b8',
              callback: function (value) {
                return '$' + value.toLocaleString()
              }
            }
          },
          x: {
            grid: {
              display: false
            },
            ticks: {
              color: '#94a3b8'
            }
          }
        }
      }
    })
  }

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
        el.onclick = () => renderResults(item.data)
        historyContainer.appendChild(el)
      })
    } catch (error) {
      console.error('Failed to load history:', error)
    }
  }
})
