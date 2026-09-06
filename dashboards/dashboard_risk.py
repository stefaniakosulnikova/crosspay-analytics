import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

st.set_page_config(page_title="Операционные риски", layout="wide")

@st.cache_data
def load_transactions():
    trans = pd.read_csv('data/transactions.csv')
    fx = pd.read_csv('data/fx_rates.csv')
    
    trans['created_at'] = pd.to_datetime(trans['created_at'])
    if 'completed_at' in trans.columns:
        trans['completed_at'] = pd.to_datetime(trans['completed_at'], errors='coerce')
    trans['month'] = trans['created_at'].dt.to_period('M').dt.to_timestamp()
    fx['date'] = pd.to_datetime(fx['date'])
    
    # Конвертация в USD (для сумм в аномалиях)
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
    
    return trans

@st.cache_data
def load_clients():
    return pd.read_csv('data/clients.csv')

trans = load_transactions()
clients = load_clients()

# -----------------------------------------------------------------------------
# 2. Предобработка
# -----------------------------------------------------------------------------

# Добавляем страну клиента к транзакциям
trans = trans.merge(clients[['client_id', 'country']], on='client_id', how='left')
trans['country'] = trans['country'].fillna('Unknown')

# Время обработки для completed
trans['processing_hours'] = (trans['completed_at'] - trans['created_at']).dt.total_seconds() / 3600

# Статусы: выделим failed, refunded, completed, pending
status_colors = {
    'completed': '#2ECC71',
    'failed': '#E74C3C',
    'refunded': '#F39C12',
    'pending': '#3498DB'
}


# 3. Фильтры
# 

st.sidebar.title("Операционные риски")
st.sidebar.markdown("---")

min_date = trans['created_at'].min()
max_date = trans['created_at'].max()

date_range = st.sidebar.slider(
    "Период транзакций",
    min_value=min_date.to_pydatetime(),
    max_value=max_date.to_pydatetime(),
    value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
    format="YYYY-MM-DD"
)

countries = ['Все'] + sorted(trans['country'].dropna().unique().tolist())
selected_country = st.sidebar.selectbox("Страна клиента", countries)

statuses = ['Все'] + ['completed', 'failed', 'refunded', 'pending']
selected_status = st.sidebar.selectbox("Статус транзакции", statuses)

# Применяем фильтры
df_filtered = trans[
    (trans['created_at'] >= pd.to_datetime(date_range[0])) &
    (trans['created_at'] <= pd.to_datetime(date_range[1]))
]

if selected_country != 'Все':
    df_filtered = df_filtered[df_filtered['country'] == selected_country]

if selected_status != 'Все':
    df_filtered = df_filtered[df_filtered['status'] == selected_status]

st.sidebar.markdown("---")
st.sidebar.caption(f"Транзакций: {len(df_filtered):,}")

# -----------------------------------------------------------------------------
# 4. Основная панель
# -----------------------------------------------------------------------------

st.title("⚠️ Операционные риски (Operational Risk Dashboard)")

# KPI
total = len(df_filtered)
completed = df_filtered[df_filtered['status'] == 'completed'].shape[0]
failed = df_filtered[df_filtered['status'] == 'failed'].shape[0]
refunded = df_filtered[df_filtered['status'] == 'refunded'].shape[0]
pending = df_filtered[df_filtered['status'] == 'pending'].shape[0]

conversion = completed / (completed + failed + refunded) if (completed + failed + refunded) > 0 else 0
failure_rate = failed / (completed + failed + refunded) if (completed + failed + refunded) > 0 else 0

# Среднее время обработки (только completed)
completed_df = df_filtered[df_filtered['status'] == 'completed']
avg_processing = completed_df['processing_hours'].mean() if not completed_df.empty else 0

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Всего транзакций", f"{total:,}")
with col2:
    st.metric("Конверсия", f"{conversion:.1%}", f"{failure_rate:.1%} отказов")
with col3:
    st.metric("Отказы (failed)", f"{failed:,}", f"{failed/total:.1%}" if total > 0 else "0%")
with col4:
    st.metric("Возвраты (refunded)", f"{refunded:,}", f"{refunded/total:.1%}" if total > 0 else "0%")
with col5:
    st.metric("Ср. время обработки", f"{avg_processing:.1f} ч")

st.markdown("---")

# Графики в две колонки
col_left, col_right = st.columns(2)

with col_left:
    # 1. Динамика статусов по месяцам
    status_by_month = df_filtered.groupby(['month', 'status']).size().reset_index(name='count')
    fig1 = px.bar(
        status_by_month,
        x='month',
        y='count',
        color='status',
        title='Динамика статусов транзакций по месяцам',
        labels={'month': 'Месяц', 'count': 'Количество', 'status': 'Статус'},
        color_discrete_map=status_colors,
        barmode='group'
    )
    st.plotly_chart(fig1, use_container_width=True)

    # 2. Отказы по странам (только failed)
    failed_by_country = df_filtered[df_filtered['status'] == 'failed'].groupby('country').size().reset_index(name='count')
    if not failed_by_country.empty:
        fig2 = px.bar(
            failed_by_country.sort_values('count', ascending=False).head(10),
            x='country',
            y='count',
            title='Топ-10 стран по количеству отказов',
            labels={'country': 'Страна', 'count': 'Количество отказов'},
            color='count',
            color_continuous_scale='Reds'
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Нет данных об отказах за выбранный период")

with col_right:
    # 3. Распределение по причинам отказа
    failed_df = df_filtered[df_filtered['status'] == 'failed']
    if not failed_df.empty:
        reason_counts = failed_df['failure_reason'].value_counts().reset_index()
        reason_counts.columns = ['reason', 'count']
        # Убираем пустые причины
        reason_counts = reason_counts[reason_counts['reason'].notna()]
        if not reason_counts.empty:
            fig3 = px.pie(
                reason_counts,
                names='reason',
                values='count',
                title='Распределение отказов по причинам',
                hole=0.4
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Нет информации о причинах отказов")
    else:
        st.info("Нет отказов за выбранный период")

    # 4. Динамика отказов по месяцам
    failed_by_month = df_filtered[df_filtered['status'] == 'failed'].groupby('month').size().reset_index(name='count')
    if not failed_by_month.empty:
        fig4 = px.line(
            failed_by_month,
            x='month',
            y='count',
            markers=True,
            title='Динамика количества отказов по месяцам',
            labels={'month': 'Месяц', 'count': 'Количество отказов'}
        )
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("Нет отказов за выбранный период")

st.markdown("---")


st.subheader("🚨 Таблица аномалий")

# Типы аномалий
anomaly_types = [
    "Отрицательная сумма (amount < 0)",
    "Незавершённые > 7 дней (pending)",
    "Очень долгая обработка (> 72 ч)",
    "Некорректная валюта"
]

selected_anomaly = st.selectbox("Выберите тип аномалии", anomaly_types)

# Формируем таблицу аномалий
anomalies = pd.DataFrame()

if selected_anomaly == "Отрицательная сумма (amount < 0)":
    anomalies = df_filtered[df_filtered['amount'] < 0].copy()
    anomalies = anomalies[['transaction_id', 'client_id', 'created_at', 'amount', 'currency', 'status', 'failure_reason']]
    st.warning(f"Найдено {len(anomalies)} транзакций с отрицательной суммой")
    
elif selected_anomaly == "Незавершённые > 7 дней (pending)":
    pending_df = df_filtered[df_filtered['status'] == 'pending'].copy()
    if not pending_df.empty:
        now = pd.Timestamp.now()
        pending_df['days_pending'] = (now - pending_df['created_at']).dt.days
        anomalies = pending_df[pending_df['days_pending'] > 7].copy()
        anomalies = anomalies[['transaction_id', 'client_id', 'created_at', 'days_pending', 'amount', 'currency']]
        st.warning(f"Найдено {len(anomalies)} транзакций в статусе pending более 7 дней")
    else:
        st.info("Нет незавершённых транзакций")
        
elif selected_anomaly == "Очень долгая обработка (> 72 ч)":
    completed_df = df_filtered[df_filtered['status'] == 'completed'].copy()
    if not completed_df.empty:
        anomalies = completed_df[completed_df['processing_hours'] > 72].copy()
        anomalies = anomalies[['transaction_id', 'client_id', 'created_at', 'completed_at', 'processing_hours', 'amount', 'currency']]
        anomalies['processing_hours'] = anomalies['processing_hours'].round(1)
        st.warning(f"Найдено {len(anomalies)} транзакций с обработкой > 72 часов")
    else:
        st.info("Нет завершённых транзакций")
        
elif selected_anomaly == "Некорректная валюта":
    # Проверяем, есть ли валюты, которых нет в fx_rates (редко)
    anomalies = df_filtered[df_filtered['usd_rate'].isna()].copy()
    anomalies = anomalies[['transaction_id', 'client_id', 'created_at', 'currency', 'amount', 'status']]
    st.warning(f"Найдено {len(anomalies)} транзакций с неизвестной валютой")

if not anomalies.empty:
    st.dataframe(anomalies, use_container_width=True)
    
    # Скачивание
    csv = anomalies.to_csv(index=False)
    st.download_button(
        label="📥 Скачать аномалии (CSV)",
        data=csv,
        file_name=f"anomalies_{selected_anomaly.replace(' ', '_')}.csv",
        mime="text/csv"
    )
else:
    if not st.session_state.get('no_data_shown', False):
        st.info("Аномалий данного типа не обнаружено")

st.markdown("---")

# -----------------------------------------------------------------------------
# 6. Дополнительно: сводная таблица по статусам
# -----------------------------------------------------------------------------

st.subheader("📊 Сводка по статусам")

status_summary = df_filtered.groupby('status').agg(
    count=('transaction_id', 'count'),
    total_amount_usd=('amount_usd', 'sum')
).reset_index()

# Проценты
total_count = status_summary['count'].sum()
status_summary['share'] = status_summary['count'] / total_count * 100

# Форматируем
status_summary['total_amount_usd'] = status_summary['total_amount_usd'].apply(lambda x: f"${x:,.0f}")
status_summary['share'] = status_summary['share'].apply(lambda x: f"{x:.1f}%")

st.dataframe(status_summary, hide_index=True, use_container_width=True)

st.caption("📊 Данные: транзакции CrossPay, конвертация в USD по курсам на дату платежа")