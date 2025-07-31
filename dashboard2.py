import os
import pandas as pd
from ultralytics import YOLO
from datetime import datetime
import cv2
import sqlite3
import torch
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from scipy.spatial.distance import euclidean
import uuid # Importado para gerar IDs únicos

# Desabilita o backend MKLDNN para evitar possíveis problemas de compatibilidade
torch.backends.mkldnn.enabled = False

# --- Configurações Globais ---
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_IDS = {
    'Olival 5 reis ': '1LaJ5PvkNcYdFVNzKOZxXZ1euLiKDQnWW',
    'Monte das Figueirinhas': '1uHNYFusLzmw6u7b87izTFHd2d5DzSINc'
}

CONFIDENCE_THRESHOLD = 0.4
DISTANCE_THRESHOLD = 80 # Limiar em pixels para considerar a mesma mosca. Ajuste conforme necessário.

CSV_FILE = '/data/rafael/tese_public/results.csv'
EXCEL_FILE = 'results.xlsx'
OUTPUT_DIR = '/data/rafael/tese_public/detections_output'

DB_PATH = 'db/placas.db'  # caminho da base SQLite

# --- Autenticação e Funções Auxiliares ---

def authenticate_drive():
    """Autentica com o Google Drive API."""
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_placas_ativas_info():
    """Busca informações de placas ativas e armadilhas da base SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT placas.placa_id, armadilhas.localidade, armadilhas.latitude, armadilhas.longitude, armadilhas.nome
        FROM placas
        JOIN armadilhas ON placas.id_armadilha = armadilhas.id
        WHERE placas.ativa = 1
        ORDER BY placas.data_colocacao DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_processed_data(csv_file=CSV_FILE):
    """Obtém imagens já processadas e o DataFrame de histórico do CSV."""
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        processed_images = set(df['Nome da imagem'].values)
        return processed_images, df
    return set(), pd.DataFrame()

def download_images(drive_service, files, folder='downloaded_images'):
    """Baixa imagens do Google Drive para uma pasta local."""
    os.makedirs(folder, exist_ok=True)
    downloaded_files = []
    for file in files:
        file_id, file_name, modified_time = file['id'], file['name'], file['modifiedTime']
        file_path = os.path.join(folder, file_name)
        if not os.path.exists(file_path):
            request = drive_service.files().get_media(fileId=file_id)
            with open(file_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            print(f"Baixado: {file_name}")
        downloaded_files.append({'path': file_path, 'name': file_name, 'date': modified_time})
    return downloaded_files

#___
def recalculate_accumulated_counts(df_data):
    """
    Recalcula as contagens acumuladas e retorna um DataFrame com todas as deteções
    e um DataFrame mestre apenas com a primeira deteção de cada mosca.
    """
    # Certifica-se que a coluna de data está no formato datetime
    df_data['Data datetime'] = pd.to_datetime(df_data['Data imagem'].str.split('T').str[0])
    
    # Ordena os dados pela data para garantir que a primeira ocorrência é de facto a mais antiga
    df_data = df_data.sort_values(by='Data datetime', ascending=True)

    all_fly_detections = []
    # Extrai cada deteção de mosca para uma lista plana
    for _, row in df_data.iterrows():
        for class_type in ['femea', 'macho', 'mosca']:
            coords_with_ids = row.get(f'Coord. {class_type}')
            confidences = str(row.get(f'Conf. {class_type}', '')).split('; ')
            
            if pd.notna(coords_with_ids) and coords_with_ids:
                detections = str(coords_with_ids).split('; ')
                for i, entry in enumerate(detections):
                    if ':' in entry:
                        fly_id, coords_str = entry.split(':', 1)
                        # Tenta obter a confiança correspondente, se disponível
                        confidence = confidences[i] if i < len(confidences) else None
                        
                        all_fly_detections.append({
                            'Fly_ID': fly_id,
                            'Class': class_type,
                            'First_Detection_Date': row['Data datetime'],
                            'First_Detection_Image': row['Nome da imagem'],
                            'Placa ID': row['Placa ID'],
                            'Localização': row['Localização'],
                            'Latitude': row['Latitude'],
                            'Longitude': row['Longitude'],
                            'First_Coords': coords_str,
                            'First_Confidence': confidence
                        })

    if not all_fly_detections:
        # Se não houver deteções, retorna o DataFrame original e um DataFrame vazio
        # Garante que as colunas de acumulados existem no df original
        for col in ['Acum. semanal femea', 'Acum. mensal femea', 'Acum. placa femea', 'Acum. semanal macho', 'Acum. mensal macho', 'Acum. placa macho', 'Acum. semanal mosca', 'Acum. mensal mosca', 'Acum. placa mosca']:
            if col not in df_data.columns:
                df_data[col] = 0
        df_data = df_data.drop(columns=['Data datetime'])
        return df_data, pd.DataFrame()

    df_all_flies = pd.DataFrame(all_fly_detections)

    # DataFrame MESTRE: Contém apenas a PRIMEIRA deteção de cada mosca
    # Como os dados foram ordenados por data, drop_duplicates mantém a primeira ocorrência
    df_fly_master_list = df_all_flies.drop_duplicates(subset=['Fly_ID', 'Class'], keep='first').copy()

    # Agora, vamos calcular os acumulados para o DataFrame original (df_data)
    # Esta lógica permanece a mesma que a sua, mas usando df_fly_master_list como fonte da verdade
    
    unique_flies_for_counting = df_fly_master_list.rename(columns={'First_Detection_Date': 'Date'})

    for idx, row in df_data.iterrows():
        current_date_obj = row['Data datetime']
        placa_id_current = row['Placa ID']
        
        for class_type in ['femea', 'macho', 'mosca']:
            # Acumulado da placa: todas as moscas únicas para esta placa até a data atual
            flies_for_placa = unique_flies_for_counting[
                (unique_flies_for_counting['Placa ID'] == placa_id_current) &
                (unique_flies_for_counting['Date'] <= current_date_obj) &
                (unique_flies_for_counting['Class'] == class_type)
            ]
            df_data.at[idx, f'Acum. placa {class_type}'] = flies_for_placa['Fly_ID'].nunique()

            # Acumulado semanal
            current_week_num = current_date_obj.isocalendar()[1]
            current_year = current_date_obj.year
            flies_for_week = unique_flies_for_counting[
                (unique_flies_for_counting['Placa ID'] == placa_id_current) &
                (unique_flies_for_counting['Date'].dt.isocalendar().week == current_week_num) &
                (unique_flies_for_counting['Date'].dt.year == current_year) &
                (unique_flies_for_counting['Class'] == class_type)
            ]
            df_data.at[idx, f'Acum. semanal {class_type}'] = flies_for_week['Fly_ID'].nunique()

            # Acumulado mensal
            flies_for_month = unique_flies_for_counting[
                (unique_flies_for_counting['Placa ID'] == placa_id_current) &
                (unique_flies_for_counting['Date'].dt.month == current_date_obj.month) &
                (unique_flies_for_counting['Date'].dt.year == current_year) &
                (unique_flies_for_counting['Class'] == class_type)
            ]
            df_data.at[idx, f'Acum. mensal {class_type}'] = flies_for_month['Fly_ID'].nunique()

    # Remove a coluna de data auxiliar antes de retornar
    df_data = df_data.drop(columns=['Data datetime'])

    return df_data, df_fly_master_list


def update_csv_and_excel(data, csv_file=CSV_FILE, excel_file=EXCEL_FILE):
    """
    Atualiza o CSV com novos dados, gera/atualiza o Excel principal
    e cria um novo ficheiro Excel otimizado para o dashboard.
    """
    if not data:
        print("Nenhuma nova entrada para adicionar ao CSV/Excel.")
        return

    new_data_df = pd.DataFrame(data)

    if os.path.exists(csv_file):
        existing_data_df = pd.read_csv(csv_file)
        combined_df = pd.concat([existing_data_df, new_data_df]).drop_duplicates(subset=['Nome da imagem'], keep='last')
    else:
        combined_df = new_data_df

    # Recalcular acumulados e obter a lista mestre de moscas
    final_df, df_fly_master_list = recalculate_accumulated_counts(combined_df.copy())
    
    # 1. Salva o ficheiro de log completo (como antes)
    final_df.to_csv(csv_file, index=False)
    final_df.to_excel(excel_file, index=False, engine='openpyxl')
    print(f"CSV de log atualizado: {csv_file}")
    print(f"Excel de log gerado: {excel_file}")

    # Criar ou atualizar dashboard_data.xlsx com coluna de Data Execução
    dashboard_file = '/data/rafael/tese_public/dashboard_data.xlsx'
    current_execution_date = datetime.now().strftime("%Y-%m-%d")

    if not df_fly_master_list.empty:
        df_fly_master_list['Data Execução'] = current_execution_date

        if os.path.exists(dashboard_file):
            existing_dashboard_df = pd.read_excel(dashboard_file)
            combined_dashboard_df = pd.concat([existing_dashboard_df, df_fly_master_list], ignore_index=True)
            combined_dashboard_df = combined_dashboard_df.drop_duplicates(subset=['Fly_ID', 'Class'], keep='first')
        else:
            combined_dashboard_df = df_fly_master_list
        
        combined_dashboard_df.to_excel(dashboard_file, index=False, engine='openpyxl')
        print(f"Fichiero dashboard atualizado: {dashboard_file}")
        print(f"    -> total de moscas registadas: {len(combined_dashboard_df)}")
    else:
        print(" Não há novas moscas para adicionar ao dashboard.")#

    # 2. Salva o novo ficheiro para o dashboard
    if not df_fly_master_list.empty:
        dashboard_file = '/data/rafael/tese_public/dashboard_data.xlsx'
        df_fly_master_list.to_excel(dashboard_file, index=False, engine='openpyxl')
        print(f"✅ Ficheiro para o dashboard gerado com sucesso: {dashboard_file}")
        print(f"   -> Este ficheiro contém {len(df_fly_master_list)} moscas únicas registadas.")
    else:
        print("⚠️ Não foi possível gerar o ficheiro do dashboard (nenhuma mosca processada).")
#__


# --- Função Principal de Processamento YOLO ---

def process_images_with_yolo(model_path, images, processed_images, df_antigo, placa_id, localizacao, latitude, longitude, confidence_threshold=CONFIDENCE_THRESHOLD):
    """
    Processa uma lista de imagens com o modelo YOLO, rastreia moscas
    e atualiza o registro no CSV.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results_to_add_to_csv = [] # Lista para as novas linhas que serão adicionadas ao CSV

    model = YOLO(model_path)

    # Preparar o histórico de moscas para comparação.
    # Este dicionário armazenará a última posição conhecida de cada ID de mosca único.
    historic_flies_data = {
        'femea': {}, # {fly_id: {'center_x': x, 'center_y': y}}
        'macho': {},
        'mosca': {}
    }

    if not df_antigo.empty:
        # Percorre o DataFrame histórico para popular historic_flies_data
        for index, row in df_antigo.iterrows():
            for class_type in ['femea', 'macho', 'mosca']:
                coords_with_ids = row.get(f'Coord. {class_type}')
                if pd.notna(coords_with_ids) and coords_with_ids:
                    for entry in str(coords_with_ids).split('; '):
                        if ':' in entry:
                            fly_id, coords_str = entry.split(':', 1)
                            try:
                                x_min, y_min, x_max, y_max = map(int, coords_str.split(','))
                                center_x = (x_min + x_max) / 2
                                center_y = (y_min + y_max) / 2
                                historic_flies_data[class_type][fly_id] = {'center_x': center_x, 'center_y': center_y}
                            except ValueError as e:
                                print(f"Erro ao processar coordenadas históricas '{coords_str}': {e}")


    new_images_processed_flag = False

    for img in images:
        image_name = img['name']
        if image_name in processed_images:
            print(f"Imagem {image_name} já processada. Pulando.")
            continue

        img_path = img['path']
        image_date_full = img['date'] # Ex: '2024-07-29T10:00:00.000Z'
        
        new_images_processed_flag = True

        detections_for_current_image = {'femea': [], 'macho': [], 'mosca': []} # IDs e Coords para esta imagem
        confidences_for_current_image = {'femea': [], 'macho': [], 'mosca': []}
        new_flies_count_for_image = {'femea': 0, 'macho': 0, 'mosca': 0} # Contagem de *novas* moscas para esta linha do CSV

        class_map = {0: 'femea', 1: 'macho', 2: 'mosca'}

        # Iterar sobre cada classe para detecção
        for class_id in [0, 1, 2]:
            class_name = class_map[class_id]
            # Usar verbose=False para reduzir a saída do YOLO
            results_yolo = model.predict(source=img_path, conf=confidence_threshold, classes=[class_id], verbose=False)

            for result in results_yolo:
                # Anota a imagem e salva (isso pode ser feito uma vez por imagem, não por classe)
                # Mas para manter o seu comportamento original de salvar por classe, mantemos aqui.
                annotated_frame = result.plot()
                output_path = os.path.join(OUTPUT_DIR, f"{image_name}_det_{class_name}.jpg")
                cv2.imwrite(output_path, annotated_frame)

                for box in result.boxes:
                    confidence = float(box.conf[0])
                    x_min, y_min, x_max, y_max = map(int, box.xyxy[0])
                    current_center_x = (x_min + x_max) / 2
                    current_center_y = (y_min + y_max) / 2
                    current_box_coords_str = f"{x_min},{y_min},{x_max},{y_max}"

                    is_new_fly_to_system = True
                    matched_fly_id = None

                    # Tentar encontrar uma mosca correspondente no histórico para esta classe
                    for historic_fly_id, historic_pos in historic_flies_data[class_name].items():
                        historic_center_x = historic_pos['center_x']
                        historic_center_y = historic_pos['center_y']

                        distance = euclidean((current_center_x, current_center_y), (historic_center_x, historic_center_y))

                        if distance < DISTANCE_THRESHOLD:
                            is_new_fly_to_system = False
                            matched_fly_id = historic_fly_id
                            # Atualiza a posição no histórico com a detecção mais recente
                            historic_flies_data[class_name][historic_fly_id] = {'center_x': current_center_x, 'center_y': current_center_y}
                            break # Encontrou uma correspondência, não precisa verificar mais

                    if is_new_fly_to_system:
                        # Gerar um novo ID para esta mosca, pois ela é "nova" para o sistema
                        new_fly_id = str(uuid.uuid4())
                        detections_for_current_image[class_name].append(f"{new_fly_id}:{current_box_coords_str}")
                        confidences_for_current_image[class_name].append(f"{confidence:.2f}")
                        new_flies_count_for_image[class_name] += 1 # Conta como nova
                        
                        # Adiciona a nova mosca ao histórico em memória para futuras comparações
                        historic_flies_data[class_name][new_fly_id] = {'center_x': current_center_x, 'center_y': current_center_y}
                    else:
                        # É uma mosca já conhecida, apenas registra sua detecção para esta imagem
                        detections_for_current_image[class_name].append(f"{matched_fly_id}:{current_box_coords_str}")
                        confidences_for_current_image[class_name].append(f"{confidence:.2f}")

      # Preparar a linha de dados para esta imagem
        row = {
            'Nome da imagem': image_name,
            'Data imagem': image_date_full,
            'Placa ID': placa_id,
            'Localização': localizacao,
            'Latitude': latitude,
            'Longitude': longitude,
            'Nº femea': new_flies_count_for_image['femea'], # Contagem de NOVAS moscas
            'Nº macho': new_flies_count_for_image['macho'],
            'Nº mosca': new_flies_count_for_image['mosca'],
            'Coord. femea': '; '.join(detections_for_current_image['femea']),
            'Coord. macho': '; '.join(detections_for_current_image['macho']),
            'Coord. mosca': '; '.join(detections_for_current_image['mosca']),
            'Conf. femea': '; '.join(confidences_for_current_image['femea']),
            'Conf. macho': '; '.join(confidences_for_current_image['macho']),
            'Conf. mosca': '; '.join(confidences_for_current_image['mosca']),
            # Acumulados são placeholders, serão preenchidos depois
            'Acum. semanal femea': 0, 'Acum. mensal femea': 0, 'Acum. placa femea': 0,
            'Acum. semanal macho': 0, 'Acum. mensal macho': 0, 'Acum. placa macho': 0,
            'Acum. semanal mosca': 0, 'Acum. mensal mosca': 0, 'Acum. placa mosca': 0,
        }
        results_to_add_to_csv.append(row)

    if new_images_processed_flag:
    # Adiciona os novos resultados e recalcula tudo de forma abrangente
        update_csv_and_excel(results_to_add_to_csv)
    else:
        print("Nenhuma imagem nova para processar nesta execução.")



# --- Fluxo Principal ---

def main():
    drive_service = authenticate_drive()
    processed_images, df_antigo = get_processed_data()

    placas_ativas = get_placas_ativas_info()
    for placa_id, localidade, latitude, longitude, nome_armadilha in placas_ativas:
        FOLDER_ID = FOLDER_IDS.get(nome_armadilha)
        if not FOLDER_ID:
            print(f"⚠️ Armadilha '{nome_armadilha}' não tem pasta atribuída no FOLDER_IDS.")
            continue

        query = f"'{FOLDER_ID}' in parents and mimeType contains 'image/'"
        try:
            results_drive = drive_service.files().list(q=query, pageSize=1000, fields="files(id, name, modifiedTime)").execute()
            files_on_drive = results_drive.get('files', [])
        except Exception as e:
            print(f"Erro ao listar arquivos do Google Drive para a armadilha '{nome_armadilha}': {e}")
            continue

        if not files_on_drive:
            print(f"📁 Nenhuma imagem encontrada no Google Drive para armadilha: {nome_armadilha}")
            continue

        # Cria uma subpasta para cada armadilha dentro de 'downloaded_images'
        nome_folder = nome_armadilha.strip().replace(" ", "_").lower()
        download_folder_path = os.path.join('downloaded_images', nome_folder)
        images_to_download = download_images(drive_service, files_on_drive, folder=download_folder_path)

        # Processa as imagens baixadas
        process_images_with_yolo('best.pt', images_to_download, processed_images, df_antigo, placa_id, localidade, latitude, longitude)

if __name__ == "__main__":
    main()