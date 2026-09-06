import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Клиенты и сегменты", layout="wide")



@st.cache_data
def load_clients():
    return pd.read_csv('data/clients.csv')

@st.cache_data
def load_transactions():
    trans = pd.read_csv('data/transactions.csv')
    fx = pd.read_csv('data/fx_rates.csv')
    
    trans['created_at'] = pd.to_datetime(trans['created_at'])
    fx['date'] = pd.to_datetime(fx['date'])
    
    # Построение словаря курсов
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
def prepare_data():
    clients = load_clients()
    trans = load_transactions()
    
    # Только успешные транзакции для расчётов доходности
    completed = trans[trans['status'] == 'completed'].copy()
    
    # Агрегация по клиентам: общий GMV, выручка, количество транзакций
    client_agg = completed.groupby('client_id').agg(
        total_gmv=('amount_usd', 'sum'),
        total_revenue=('client_fee_usd', 'sum'),
        total_cost=('direct_cost_usd', 'sum'),
        tx_count=('transaction_id', 'count'),
        first_tx=('created_at', 'min'),
        last_tx=('created_at', 'max')
    ).reset_index()
    
    # Объединение с данными клиентов
    df = clients.merge(client_agg, on='client_id', how='left').fillna({
        'total_gmv': 0,
        'total_revenue': 0,
        'total_cost': 0,
        'tx_count': 0,
        'first_tx': pd.NaT,
        'last_tx': pd.NaT
    })
    
    # Для новых клиентов по месяцам
    df['signup_month'] = pd.to_datetime(df['signup_date']).dt.to_period('M').dt.to_timestamp()
    
    return df, completed

df_clients, df_trans = prepare_data()



@st.cache_data
def calculate_retention(df_clients, df_trans):
    """Рассчитывает retention для каждого клиента: наличие второй транзакции в интервалах 30, 60, 90 дней."""
    # Для каждого клиента получаем все даты транзакций (completed)
    tx_dates = df_trans[['client_id', 'created_at']].drop_duplicates()
    tx_dates = tx_dates.sort_values(['client_id', 'created_at'])
    
    # Первая и вторая транзакция
    first = tx_dates.groupby('client_id').first().reset_index()
    second = tx_dates.groupby('client_id').nth(1).reset_index()
    
    merged = first.merge(second, on='client_id', how='left', suffixes=('_first', '_second'))
    merged['days_diff'] = (merged['created_at_second'] - merged['created_at_first']).dt.days
    
    # Метки retention
    merged['retention_30'] = merged['days_diff'] <= 30
    merged['retention_60'] = merged['days_diff'] <= 60
    merged['retention_90'] = merged['days_diff'] <= 90
    
    return merged[['client_id', 'retention_30', 'retention_60', 'retention_90']]

retention_data = calculate_retention(df_clients, df_trans)
df_clients = df_clients.merge(retention_data, on='client_id', how='left').fillna({
    'retention_30': False,
    'retention_60': False,
    'retention_90': False
})

st.sidebar.title("Клиенты и сегменты")
st.sidebar.markdown("---")

# Фильтр по дате регистрации
min_date = df_clients['signup_month'].min()
max_date = df_clients['signup_month'].max()
if pd.isna(min_date):
    st.warning("Нет данных о клиентах")
    st.stop()

date_range = st.sidebar.slider(
    "Период регистрации клиентов",
    min_value=min_date.to_pydatetime(),
    max_value=max_date.to_pydatetime(),
    value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
    format="YYYY-MM"
)

df_filtered = df_clients[
    (df_clients['signup_month'] >= pd.to_datetime(date_range[0])) &
    (df_clients['signup_month'] <= pd.to_datetime(date_range[1]))
]

# Дополнительные фильтры
segments = ['Все'] + sorted(df_filtered['segment'].dropna().unique().tolist())
selected_segment = st.sidebar.selectbox("Сегмент", segments)

countries = ['Все'] + sorted(df_filtered['country'].dropna().unique().tolist())
selected_country = st.sidebar.selectbox("Страна", countries)

# Применяем фильтры
if selected_segment != 'Все':
    df_filtered = df_filtered[df_filtered['segment'] == selected_segment]
if selected_country != 'Все':
    df_filtered = df_filtered[df_filtered['country'] == selected_country]

st.sidebar.markdown("---")
st.sidebar.caption(f"Клиентов: {len(df_filtered)}")

# -----------------------------------------------------------------------------
# 5. Основная панель
# -----------------------------------------------------------------------------

st.title("👥 Клиенты и сегменты (Client Analytics)")

# KPI
col1, col2, col3, col4, col5 = st.columns(5)

total_clients = len(df_filtered)
active_clients = df_filtered[df_filtered['tx_count'] > 0].shape[0]
avg_arpu = df_filtered[df_filtered['tx_count'] > 0]['total_revenue'].mean() if active_clients > 0 else 0
new_clients = df_filtered[df_filtered['signup_month'] == df_filtered['signup_month'].max()].shape[0]
retention_rate = df_filtered['retention_30'].mean() * 100

with col1:
    st.metric("Всего клиентов", f"{total_clients:,}")
with col2:
    st.metric("Активные клиенты", f"{active_clients:,}", f"{active_clients/total_clients:.1%} от всех")
with col3:
    st.metric("Средний ARPU", f"${avg_arpu:,.2f}")
with col4:
    st.metric("Новых за месяц", f"{new_clients:,}")
with col5:
    st.metric("Retention (30 дней)", f"{retention_rate:.1f}%")

st.markdown("---")

# Графики в две колонки
col_left, col_right = st.columns(2)

with col_left:
    # 1. Распределение клиентов по сегментам
    seg_dist = df_filtered['segment'].value_counts().reset_index()
    seg_dist.columns = ['segment', 'count']
    fig1 = px.pie(seg_dist, names='segment', values='count', title='Распределение клиентов по сегментам')
    st.plotly_chart(fig1, use_container_width=True)

    # 2. GMV по сегментам
    gmv_by_seg = df_filtered.groupby('segment')['total_gmv'].sum().reset_index()
    fig2 = px.bar(gmv_by_seg, x='segment', y='total_gmv', title='GMV по сегментам',
                  labels={'total_gmv': 'GMV (USD)', 'segment': 'Сегмент'})
    st.plotly_chart(fig2, use_container_width=True)

with col_right:
    # 3. Выручка по сегментам
    rev_by_seg = df_filtered.groupby('segment')['total_revenue'].sum().reset_index()
    fig3 = px.bar(rev_by_seg, x='segment', y='total_revenue', title='Выручка от комиссий по сегментам',
                  labels={'total_revenue': 'Выручка (USD)', 'segment': 'Сегмент'})
    st.plotly_chart(fig3, use_container_width=True)

    # 4. ARPU по сегментам (только активные клиенты)
    active_df = df_filtered[df_filtered['tx_count'] > 0]
    arpu_by_seg = active_df.groupby('segment')['total_revenue'].mean().reset_index()
    fig4 = px.bar(arpu_by_seg, x='segment', y='total_revenue', title='Средний ARPU по сегментам',
                  labels={'total_revenue': 'ARPU (USD)', 'segment': 'Сегмент'})
    st.plotly_chart(fig4, use_container_width=True)

st.markdown("---")

# Дополнительные графики во всю ширину
st.subheader("📊 Дополнительные срезы")

col5, col6 = st.columns(2)

with col5:
    # 5. Новые клиенты по месяцам
    new_by_month = df_filtered.groupby('signup_month').size().reset_index(name='count')
    fig5 = px.line(new_by_month, x='signup_month', y='count', markers=True,
                   title='Новые клиенты по месяцам',
                   labels={'signup_month': 'Месяц регистрации', 'count': 'Количество'})
    st.plotly_chart(fig5, use_container_width=True)

with col6:
    # 6. Топ-стран по выручке
    rev_by_country = df_filtered.groupby('country')['total_revenue'].sum().reset_index()
    rev_by_country = rev_by_country.sort_values('total_revenue', ascending=False).head(10)
    fig6 = px.bar(rev_by_country, x='country', y='total_revenue', title='Топ-10 стран по выручке',
                  labels={'total_revenue': 'Выручка (USD)', 'country': 'Страна'})
    st.plotly_chart(fig6, use_container_width=True)

st.markdown("---")

# 7. Матрица сегмент × размер компании (тепловая карта)
st.subheader("📊 Матрица сегментов и размеров компании")

# GMV матрица
gmv_matrix = df_filtered.pivot_table(
    values='total_gmv',
    index='segment',
    columns='company_size',
    aggfunc='sum',
    fill_value=0
)
fig7 = px.imshow(
    gmv_matrix,
    text_auto=True,
    title='GMV по сегментам и размеру компании',
    labels={'x': 'Размер компании', 'y': 'Сегмент', 'color': 'GMV (USD)'},
    color_continuous_scale='Blues'
)
st.plotly_chart(fig7, use_container_width=True)

# ARPU матрица (только активные)
arpu_matrix = active_df.pivot_table(
    values='total_revenue',
    index='segment',
    columns='company_size',
    aggfunc='mean',
    fill_value=0
)
fig8 = px.imshow(
    arpu_matrix,
    text_auto=True,
    title='Средний ARPU по сегментам и размеру компании',
    labels={'x': 'Размер компании', 'y': 'Сегмент', 'color': 'ARPU (USD)'},
    color_continuous_scale='Reds'
)
st.plotly_chart(fig8, use_container_width=True)

st.markdown("---")

# 8. Детализация по клиентам
st.subheader("🔎 Детализация по клиентам")

# Выбор клиента для просмотра
client_list = df_filtered['client_id'].tolist()
selected_client = st.selectbox("Выберите клиента для детального просмотра", client_list)

client_row = df_filtered[df_filtered['client_id'] == selected_client].iloc[0]

col_det1, col_det2 = st.columns(2)
with col_det1:
    st.write("**Информация о клиенте**")
    det_data = {
        "Параметр": ["Client ID", "Страна", "Сегмент", "Размер компании", "Канал привлечения", "Менеджер"],
        "Значение": [
            client_row['client_id'],
            client_row['country'],
            client_row['segment'],
            client_row['company_size'],
            client_row['acquisition_channel'],
            client_row['account_manager_id']
        ]
    }
    st.dataframe(pd.DataFrame(det_data), hide_index=True, use_container_width=True)

with col_det2:
    st.write("**Финансовые показатели**")
    det_data2 = {
        "Параметр": ["Всего транзакций", "GMV", "Выручка", "Средний чек", "Retention 30д", "Дата регистрации"],
        "Значение": [
            f"{client_row['tx_count']:.0f}",
            f"${client_row['total_gmv']:,.2f}",
            f"${client_row['total_revenue']:,.2f}",
            f"${client_row['total_gmv']/client_row['tx_count'] if client_row['tx_count']>0 else 0:,.2f}",
            "Да" if client_row['retention_30'] else "Нет",
            client_row['signup_date']
        ]
    }
    st.dataframe(pd.DataFrame(det_data2), hide_index=True, use_container_width=True)

st.caption("📊 Данные: клиенты и транзакции CrossPay, конвертация в USD по курсам на дату платежа")