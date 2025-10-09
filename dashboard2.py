import streamlit as st
import pandas as pd
import altair as alt
import pathlib
import sqlite3
from datetime import date

# ---------------------------------------------------
# Setup da página
# ---------------------------------------------------
st.set_page_config(page_title="Dashboard Mosca da Azeitona", layout="wide")
st.title("🪰 Dashboard - Capturas da Mosca da Azeitona")

BASE_DIR = pathlib.Path(__file__).parent.resolve()

# ---------------------------------------------------
# Carregar dados mestre (Excel)
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
    df["First_Confidence"] = pd.to_numeric(df["First_Confidence"], errors="coerce").fillna(0)
    df = df.sort_values("First_Detection_Date", ascending=False)
    return df

df_mestre = carregar_dados_mestre()
if df_mestre.empty:
    st.stop()

# ---------------------------------------------------
# Carregar localização das armadilhas a partir da BD
# ---------------------------------------------------
def carregar_localizacoes():
    db_path = BASE_DIR / "../tese_public/placas.db"
    if not db_path.exists():
        st.warning("Base de dados 'placas.db' não encontrada. Apenas serão usadas localizações do Excel.")
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)
    query = """
        SELECT 
            p.placa_id AS "Placa ID",
            a.nome AS "Nome Armadilha",
            a.localidade AS "Localização",
            a.latitude AS "Latitude",
            a.longitude AS "Longitude"
        FROM placas p
        JOIN armadilhas a ON p.id_armadilha = a.id
    """
    try:
        df_loc = pd.read_sql_query(query, conn)
    except Exception as e:
        st.error(f"Erro a ler dados de 'placas.db': {e}")
        conn.close()
        return pd.DataFrame()

    conn.close()
    return df_loc

df_localizacoes = carregar_localizacoes()

# ---------------------------------------------------
# Juntar localização das armadilhas ao ficheiro mestre
# ---------------------------------------------------
if not df_localizacoes.empty:
    df_mestre = df_mestre.merge(df_localizacoes, on="Placa ID", how="left")

    # Substituir valores antigos, se existirem
    df_mestre["Localização"] = df_mestre["Localização_y"].combine_first(df_mestre.get("Localização_x"))
    df_mestre["Latitude"] = df_mestre.get("Latitude_y", df_mestre.get("Latitude_x"))
    df_mestre["Longitude"] = df_mestre.get("Longitude_y", df_mestre.get("Longitude_x"))
    df_mestre["Nome Armadilha"] = df_mestre.get("Nome Armadilha")

    # Limpar colunas duplicadas
    df_mestre.drop(
        columns=[c for c in df_mestre.columns if c.endswith("_x") or c.endswith("_y")],
        inplace=True,
        errors="ignore"
    )

# ---------------------------------------------------
# Filtros (sidebar)
# ---------------------------------------------------
with st.sidebar:
    st.header("🔍 Filtros")

    # Combinar localizações da BD e do ficheiro mestre
    if not df_localizacoes.empty:
        todas_localizacoes = sorted(
            set(df_localizacoes["Localização"].dropna().unique()) |
            set(df_mestre["Localização"].dropna().unique())
        )
    else:
        todas_localizacoes = sorted(df_mestre["Localização"].dropna().unique())

    # Filtro de localização (NÃO seleciona tudo por defeito)
    localizacoes = st.multiselect(
        "Filtrar por localização",
        todas_localizacoes
    )

    # Intervalo de datas
    if not df_mestre.empty and "First_Detection_Date" in df_mestre.columns:
        min_date = df_mestre["First_Detection_Date"].min().date()
        max_date = df_mestre["First_Detection_Date"].max().date()
    else:
        min_date = max_date = None

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
            (df_filtrado["First_Detection_Date"].dt.date >= inicio)
            & (df_filtrado["First_Detection_Date"].dt.date <= fim)
        ]



# ---------------------------------------------------
# Curva de voo 
# ---------------------------------------------------
st.subheader("📈 Curva de Voo")

# Verificar se após os filtros existem datas válidas
valid_dates = df_filtrado["First_Detection_Date"].dropna()

if valid_dates.empty:
    # Aviso informativo ao utilizador (não é um erro)
    st.info("Sem deteções nas localizações/intervalo selecionados — gráfico vazio (não há datas).")

    # Escolher um intervalo razoável para desenhar um gráfico vazio:
    # usamos a menor data do ficheiro mestre (se existir) ou hoje como fallback.
    mestre_dates = df_mestre["First_Detection_Date"].dropna()
    if not mestre_dates.empty:
        start_date = mestre_dates.min().date()
    else:
        # fallback simples: hoje (gera uma linha com um único dia)
        start_date = date.today()

    end_date = date.today()
    full_dates = pd.date_range(start=start_date, end=end_date, freq="D").date

    # DataFrame com zeros (para evitar erros nas chamadas seguintes)
    df_daily = pd.DataFrame(0, index=full_dates, columns=["femea", "macho", "mosca"])
else:
    # Cálculo normal quando há datas
    start_date = valid_dates.min().date()
    end_date = date.today()
    full_dates = pd.date_range(start=start_date, end=end_date, freq="D").date

    df_daily = (
        df_filtrado.groupby([df_filtrado["First_Detection_Date"].dt.date, "Class"])["Fly_ID"]
        .count()
        .unstack(fill_value=0)
    )
    df_daily = df_daily.reindex(columns=["femea", "macho", "mosca"], fill_value=0)
    df_daily = df_daily.reindex(full_dates, fill_value=0)

# Normalizar e preparar para o gráfico (funciona tanto com dados reais como com zeros)
df_daily.index.name = "Data"
df_daily = df_daily.reset_index().rename(
    columns={"femea": "Nº Fêmeas", "macho": "Nº Machos", "mosca": "Nº Moscas"}
)
df_daily["Total Moscas"] = df_daily[["Nº Fêmeas", "Nº Machos", "Nº Moscas"]].sum(axis=1)
df_daily["Acumulado"] = df_daily["Total Moscas"].cumsum()

# Mantém o alerta caso existam dias com mais de 3 moscas (se houver dados reais)
moscas_altas = df_daily[df_daily["Total Moscas"] > 3]
if not moscas_altas.empty and valid_dates.size > 0:
    st.error(f"🚨 Alerta: {len(moscas_altas)} dias com mais de 3 moscas capturadas.")

max_y = int(df_daily["Total Moscas"].max() if df_daily["Total Moscas"].size > 0 else 1)
chart = (
    alt.Chart(df_daily)
    .transform_fold(["Nº Fêmeas", "Nº Machos", "Nº Moscas"], as_=["Classe", "Contagem"])
    .mark_line(point=True)
    .encode(
        x=alt.X("Data:T", title="Data", axis=alt.Axis(format="%d %b")),
        y=alt.Y("Contagem:Q", title="Nº Moscas", scale=alt.Scale(domain=[0, max_y + 1])),
        color="Classe:N",
        tooltip=["Data", "Nº Fêmeas", "Nº Machos", "Nº Moscas", "Acumulado"],
    )
    .properties(height=300)
    .interactive()
)
st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------
# Tabelas
# ---------------------------------------------------
st.subheader("📋 Resumo Diário de Moscas")
st.dataframe(
    df_daily[["Data", "Nº Fêmeas", "Nº Machos", "Nº Moscas", "Acumulado"]].sort_values(
        "Data", ascending=False
    ),
    use_container_width=True,
)

st.subheader("📊 Total de Moscas por Classe")
capturas_classes = (
    df_filtrado["Class"]
    .value_counts()
    .reindex(["femea", "macho", "mosca"], fill_value=0)
    .reset_index()
)
capturas_classes.columns = ["Classe", "Total"]
st.bar_chart(capturas_classes.set_index("Classe"))

st.subheader("📅 Moscas Capturadas por Semana")
df_filtrado["Semana"] = df_filtrado["First_Detection_Date"].dt.isocalendar().week
semanal_df = (
    df_filtrado.groupby(["Semana", "Class"])["Fly_ID"]
    .count()
    .unstack(fill_value=0)
    .reindex(columns=["femea", "macho", "mosca"], fill_value=0)
)
st.dataframe(semanal_df, use_container_width=True)

st.subheader("📆 Moscas Capturadas por Mês")
df_filtrado["Mês"] = df_filtrado["First_Detection_Date"].dt.strftime("%Y-%m (%B)")
mensal_df = (
    df_filtrado.groupby(["Mês", "Class"])["Fly_ID"]
    .count()
    .unstack(fill_value=0)
    .reindex(columns=["femea", "macho", "mosca"], fill_value=0)
)
st.dataframe(mensal_df, use_container_width=True)

st.subheader("🪧 Total de Moscas Capturadas por Placa")
placa_df = (
    df_filtrado.groupby(["Placa ID", "Class"])["Fly_ID"]
    .count()
    .unstack(fill_value=0)
    .reindex(columns=["femea", "macho", "mosca"], fill_value=0)
)
st.dataframe(placa_df, use_container_width=True)

# ---------------------------------------------------
# Mapa de Armadilhas
# ---------------------------------------------------
st.subheader("🗺️ Mapa Localização das Armadilhas ")

if not df_localizacoes.empty:
    df_mapa = df_localizacoes[["Latitude", "Longitude"]].dropna().drop_duplicates()
else:
    df_mapa = df_filtrado[["Latitude", "Longitude"]].dropna().drop_duplicates()

if not df_mapa.empty:
    st.map(df_mapa.rename(columns={"Latitude": "latitude", "Longitude": "longitude"}))
else:
    st.info("Sem coordenadas para o mapa.")

# ---------------------------------------------------
# Imagens apenas com deteções (filtradas)
# ---------------------------------------------------
with st.expander("📁 Ver imagens de deteção por data de processamento", expanded=True):
    if not df_filtrado.empty:
        # Limpar nomes das imagens
        df_filtrado["First_Detection_Image_clean"] = (
            df_filtrado["First_Detection_Image"].str.strip().str.lower()
        )

        # Agrupar por imagem e localização e contar Fly_ID por classe
        df_counts = (
            df_filtrado.groupby(["First_Detection_Image_clean", "Localização", "Class"])["Fly_ID"]
            .nunique()
            .unstack(fill_value=0)
            .reset_index()
        )

        # Ordenar pelas mais recentes
        df_counts = df_counts.merge(
            df_filtrado[["First_Detection_Image_clean", "First_Detection_Date"]].drop_duplicates(),
            on="First_Detection_Image_clean",
            how="left",
        ).sort_values(by="First_Detection_Date", ascending=False)

        # Iterar pelas imagens filtradas
        for _, row in df_counts.iterrows():
            img_name = row["First_Detection_Image_clean"]
            localizacao = row["Localização"]
            img_date = row["First_Detection_Date"].date() if pd.notna(row["First_Detection_Date"]) else "Sem data"

            n_f = int(row.get("femea", 0) or 0)
            n_m = int(row.get("macho", 0) or 0)
            n_mo = int(row.get("mosca", 0) or 0)

            # Exibir cabeçalho da imagem
            st.markdown(f"### 🖼️ {img_date}")
            st.markdown(f"**📍 Localização:** {localizacao}")
            st.markdown(f"**🔢 Deteções:** F: {n_f} | M: {n_m} | Mo: {n_mo}")

            # Mostrar as imagens correspondentes
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
        st.info("Sem imagens para as localizações/intervalo selecionados.")

# ---------------------------------------------------
# Rodapé
# ---------------------------------------------------
st.caption("Dashboard monitorização da mosca da azeitona · Desenvolvido por Rafael Rodrigues")
