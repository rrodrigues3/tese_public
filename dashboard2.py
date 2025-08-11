import streamlit as st
import pandas as pd
import os
import altair as alt
import pathlib
import locale
from datetime import date

# Setup da página
st.set_page_config(page_title="Dashboard Mosca da Azeitona", layout="wide")
st.title("🪰 Dashboard - Capturas da Mosca da Azeitona")

# Diretório base
BASE_DIR = pathlib.Path(__file__).parent.resolve()

# Definir locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_PT.UTF-8')
except Exception:
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        st.warning("Não foi possível definir o locale para Português. As datas podem aparecer em inglês.")

# --- ALTERAÇÃO 1: Carregar os dois ficheiros de dados ---

# Função para carregar a lista MESTRE de moscas únicas (para estatísticas)
@st.cache_data(ttl=60)
def carregar_dados_mestre():
    master_file = BASE_DIR / "../tese_public/dashboard_data.xlsx"
    if not master_file.exists():
        st.error("Ficheiro 'dashboard_data.xlsx' não encontrado! Por favor, execute o script de processamento primeiro.")
        return pd.DataFrame()
        
    df = pd.read_excel(master_file, engine='openpyxl')
    # Conversão de tipos de dados
    df["First_Detection_Date"] = pd.to_datetime(df["First_Detection_Date"], errors='coerce')
    df["Localização"] = df["Localização"].fillna("Desconhecida")
    df['First_Confidence'] = pd.to_numeric(df['First_Confidence'], errors='coerce').fillna(0)
    df = df.sort_values("First_Detection_Date", ascending=False)
    return df

# Função para carregar o LOG de imagens (apenas para a galeria de imagens)
@st.cache_data(ttl=60)
def carregar_dados_log():
    log_file = BASE_DIR / "../tese_public/results.csv"
    if not log_file.exists():
        return pd.DataFrame()
    df = pd.read_csv(log_file)
    df["Data imagem"] = pd.to_datetime(df["Data imagem"], errors='coerce')
    df = df.sort_values("Data imagem", ascending=False)
    return df

# Carregar os dados
df_mestre = carregar_dados_mestre()
df_log = carregar_dados_log()

# Se o ficheiro mestre não carregar, para a execução
if df_mestre.empty:
    st.stop()

# --- ALTERAÇÃO 2: Filtros aplicados aos dados mestre ---
with st.sidebar:
    st.header("🔍 Filtros")
    
    # Filtro por localização
    localizacoes_disponiveis = df_mestre["Localização"].unique()
    localizacoes = st.multiselect("Filtrar por localização", localizacoes_disponiveis)
    
    # Filtro por data
    min_date = df_mestre["First_Detection_Date"].min().date()
    max_date = df_mestre["First_Detection_Date"].max().date()
    data_range = st.date_input(
        "Filtrar por intervalo de datas",
        value=(),
        min_value=min_date,
        max_value=max_date
    )

    # Aplicar filtros
    df_filtrado = df_mestre.copy()
    if localizacoes:
        df_filtrado = df_filtrado[df_filtrado["Localização"].isin(localizacoes)]

    if len(data_range) == 2:
        inicio, fim = data_range
        df_filtrado = df_filtrado[
            (df_filtrado["First_Detection_Date"].dt.date >= inicio) &
            (df_filtrado["First_Detection_Date"].dt.date <= fim)
        ]

# --- ALTERAÇÃO 3: Lógica da Curva de Voo totalmente refeita ---
# --- CURVA DE VOO (NÃO ACUMULADA) ---
st.subheader("📈 Curva de Voo")

# Agrupamento por data (sem hora) e por classe
df_daily = df_filtrado.groupby([df_filtrado['First_Detection_Date'].dt.date, 'Class'])['Fly_ID'].count().unstack(fill_value=0)
df_daily = df_daily.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)

# Preencher datas em falta
start_date = df_filtrado['First_Detection_Date'].dt.date.min()
end_date = date.today()  # força a ir até hoje
full_dates = pd.date_range(start=start_date, end=end_date, freq='D').date
df_daily = df_daily.reindex(full_dates, fill_value=0)
df_daily.index.name = "Data"

# Renomear colunas
df_daily = df_daily.reset_index().rename(columns={
    'femea': 'Nº Fêmeas',
    'macho': 'Nº Machos',
    'mosca': 'Nº Moscas'
})

# Criar coluna Total (mas não acumulada!)
df_daily['Total Moscas'] = df_daily[['Nº Fêmeas', 'Nº Machos', 'Nº Moscas']].sum(axis=1)

df_daily['Acumulado'] = df_daily['Total Moscas'].cumsum()

# Alerta de risco elevado (se num dia > 5 moscas novas)
moscas_altas = df_daily[df_daily["Total Moscas"] > 5]
if not moscas_altas.empty:
    st.error(f"🚨 Alerta: Detetados {len(moscas_altas)} dias com mais de 5 moscas capturadas.")

# Gráfico da curva de voo
max_y = df_daily["Total Moscas"].max()
chart = alt.Chart(df_daily).transform_fold(
    ['Nº Fêmeas', 'Nº Machos', 'Nº Moscas'],
    as_=['Classe', 'Contagem']
).mark_line(point=True).encode(
    x=alt.X('Data:T', title='Data', axis=alt.Axis(format='%d %b')),
    y=alt.Y('Contagem:Q', title='Nº Moscas', scale=alt.Scale(domain=[0, max_y + 1])),
    color='Classe:N',
    tooltip=['Data', 'Nº Fêmeas', 'Nº Machos', 'Nº Moscas', 'Acumulado']
).properties(height=300).interactive()

st.altair_chart(chart, use_container_width=True)


# --- ALTERAÇÃO 4: Todas as tabelas de agregação usam os dados mestre ---

# Deteções Diárias
st.subheader("📋 Resumo Diário de Novas Moscas")
st.dataframe(
    df_daily[['Data', 'Nº Fêmeas', 'Nº Moscas', 'Acumulado']].sort_values("Data", ascending=False), 
    use_container_width=True,
)

# Capturas por Classe
st.subheader("📊 Total de Moscas Únicas por Classe")
capturas_classes = df_filtrado['Class'].value_counts().reindex(['femea', 'macho', 'mosca'], fill_value=0).reset_index()
capturas_classes.columns = ["Classe", "Total"]
st.bar_chart(capturas_classes.set_index("Classe"))

# Capturas Semanais
st.subheader("📅 Moscas Capturadas por Semana")
df_filtrado['Semana'] = df_filtrado['First_Detection_Date'].dt.isocalendar().week
semanal_df = df_filtrado.groupby(['Semana', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
semanal_df = semanal_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(semanal_df, use_container_width=True)

# Capturas Mensais
st.subheader("📆 Moscas Capturadas por Mês")
df_filtrado['Mês'] = df_filtrado['First_Detection_Date'].dt.strftime('%Y-%m (%B)')
mensal_df = df_filtrado.groupby(['Mês', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
mensal_df = mensal_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(mensal_df, use_container_width=True)

# Capturas por Placa
st.subheader("🪧 Total de Moscas Capturadas por Placa")
placa_df = df_filtrado.groupby(['Placa ID', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
placa_df = placa_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(placa_df, use_container_width=True)

# Mapa de Localizações
st.subheader("🗺️ Mapa de Armadilhas com Deteções")
df_mapa = df_filtrado[['Latitude', 'Longitude']].dropna().drop_duplicates()
df_mapa["Latitude"] = pd.to_numeric(df_mapa["Latitude"], errors='coerce')
df_mapa["Longitude"] = pd.to_numeric(df_mapa["Longitude"], errors='coerce')
df_mapa = df_mapa.dropna()

if not df_mapa.empty:
    st.map(df_mapa.rename(columns={"Latitude": "latitude", "Longitude": "longitude"}))
else:
    st.info("Sem coordenadas disponíveis para o mapa.")

# --- ALTERAÇÃO 5: Usar o df_log para a galeria de imagens ---
with st.expander("📁 Ver imagens de deteção por data de processamento", expanded=True):
    if not df_log.empty:
        df_log_filtrado = df_log.copy()

        if localizacoes:
            df_log_filtrado = df_log_filtrado[df_log_filtrado["Localização"].isin(localizacoes)]

        if len(data_range) == 2:
            inicio, fim = data_range
            df_log_filtrado = df_log_filtrado[
                (df_log_filtrado["Data imagem"].dt.date >= inicio) &
                (df_log_filtrado["Data imagem"].dt.date <= fim)
            ]

        if df_log_filtrado.empty:
            st.info("Nenhuma imagem de log corresponde aos filtros selecionados.")

        for _, row in df_log_filtrado.iterrows():
            st.markdown(f"### 🖼️ {row['Nome da imagem']} - {row['Data imagem'].date()}")
            st.markdown(f"**📍 Localização:** {row['Localização']}")
            st.markdown(f"**🔢 Deteções:** F: {row.get('Nº femea', 0)} | M: {row.get('Nº macho', 0)} | Mo: {row.get('Nº mosca', 0)}")

            img_base_name = row['Nome da imagem'].strip()
            variantes = ["femea", "macho", "mosca"]
            colunas = st.columns(3)  # 3 miniaturas lado a lado

            for i, classe in enumerate(variantes):
                img_nome_classe = f"{img_base_name}_det_{classe}.jpg"
                img_path = BASE_DIR / "../tese_public/detections_output" / img_nome_classe

                if img_path.exists():
                    with colunas[i]:
                        st.image(str(img_path), caption=classe.capitalize(), use_container_width=True)
                else:
                    with colunas[i]:
                        st.warning(f"Sem deteção de {classe}.")

            st.markdown("---")
    else:
        st.info("Ficheiro de log 'results.csv' não encontrado. A galeria de imagens não pode ser exibida.")


# Rodapé
st.caption("Dashboard a ler dados de moscas únicas · Desenvolvido por Rafael Rodrigues")
