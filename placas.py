import os
import sqlite3
from datetime import datetime

DB_DIR = "db"
DB_PATH = os.path.join(DB_DIR, "placas.db")


def inicializar_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS armadilhas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            localidade TEXT,
            latitude REAL,
            longitude REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa_id TEXT UNIQUE NOT NULL,
            id_armadilha INTEGER NOT NULL,
            data_colocacao TEXT,
            ativa INTEGER,
            FOREIGN KEY (id_armadilha) REFERENCES armadilhas(id)
        )
    """)

    conn.commit()
    conn.close()


def listar_armadilhas():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, localidade, latitude, longitude FROM armadilhas")
    armadilhas = cursor.fetchall()
    conn.close()

    if not armadilhas:
        print("\n⚠️ Nenhuma armadilha cadastrada.")
        return []

    print("\n🔎 Armadilhas registadas:")
    for a in armadilhas:
        print(f"ID: {a[0]} | Nome: {a[1]} | Localidade: {a[2]} | Coordenadas: ({a[3]}, {a[4]})")
    return armadilhas


def adicionar_armadilha():
    print("\n📍 Nova Armadilha:")
    nome = input("Nome da armadilha: ")
    localidade = input("Localidade: ")
    latitude = input("Latitude: ")
    longitude = input("Longitude: ")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO armadilhas (nome, localidade, latitude, longitude)
        VALUES (?, ?, ?, ?)
    """, (nome, localidade, latitude, longitude))
    id_arma = cursor.lastrowid

    nova_placa_id = f"PLACA_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        INSERT INTO placas (placa_id, id_armadilha, data_colocacao, ativa)
        VALUES (?, ?, ?, 1)
    """, (nova_placa_id, id_arma, data))

    conn.commit()
    conn.close()
    print("✅ Armadilha adicionada com sucesso!")


def trocar_placa():
    armadilhas = listar_armadilhas()
    if not armadilhas:
        return

    try:
        id_arma = int(input("\nDigite o ID da armadilha para trocar a placa: "))
    except ValueError:
        print("❌ ID inválido.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE placas SET ativa = 0
        WHERE id_armadilha = ? AND ativa = 1
    """, (id_arma,))

    nova_placa_id = f"PLACA_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        INSERT INTO placas (placa_id, id_armadilha, data_colocacao, ativa)
        VALUES (?, ?, ?, 1)
    """, (nova_placa_id, id_arma, data))

    conn.commit()
    conn.close()
    print(f"🔄 Placa trocada com sucesso. Novo ID: {nova_placa_id}")

    with open("placa_id.txt", "w") as f:
        f.write(nova_placa_id)


def remover_armadilha():
    armadilhas = listar_armadilhas()
    if not armadilhas:
        return

    try:
        id_arma = int(input("\nDigite o ID da armadilha a remover: "))
    except ValueError:
        print("❌ ID inválido.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM placas WHERE id_armadilha = ?", (id_arma,))
    cursor.execute("DELETE FROM armadilhas WHERE id = ?", (id_arma,))
    conn.commit()
    conn.close()
    print("🗑️ Armadilha removida com sucesso!")


def obter_info_placa_atual():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.placa_id, a.nome, a.localidade, a.latitude, a.longitude
        FROM placas p
        JOIN armadilhas a ON p.id_armadilha = a.id
        WHERE p.ativa = 1
        ORDER BY p.data_colocacao DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row if row else None


def menu():
    inicializar_db()
    while True:
        print("\n📋 MENU DE GESTÃO DE ARMADILHAS")
        print("1 - Ver armadilhas registadas")
        print("2 - Registar nova armadilha")
        print("3 - Trocar placa ativa")
        print("4 - Remover armadilha")
        print("5 - Sair")
        opcao = input("Escolha uma opção: ")

        if opcao == "1":
            listar_armadilhas()
        elif opcao == "2":
            adicionar_armadilha()
        elif opcao == "3":
            trocar_placa()
        elif opcao == "4":
            remover_armadilha()
        elif opcao == "5":
            print("👋 A sair do programa...")
            break
        else:
            print("❌ Opção inválida.")


if __name__ == "__main__":
    menu()