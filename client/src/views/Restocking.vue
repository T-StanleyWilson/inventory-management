<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-slider">
          <input
            type="range"
            min="0"
            max="50000"
            step="500"
            v-model.number="budget"
            class="budget-range"
          />
          <div class="budget-readout">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ totalCost.toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.budgetRemaining') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ budgetRemaining.toLocaleString() }}</div>
        </div>
      </div>

      <div v-if="orderSuccess" class="success-panel">
        {{ t('restocking.orderSuccess', {
          orderNumber: orderSuccess.order_number,
          leadTime: t('restocking.leadTimeDays', { days: orderSuccess.lead_time_days }),
          expectedDelivery: formatDate(orderSuccess.expected_delivery)
        }) }}
      </div>

      <div v-if="submitError" class="error">{{ submitError }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ recommendations.length }})</h3>
          <button
            class="place-order-btn"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
          </button>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.currentDemand') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.demandGap') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in recommendations" :key="rec.sku">
                <td><strong>{{ rec.sku }}</strong></td>
                <td>{{ rec.name }}</td>
                <td>{{ rec.current_demand }}</td>
                <td>{{ rec.forecasted_demand }}</td>
                <td>{{ rec.gap }}</td>
                <td><strong>{{ rec.quantity }}</strong></td>
                <td>{{ currencySymbol }}{{ rec.unit_cost.toLocaleString() }}</td>
                <td>{{ currencySymbol }}{{ rec.line_total.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])

    const budget = ref(10000)
    const submitting = ref(false)
    const submitError = ref(null)
    const orderSuccess = ref(null)

    const loadForecasts = async () => {
      try {
        loading.value = true
        forecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Greedy, budget-constrained restock recommendations:
    // items with the biggest demand shortfall are prioritized, but smaller/cheaper
    // items further down the list still get a chance to fit into whatever budget
    // remains rather than stopping as soon as one item doesn't fit.
    const recommendations = computed(() => {
      const withGaps = forecasts.value.map(f => {
        const gap = f.forecasted_demand - f.current_demand
        // When demand isn't growing, still restock a sensible minimum reorder
        // quantity (10) rather than recommending zero units.
        const quantity = gap > 0 ? gap : 10
        const lineTotal = Math.round(quantity * f.unit_cost * 100) / 100
        return {
          sku: f.item_sku,
          name: f.item_name,
          current_demand: f.current_demand,
          forecasted_demand: f.forecasted_demand,
          gap,
          quantity,
          unit_cost: f.unit_cost,
          line_total: lineTotal
        }
      })

      withGaps.sort((a, b) => b.gap - a.gap)

      const result = []
      let runningTotal = 0

      for (const item of withGaps) {
        // Skip-and-continue: an item that doesn't fit right now shouldn't block
        // cheaper items later in the list from being included.
        if (runningTotal + item.line_total <= budget.value) {
          result.push(item)
          runningTotal += item.line_total
        }
      }

      return result
    })

    const totalCost = computed(() => {
      return Math.round(recommendations.value.reduce((sum, r) => sum + r.line_total, 0) * 100) / 100
    })

    const budgetRemaining = computed(() => {
      const remaining = budget.value - totalCost.value
      return remaining > 0 ? remaining : 0
    })

    const formatDate = (dateString) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return new Date(dateString).toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    const placeOrder = async () => {
      submitError.value = null
      orderSuccess.value = null
      submitting.value = true
      try {
        const payload = {
          budget: budget.value,
          items: recommendations.value.map(r => ({
            sku: r.sku,
            name: r.name,
            quantity: r.quantity,
            unit_cost: r.unit_cost,
            line_total: r.line_total
          }))
        }
        orderSuccess.value = await api.createRestockOrder(payload)
      } catch (err) {
        submitError.value = t('restocking.orderError')
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      recommendations,
      totalCost,
      budgetRemaining,
      currencySymbol,
      submitting,
      submitError,
      orderSuccess,
      placeOrder,
      formatDate
    }
  }
}
</script>

<style scoped>
.budget-slider {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.budget-range {
  flex: 1;
  accent-color: #2563eb;
}

.budget-readout {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 100px;
  text-align: right;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.place-order-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.success-panel {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
}
</style>
