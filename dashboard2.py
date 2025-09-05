import streamlit as st
import pandas as pd
import os
import altair as alt
import pathlib
import locale
from datetime import date

# ---------------------------------------------------
# Setup da página
# ---------------------------------------------------
st.set_page_config(page_title="Dashboard Mosca da Azeitona", layout="wide")
st.title("🪰 Dashboard - Capturas da Mosca da Azeitona")

BASE_DIR = pathlib.Path(__file__).parent.resolve()

# ---------------------------------------------------
# Carregar dados mestre
# ---------------------------------------------------
@st.cache_data(ttl=60)
def carregar_dados_mestre():
    master_file = BASE_DIR / "../tese_public/dashboard_data.xlsx"
    if not master_file.exists():
        st.error("Ficheiro 'dashboard_data.xlsx' não encontrado! Executa o script de processamento primeiro.")
        return pd.DataFrame()

    df = pd.read_excel(master_file, engine='openpyxl')
    df["First_Detection_Date"] = pd.to_datetime(df["First_Detection_Date"], errors='coerce')
    df["Localização"] = df["Localização"].fillna("Desconhecida")
    df['First_Confidence'] = pd.to_numeric(df['First_Confidence'], errors='coerce').fillna(0)
    df = df.sort_values("First_Detection_Date", ascending=False)
    return df

df_mestre = carregar_dados_mestre()
if df_mestre.empty:
    st.stop()

# ---------------------------------------------------
# Filtros (sidebar)
# ---------------------------------------------------
with st.sidebar:
    st.header("🔍 Filtros")

    localizacoes_disponiveis = df_mestre["Localização"].unique()
    localizacoes = st.multiselect("Filtrar por localização", localizacoes_disponiveis)

    min_date = df_mestre["First_Detection_Date"].min().date()
    max_date = df_mestre["First_Detection_Date"].max().date()
    data_range = st.date_input(
        "Filtrar por intervalo de datas",
        value=(),
        min_value=min_date,
        max_value=max_date
    )

    df_filtrado = df_mestre.copy()
    if localizacoes:
        df_filtrado = df_filtrado[df_filtrado["Localização"].isin(localizacoes)]

    if len(data_range) == 2:
        inicio, fim = data_range
        df_filtrado = df_filtrado[
            (df_filtrado["First_Detection_Date"].dt.date >= inicio) &
            (df_filtrado["First_Detection_Date"].dt.date <= fim)
        ]

# ---------------------------------------------------
# Curva de voo 
# ---------------------------------------------------
st.subheader("📈 Curva de Voo")

df_daily = df_filtrado.groupby([df_filtrado['First_Detection_Date'].dt.date, 'Class'])['Fly_ID'] \
    .count().unstack(fill_value=0)
df_daily = df_daily.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)

start_date = df_filtrado['First_Detection_Date'].dt.date.min()
end_date = date.today()
full_dates = pd.date_range(start=start_date, end=end_date, freq='D').date
df_daily = df_daily.reindex(full_dates, fill_value=0)
df_daily.index.name = "Data"

df_daily = df_daily.reset_index().rename(columns={
    'femea': 'Nº Fêmeas',
    'macho': 'Nº Machos',
    'mosca': 'Nº Moscas'
})
df_daily['Total Moscas'] = df_daily[['Nº Fêmeas', 'Nº Machos', 'Nº Moscas']].sum(axis=1)
df_daily['Acumulado'] = df_daily['Total Moscas'].cumsum()

moscas_altas = df_daily[df_daily["Total Moscas"] > 3]
if not moscas_altas.empty:
    st.error(f"🚨 Alerta: {len(moscas_altas)} dias com mais de 3 moscas capturadas.")

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

# ---------------------------------------------------
# Tabelas 
# ---------------------------------------------------
st.subheader("📋 Resumo Diário de Moscas")
st.dataframe(df_daily[['Data', 'Nº Fêmeas', 'Nº Machos', 'Nº Moscas', 'Acumulado']]
             .sort_values("Data", ascending=False),
             use_container_width=True)

st.subheader("📊 Total de Moscas por Classe")
capturas_classes = df_filtrado['Class'].value_counts().reindex(['femea', 'macho', 'mosca'], fill_value=0).reset_index()
capturas_classes.columns = ["Classe", "Total"]
st.bar_chart(capturas_classes.set_index("Classe"))

st.subheader("📅 Moscas Capturadas por Semana")
df_filtrado['Semana'] = df_filtrado['First_Detection_Date'].dt.isocalendar().week
semanal_df = df_filtrado.groupby(['Semana', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
semanal_df = semanal_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(semanal_df, use_container_width=True)

st.subheader("📆 Moscas Capturadas por Mês")
df_filtrado['Mês'] = df_filtrado['First_Detection_Date'].dt.strftime('%Y-%m (%B)')
mensal_df = df_filtrado.groupby(['Mês', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
mensal_df = mensal_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(mensal_df, use_container_width=True)

st.subheader("🪧 Total de Moscas Capturadas por Placa")
placa_df = df_filtrado.groupby(['Placa ID', 'Class'])['Fly_ID'].count().unstack(fill_value=0)
placa_df = placa_df.reindex(columns=['femea', 'macho', 'mosca'], fill_value=0)
st.dataframe(placa_df, use_container_width=True)

st.subheader("🗺️ Mapa de Armadilhas com Deteções")
df_mapa = df_filtrado[['Latitude', 'Longitude']].dropna().drop_duplicates()
df_mapa["Latitude"] = pd.to_numeric(df_mapa["Latitude"], errors='coerce')
df_mapa["Longitude"] = pd.to_numeric(df_mapa["Longitude"], errors='coerce')
df_mapa = df_mapa.dropna()
if not df_mapa.empty:
    st.map(df_mapa.rename(columns={"Latitude": "latitude", "Longitude": "longitude"}))
else:
    st.info("Sem coordenadas para o mapa.")

# ---------------------------------------------------
# Imagens apenas com deteções
# ---------------------------------------------------
with st.expander("📁 Ver imagens de deteção por data de processamento", expanded=True):
    if not df_mestre.empty:
        # Limpar nomes das imagens
        df_mestre['First_Detection_Image_clean'] = df_mestre['First_Detection_Image'].str.strip().str.lower()

        # Agrupar por imagem e localização e contar Fly_ID por classe
        df_counts = df_mestre.groupby(['First_Detection_Image_clean', 'Localização', 'Class'])['Fly_ID'] \
            .nunique().unstack(fill_value=0)

        # Resetar index para facilitar acesso
        df_counts = df_counts.reset_index()

        # Ordenar pelas mais recentes (baseado na primeira deteção)
        df_counts = df_counts.merge(
            df_mestre[['First_Detection_Image_clean', 'First_Detection_Date']].drop_duplicates(),
            on='First_Detection_Image_clean',
            how='left'
        )
        df_counts = df_counts.sort_values(by='First_Detection_Date', ascending=False)

        # Iterar pelas imagens
        for _, row in df_counts.iterrows():
            img_name = row['First_Detection_Image_clean']
            localizacao = row['Localização']

            n_f = int(row.get('femea', 0) or 0)
            n_m = int(row.get('macho', 0) or 0)
            n_mo = int(row.get('mosca', 0) or 0)

            # Exibir localização acima do nome
            st.markdown(f"### 🖼️ {img_name}")
            st.markdown(f"**📍 Localização:** {localizacao}")
            st.markdown(f"**🔢 Deteções:** F: {n_f} | M: {n_m} | Mo: {n_mo}")

            # Mostrar imagens por classe
            colunas = st.columns(3)
            for i, classe in enumerate(["femea", "macho", "mosca"]):
                img_nome_classe = f"{img_name}_det_{classe}.jpg"
                img_path = BASE_DIR / "../tese_public/detections_output" / img_nome_classe
                if img_path.exists():
                    with colunas[i]:
                        st.image(str(img_path), caption=classe.capitalize(), use_container_width=True)
                else:
                    with colunas[i]:
                        st.warning(f"Sem deteção de {classe}.")
            st.markdown("---")
    else:
        st.info("Excel mestre vazio, não há imagens.")

# ---------------------------------------------------
# Rodapé
# ---------------------------------------------------
st.caption("Dashboard monitorização da mosca da azeitona · Desenvolvido por Rafael Rodrigues")