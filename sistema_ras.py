import streamlit as st
import sqlite3
import pandas as pd
import time
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

# ================= CONFIG =================
st.set_page_config(page_title="Sistema RAS V7", layout="wide")
TZ = ZoneInfo("America/Sao_Paulo")

# ================= HASH =================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# ================= SESSION =================
if 'logado' not in st.session_state:
    st.session_state.update({
        'logado': False,
        'usuario_id': None,
        'tipo_usuario': None,
        'primeiro_acesso': False,
        'nome_usuario': ""
    })

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ================= DATABASE =================
def get_connection():
    return sqlite3.connect('ras_database_v7.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS agentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matricula TEXT UNIQUE,
        nome TEXT,
        graduacao TEXT,
        lotacao TEXT,
        senha TEXT,
        primeiro_acesso INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS administradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE,
        senha TEXT,
        primeiro_acesso INTEGER DEFAULT 1
    )''')

    # VAGAS COM DATA_LIBERACAO
    c.execute('''CREATE TABLE IF NOT EXISTS vagas_ras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento TEXT,
        data_inicio DATE,
        hora_inicio TIME,
        hora_fim TIME,
        vagas_totais INTEGER,
        valor REAL,
        data_liberacao TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS inscricoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_vaga INTEGER,
        id_agente INTEGER,
        status TEXT DEFAULT 'ATIVO',
        data_inscricao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    try:
        senha_hash = make_hashes('admin123')
        c.execute("INSERT INTO administradores (usuario, senha) VALUES (?, ?)",
                  ('admin', senha_hash))
    except:
        pass

    conn.commit()
    conn.close()

init_db()

# ================= FUNÇÕES =================

def criar_vaga(evento, data, hi, hf, qtd, valor, data_liberacao):
    conn = get_connection()
    conn.execute("""
        INSERT INTO vagas_ras
        (evento, data_inicio, hora_inicio, hora_fim, vagas_totais, valor, data_liberacao)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (evento, data, str(hi), str(hf), qtd, valor, data_liberacao.isoformat()))
    conn.commit()
    conn.close()

def inscrever_ras(id_agente, id_vaga):
    conn = get_connection()

    vaga = conn.execute("SELECT vagas_totais, data_liberacao FROM vagas_ras WHERE id=?",
                        (id_vaga,)).fetchone()

    agora = datetime.now(TZ)
    liberacao = datetime.fromisoformat(vaga[1])

    if liberacao.tzinfo is None:
        liberacao = liberacao.replace(tzinfo=TZ)

    if agora < liberacao:
        conn.close()
        return False, "Inscrições ainda não liberadas."

    ativos = conn.execute("""
        SELECT COUNT(*) FROM inscricoes
        WHERE id_vaga=? AND status='ATIVO'
    """, (id_vaga,)).fetchone()[0]

    if ativos < vaga[0]:
        status = 'ATIVO'
        msg = "Inscrição confirmada!"
    else:
        status = 'ESPERA'
        msg = "Entrou na lista de espera."

    conn.execute("""
        INSERT INTO inscricoes (id_vaga, id_agente, status)
        VALUES (?, ?, ?)
    """, (id_vaga, id_agente, status))

    conn.commit()
    conn.close()

    return True, msg

# ================= LOGIN SIMPLIFICADO =================

if not st.session_state['logado']:
    st.title("👮‍♂️ S.G.R.A.S V7")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        conn = get_connection()
        user = conn.execute("SELECT id, senha FROM administradores WHERE usuario=?",
                            (usuario,)).fetchone()
        conn.close()

        if user and check_hashes(senha, user[1]):
            st.session_state['logado'] = True
            st.session_state['tipo_usuario'] = 'admin'
            st.session_state['usuario_id'] = user[0]
            st.rerun()
        else:
            st.error("Login inválido")

# ================= SISTEMA =================
else:
    if st.sidebar.button("Logout"):
        logout()

    menu = st.sidebar.radio("Menu", ["Criar Escala", "Área do Agente"])

    # ================= ADMIN =================
    if menu == "Criar Escala":
        st.header("Nova Escala RAS")

        evento = st.text_input("Evento")
        dt = st.date_input("Data do Serviço")
        hi = st.time_input("Hora Início")
        hf = st.time_input("Hora Fim")
        qtd = st.number_input("Vagas", 1, 100, 10)
        valor = st.number_input("Valor", 0.0, 1000.0, 200.0)

        st.markdown("### ⏳ Liberação da Inscrição")
        data_lib = st.date_input("Data de Liberação")
        hora_lib = st.time_input("Hora de Liberação")

        if st.button("Publicar"):
            data_liberacao = datetime.combine(data_lib, hora_lib).replace(tzinfo=TZ)
            criar_vaga(evento, dt, hi, hf, qtd, valor, data_liberacao)
            st.success("Escala criada com liberação programada!")

    # ================= AGENTE =================
    if menu == "Área do Agente":
        st.header("Vagas Disponíveis")

        conn = get_connection()
        vagas = pd.read_sql("SELECT * FROM vagas_ras ORDER BY data_inicio", conn)
        conn.close()

        if vagas.empty:
            st.info("Sem vagas disponíveis.")

        for _, row in vagas.iterrows():

            liberacao = datetime.fromisoformat(row['data_liberacao'])
            if liberacao.tzinfo is None:
                liberacao = liberacao.replace(tzinfo=TZ)

            agora = datetime.now(TZ)

            with st.container(border=True):

                st.subheader(row['evento'])
                st.write(f"📅 {row['data_inicio']} | 🕒 {row['hora_inicio']} - {row['hora_fim']}")
                st.write(f"💰 R$ {row['valor']:.2f}")

                if agora < liberacao:

                    placeholder = st.empty()
                    segundos = int((liberacao - agora).total_seconds())

                    dias = segundos // 86400
                    horas = (segundos % 86400) // 3600
                    minutos = (segundos % 3600) // 60
                    seg = segundos % 60

                    placeholder.markdown(
                        f"## 🔒 Liberação em: ⏳ {dias}d {horas}h {minutos}m {seg}s"
                    )

                    st.button("Aguardando Liberação", disabled=True)

                else:
                    if st.button("Inscrever", key=f"vaga_{row['id']}"):
                        ok, msg = inscrever_ras(1, row['id'])
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)