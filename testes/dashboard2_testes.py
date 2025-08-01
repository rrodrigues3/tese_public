import streamlit as st
import pandas as pd
import os
import altair as alt
import pathlib
import locale
import numpy as np
from datetime import timedelta

# Setup da página
st.set_page_config(page_title="Dashboard Mosca da Azeitona", layout="wide")
st.title("🪰 Dashboard - Capturas da Mosca da Azeitona")

# Diretório base
BASE_DIR = pathlib.Path(__file__).parent.resolve()

# Definir locale para português
try:
    locale.setlocale(locale.LC_TIME, 'pt_PT.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except:
        pass  # fallback

# Função para extrair centros das bounding boxes a partir da string do CSV
def extrair_centros(coord_str):
    if pd.isna(coord_str) or coord_str.strip() == "":
        return []
    centros = []
    boxes = coord_str.split(";")
    for box in boxes:
        coords = box.strip().split(",")
        if len(coords) == 4:
            try:
                x_min, y_min, x_max, y_max = map(int, coords)
                cx = (x_min + x_max) / 2
                cy = (y_min + y_max) / 2
                centros.append((cx, cy))
            except:
                pass
    return centros

# Função para remover detecções duplicadas entre dias consecutivos (por placa e classe)
def remover_detecoes_duplicadas(df, tolerancia_px=30):
    df = df.sort_values(["Placa ID", "Data imagem"]).copy()
    df["Data imagem"] = pd.to_datetime(df["Data imagem"])

    # Preenche valores nulos das coord com string vazia
    for classe in ["femea", "macho", "mosca"]:
        df[f"Coord. {classe}"] = df[f"Coord. {classe}"].fillna("")

    indices = df.index.to_list()

    for i in range(1, len(indices)):
        idx_atual = indices[i]
        idx_anterior = indices[i - 1]

        if df.at[idx_atual, "Placa ID"] != df.at[idx_anterior, "Placa ID"]:
            # Placas diferentes, não comparar
            continue

        for classe in ["femea", "macho", "mosca"]:
            coords_atual = extrair_centros(df.at[idx_atual, f"Coord. {classe}"])
            coords_ant = extrair_centros(df.at[idx_anterior, f"Coord. {classe}"])

            coords_filtrados = []
            for (cx, cy) in coords_atual:
                duplicado = False
                for (px, py) in coords_ant:
                    dist = np.sqrt((cx - px) ** 2 + (cy - py) ** 2)
                    if dist <= tolerancia_px:
                        duplicado = True
                        break
                if not duplicado:
                    coords_filtrados.append((cx, cy))

            # Atualizar contagem e coordenadas (reconstruir string)
            df.at[idx_atual, f"Nº {classe}"] = len(coords_filtrados)

            # Reconstruir string no formato original: "x_min,y_min,x_max,y_max; ..."
            # Criar caixas 20x20 px centradas nos centros filtrados
            caixas_str = []
            tamanho = 20
            for (cx, cy) in coords_filtrados:
                x_min = int(cx - tamanho/2)
                y_min = int(cy - tamanho/2)
                x_max = int(cx + tamanho/2)
                y_max = int(cy + tamanho/2)
                caixas_str.append(f"{x_min},{y_min},{x_max},{y_max}")
            df.at[idx_atual, f"Coord. {classe}"] = "; ".join(caixas_str)

    return df

# Carregar dados
@st.cache_data(ttl=60)
def carregar_dados():
    df = pd.read_csv(BASE_DIR / "results.csv", dtype=str)
    for col in ["Nº femea", "Nº macho", "Nº mosca"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["Data imagem"] = pd.to_datetime(df["Data imagem"], errors="coerce")
    df["Localização"] = df["Localização"].fillna("Desconhecida")
    df = df.sort_values("Data imagem", ascending=False)
    return df

df = carregar_dados()

# Aplicar filtro para remover duplicados
df = remover_detecoes_duplicadas(df)

# Filtros laterais
with st.sidebar:
    st.header("🔍 Filtros")
    
    localizacoes = st.multiselect("Filtrar por localização", df["Localização"].unique())
    if localizacoes:
        df = df[df["Localização"].isin(localizacoes)]

    data_range = st.date_input("Filtrar por intervalo de datas", [])
    if len(data_range) == 2:
        inicio, fim = data_range
        df = df[(df["Data imagem"].dt.date >= inicio) & (df["Data imagem"].dt.date <= fim)]

# 📈 Curva de voo + Alerta de risco elevado
st.subheader("📈 Curva de Voo (Capturas por Dia)")

# Agrupamento correto e cálculos diários
df_agg = df.groupby("Data imagem")[["Nº femea", "Nº macho", "Nº mosca"]].sum().sort_index()
df_agg["Acumulado Total"] = df_agg["Nº mosca"].cumsum()
df_agg["Nº mosca dia"] = df_agg["Acumulado Total"].diff().fillna(df_agg["Acumulado Total"]).clip(lower=0).astype(int)
df_agg["Nº femea dia"] = df_agg["Nº femea"].diff().fillna(df_agg["Nº femea"]).clip(lower=0).astype(int)
df_agg["Nº macho dia"] = df_agg["Nº macho"].diff().fillna(df_agg["Nº macho"]).clip(lower=0).astype(int)

df_daily = df_agg[["Nº femea dia", "Nº macho dia", "Nº mosca dia", "Acumulado Total"]].copy()
df_daily.index = df_daily.index.date
df_daily = df_daily.reset_index().rename(columns={"index": "Data"})

# Alerta de risco elevado
moscas_altas = df_daily[df_daily["Nº mosca dia"] > 5]
n_alertas = len(moscas_altas)

if "n_alertas_vistos" not in st.session_state:
    st.session_state.n_alertas_vistos = 0
if "alerta_silenciado" not in st.session_state:
    st.session_state.alerta_silenciado = False

if n_alertas > st.session_state.n_alertas_vistos or not st.session_state.alerta_silenciado:
    with st.container():
        st.error(f"🚨 Alerta: Foram detetadas {n_alertas} dias com mais de 5 moscas. Risco elevado!")
        if st.button("🔕 Silenciar alerta"):
            st.session_state.alerta_silenciado = True
            st.session_state.n_alertas_vistos = n_alertas

# Gráfico da curva de voo
max_y = df_daily["Nº mosca dia"].max()

st.altair_chart(
    alt.Chart(df_daily).mark_line(point=True).encode(
        x=alt.X('Data:T', title='Data', axis=alt.Axis(format='%d %b')),  # Dia e mês em português
        y=alt.Y(
            'Nº mosca dia:Q',
            title='Nº moscas',
            scale=alt.Scale(domain=[0, max_y + 1]),
            axis=alt.Axis(tickCount=max_y + 1)
        )
    ).properties(width=700, height=300),
    use_container_width=True
)

# 📋 Deteções Diárias
st.subheader("📋 Deteções Diárias")
df_daily_sorted = df_daily.sort_values("Data", ascending=False)
st.dataframe(df_daily_sorted.rename(columns={
    "Nº femea dia": "Nº femea",
    "Nº macho dia": "Nº macho",
    "Nº mosca dia": "Nº mosca"
}), use_container_width=True)

# 📊 Capturas por Classe
st.subheader("📊 Capturas por Classe")
capturas_classes = df[["Nº femea", "Nº macho", "Nº mosca"]].sum().reset_index()
capturas_classes.columns = ["Classe", "Total"]
st.bar_chart(capturas_classes.set_index("Classe"))

# 📅 Capturas Semanais por Classe
df["Semana"] = df["Data imagem"].dt.isocalendar().week
st.subheader("📅 Capturas Semanais por Classe")
st.dataframe(df.groupby("Semana")[["Nº femea", "Nº macho", "Nº mosca"]].sum(), use_container_width=True)

# 📆 Capturas Mensais por Classe
df["Mês"] = df["Data imagem"].dt.month
st.subheader("📆 Capturas Mensais por Classe")
st.dataframe(df.groupby("Mês")[["Nº femea", "Nº macho", "Nº mosca"]].sum(), use_container_width=True)

# 🪧 Capturas por Placa
st.subheader("🪧 Capturas por Placa")
st.dataframe(df.groupby("Placa ID")[["Nº femea", "Nº macho", "Nº mosca"]].sum(), use_container_width=True)

# 🗺️ Mapa de Localizações
st.subheader("🗺️ Mapa de Localizações")
df_mapa = df[["Latitude", "Longitude"]].dropna()
df_mapa["Latitude"] = pd.to_numeric(df_mapa["Latitude"], errors="coerce")
df_mapa["Longitude"] = pd.to_numeric(df_mapa["Longitude"], errors="coerce")
df_mapa = df_mapa.dropna()

if not df_mapa.empty:
    st.map(df_mapa.rename(columns={"Latitude": "latitude", "Longitude": "longitude"}))
else:
    st.info("Sem coordenadas disponíveis para o mapa.")

# 📁 Ver imagens com deteções detalhadas
with st.expander("📁 Ver imagens com deteções detalhadas"):
    for idx, row in df.iterrows():
        st.markdown(f"### 🖼️ {row['Nome da imagem']} - {row['Data imagem'].date()}")

        cols = st.columns(3)
        for i, classe in enumerate(["femea", "macho", "mosca"]):
            img_path = BASE_DIR / "detections_output" / f"{row['Nome da imagem']}_det_{classe}.jpg"
            if img_path.exists():
                cols[i].image(str(img_path), caption=classe.capitalize(), use_container_width=True)
            else:
                cols[i].write(f"🔍 Sem imagem de {classe}")

        st.markdown(f"**📍 Localização:** {row['Localização']}")
        st.markdown(f"**🔢 Nº Deteções:** F: {row['Nº femea']} | M: {row['Nº macho']} | Mo: {row['Nº mosca']}")
        st.markdown("---")

# Rodapé
st.caption("Atualizado automaticamente a cada 12 horas · Desenvolvido por Rafael Rodrigues")