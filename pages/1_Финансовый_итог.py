import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Финансовый итог", layout="wide")

# -----------------------------------------------------------------------------
# 1. Загрузка данных с прямыми путями
# -----------------------------------------------------------------------------

@st.cache_data
def load_transactions():
    trans = pd.read_csv('data/transactions.csv')
    fx = pd.read_csv('data/fx_rates.csv')

    trans['created_at'] = pd.to_datetime(trans['created_at'])
    trans['month'] = trans['created_at'].dt.to_period('M').dt.to_timestamp()
    fx['date'] = pd.to_datetime(fx['date'])

    # Создаем словарь курсов для каждой валюты (дата -> курс)
    fx_dict = {}
    for curr in trans['currency'].unique():
        curr_fx = fx[fx['currency'] == curr].sort_values('date')
        if not curr_fx.empty:
            fx_dict[curr] = curr_fx.set_index('date')['usd_rate'].to_dict()

    def get_rate(currency, date):
        if currency not in fx_dict:
            return 1.0
        rates = fx_dict[currency]
        dates = sorted(rates.keys())
        if date < dates[0]:
            return rates[dates[0]]
        for d in reversed(dates):
            if d <= date:
                return rates[d]
        return rates[dates[0]]

    trans['usd_rate'] = trans.apply(
        lambda row: get_rate(row['currency'], row['created_at']),
        axis=1
    )

    trans['amount_usd'] = trans['amount'] * trans['usd_rate']
    trans['client_fee_usd'] = trans['client_fee'] * trans['usd_rate']
    trans['direct_cost_usd'] = trans['direct_cost'] * trans['usd_rate']

    return trans


@st.cache_data
def aggregate_by_month(trans):
    completed = trans[trans['status'] == 'completed']
    agg = completed.groupby('month').agg(
        gmv=('amount_usd', 'sum'),
        revenue=('client_fee_usd', 'sum'),
        cost=('direct_cost_usd', 'sum'),
        tx_count=('transaction_id', 'count'),
        active_clients=('client_id', 'nunique')
    ).reset_index()

    # Конверсия
    status_counts = trans.groupby(['month', 'status']).size().unstack(fill_value=0)
    for sts in ['completed', 'failed', 'refunded', 'pending']:
        if sts not in status_counts.columns:
            status_counts[sts] = 0
    status_counts['total'] = status_counts['completed'] + status_counts['failed'] + status_counts['refunded']
    status_counts['conversion'] = status_counts['completed'] / status_counts['total'].replace(0, 1)

    agg = agg.merge(status_counts[['conversion']], left_on='month', right_index=True, how='left')

    agg['margin'] = (agg['revenue'] - agg['cost']) / agg['revenue'] * 100
    agg['avg_ticket'] = agg['gmv'] / agg['tx_count']
    agg['avg_fee'] = agg['revenue'] / agg['tx_count']
    agg['fee_rate'] = agg['revenue'] / agg['gmv'] * 100

    return agg.sort_values('month')


# -----------------------------------------------------------------------------
# 2. Загрузка
# -----------------------------------------------------------------------------

trans = load_transactions()
agg = aggregate_by_month(trans)

if agg.empty:
    st.warning("Нет завершённых транзакций.")
    st.stop()

min_date = agg['month'].min()
max_date = agg['month'].max()

# -----------------------------------------------------------------------------
# 3. Фильтры в сайдбаре
# -----------------------------------------------------------------------------

st.sidebar.title("Финансовый итог")
st.sidebar.markdown("---")

metric_options = {
    'gmv': 'GMV (объём, USD)',
    'revenue': 'Выручка от комиссий, USD',
    'margin': 'Маржинальность, %',
    'tx_count': 'Количество транзакций',
    'active_clients': 'Активные клиенты',
    'conversion': 'Конверсия платежей, %',
    'avg_ticket': 'Средний чек, USD',
    'avg_fee': 'Средняя комиссия, USD',
    'fee_rate': 'Средняя ставка комиссии, %'
}

selected_metric = st.sidebar.selectbox(
    "Выберите метрику для графика",
    options=list(metric_options.keys()),
    format_func=lambda x: metric_options[x]
)

date_range = st.sidebar.slider(
    "Выберите период",
    min_value=min_date.to_pydatetime(),
    max_value=max_date.to_pydatetime(),
    value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
    format="YYYY-MM"
)

agg_filtered = agg[
    (agg['month'] >= pd.to_datetime(date_range[0])) &
    (agg['month'] <= pd.to_datetime(date_range[1]))
]

if agg_filtered.empty:
    st.warning("Нет данных за выбранный период.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.caption(f"Данных: {len(agg_filtered)} месяцев")
st.sidebar.caption(f"Период: {date_range[0].strftime('%Y-%m')} — {date_range[1].strftime('%Y-%m')}")

# -----------------------------------------------------------------------------
# 4. Основная панель
# -----------------------------------------------------------------------------

st.title("📊 Финансовое здоровье бизнеса (Executive Dashboard)")

last = agg_filtered.iloc[-1]
prev = agg_filtered.iloc[-2] if len(agg_filtered) > 1 else last

def delta(current, previous):
    if previous == 0 or pd.isna(previous):
        return 0.0
    return (current - previous) / abs(previous)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    d = delta(last['gmv'], prev['gmv'])
    st.metric("GMV", f"${last['gmv']:,.0f}", f"{d:+.1%} к предыдущему")
with col2:
    d = delta(last['revenue'], prev['revenue'])
    st.metric("Выручка", f"${last['revenue']:,.0f}", f"{d:+.1%} к предыдущему")
with col3:
    d = delta(last['margin'], prev['margin'])
    st.metric("Маржинальность", f"{last['margin']:.1f}%", f"{d:+.1%} к предыдущему")
with col4:
    d = delta(last['conversion'], prev['conversion'])
    st.metric("Конверсия", f"{last['conversion']:.1%}", f"{d:+.1%} к предыдущему")
with col5:
    d = delta(last['tx_count'], prev['tx_count'])
    st.metric("Транзакции", f"{last['tx_count']:,.0f}", f"{d:+.1%} к предыдущему")

st.markdown("---")

st.subheader(f"📈 Динамика: {metric_options[selected_metric]}")
fig = px.line(
    agg_filtered,
    x='month',
    y=selected_metric,
    title=f"{metric_options[selected_metric]} по месяцам",
    markers=True,
    labels={'month': 'Месяц', selected_metric: metric_options[selected_metric]}
)
fig.update_layout(height=400, hovermode='x unified', template='plotly_white')
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

st.subheader("🔎 Детализация по месяцам")
months = agg_filtered['month'].dt.strftime('%Y-%m').tolist()
default_idx = len(months) - 1
selected_month_str = st.selectbox("Выберите месяц", options=months, index=default_idx)
selected_month = pd.to_datetime(selected_month_str)
row = agg_filtered[agg_filtered['month'] == selected_month].iloc[0]

col_det1, col_det2 = st.columns(2)
with col_det1:
    st.write("**Основные показатели**")
    detail_data = {
        "Показатель": ["GMV", "Выручка", "Маржинальность", "Конверсия", "Средний чек", "Средняя комиссия"],
        "Значение": [
            f"${row['gmv']:,.0f}",
            f"${row['revenue']:,.0f}",
            f"{row['margin']:.1f}%",
            f"{row['conversion']:.1%}",
            f"${row['avg_ticket']:,.2f}",
            f"${row['avg_fee']:,.2f}"
        ]
    }
    st.dataframe(pd.DataFrame(detail_data), hide_index=True, use_container_width=True)

with col_det2:
    st.write("**Дополнительные метрики**")
    detail_data2 = {
        "Показатель": ["Кол-во транзакций", "Активные клиенты", "Средняя ставка комиссии", "Затраты", "Прибыль"],
        "Значение": [
            f"{row['tx_count']:,.0f}",
            f"{row['active_clients']:,.0f}",
            f"{row['fee_rate']:.2f}%",
            f"${row['cost']:,.2f}",
            f"${row['revenue'] - row['cost']:,.2f}"
        ]
    }
    st.dataframe(pd.DataFrame(detail_data2), hide_index=True, use_container_width=True)

st.markdown("---")

st.subheader("📊 Дополнительные графики")
col_extra1, col_extra2 = st.columns(2)
with col_extra1:
    fig2 = px.line(
        agg_filtered,
        x='month',
        y=['gmv', 'revenue'],
        title='GMV и Выручка',
        labels={'value': 'USD', 'month': 'Месяц', 'variable': 'Показатель'}
    )
    st.plotly_chart(fig2, use_container_width=True)

with col_extra2:
    fig3 = px.bar(
        agg_filtered,
        x='month',
        y='margin',
        title='Маржинальность по месяцам',
        labels={'margin': 'Маржинальность, %', 'month': 'Месяц'}
    )
    st.plotly_chart(fig3, use_container_width=True)

st.caption("📊 Данные: транзакции CrossPay, конвертация в USD по курсам на дату платежа")