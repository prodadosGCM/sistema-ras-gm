import streamlit as st
import sqlite3
import pandas as pd
import time
import hashlib

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema RAS", layout="wide")

# --- FUNÇÕES DE SEGURANÇA (HASH) ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

# --- GERENCIAMENTO DE SESSÃO ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['usuario_id'] = None
    st.session_state['tipo_usuario'] = None 
    st.session_state['primeiro_acesso'] = False
    st.session_state['nome_usuario'] = ""

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- BANCO DE DADOS (V6 - COM TABELA DE CARGOS) ---
def get_connection():
    # V6 garante o reset total e nova estrutura
    return sqlite3.connect('ras_database_v6.db')

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Tabela Agentes
    c.execute('''CREATE TABLE IF NOT EXISTS agentes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE,
                    nome TEXT,
                    graduacao TEXT,
                    lotacao TEXT,
                    senha TEXT,
                    primeiro_acesso INTEGER DEFAULT 0
                )''')
    
    # 2. Tabela Admin
    c.execute('''CREATE TABLE IF NOT EXISTS administradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE,
                    senha TEXT,
                    primeiro_acesso INTEGER DEFAULT 1
                )''')
    
    # 3. Tabela Vagas
    c.execute('''CREATE TABLE IF NOT EXISTS vagas_ras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evento TEXT,
                    data_inicio DATE,
                    hora_inicio TIME,
                    hora_fim TIME,
                    vagas_totais INTEGER,
                    valor REAL
                )''')
    
    # 4. Tabela Inscrições
    c.execute('''CREATE TABLE IF NOT EXISTS inscricoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_vaga INTEGER,
                    id_agente INTEGER,
                    status TEXT DEFAULT 'ATIVO',
                    data_inscricao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(id_vaga) REFERENCES vagas_ras(id),
                    FOREIGN KEY(id_agente) REFERENCES agentes(id)
                )''')

    # 5. NOVA TABELA: Cargos
    c.execute('''CREATE TABLE IF NOT EXISTS cargos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT UNIQUE
                )''')

    # Popula cargos padrão se a tabela estiver vazia
    c.execute("SELECT count(*) FROM cargos")
    if c.fetchone()[0] == 0:
        cargos_padrao = ["Guarda Municipal", "Subinspetor", "Inspetor", "Soldado", "Cabo", "Sargento", "Subtenente", "Tenente", "Capitão", "Major"]
        for cargo in cargos_padrao:
            try:
                c.execute("INSERT INTO cargos (nome) VALUES (?)", (cargo,))
            except: pass

    # Cria Admin Padrão (admin / admin123)
    try:
        senha_hash = make_hashes('admin123')
        c.execute("INSERT INTO administradores (usuario, senha, primeiro_acesso) VALUES (?, ?, ?)", 
                  ('admin', senha_hash, 1))
    except sqlite3.IntegrityError:
        pass 
        
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES DE LÓGICA ---

def get_lista_cargos():
    conn = get_connection()
    df = pd.read_sql("SELECT nome FROM cargos ORDER BY nome", conn)
    conn.close()
    return df['nome'].tolist()

def adicionar_cargo(novo_cargo):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO cargos (nome) VALUES (?)", (novo_cargo,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def remover_cargo(cargo_nome):
    conn = get_connection()
    conn.execute("DELETE FROM cargos WHERE nome = ?", (cargo_nome,))
    conn.commit()
    conn.close()

def login_admin(usuario, senha):
    conn = get_connection()
    user = conn.execute("SELECT id, senha, primeiro_acesso FROM administradores WHERE usuario = ?", (usuario,)).fetchone()
    conn.close()
    if user and check_hashes(senha, user[1]):
        return True, user[0], user[2]
    return False, None, None

def login_agente(matricula, senha):
    conn = get_connection()
    user = conn.execute("SELECT id, nome, senha, primeiro_acesso FROM agentes WHERE matricula = ?", (matricula,)).fetchone()
    conn.close()
    if user and check_hashes(senha, user[2]):
        return True, user[0], user[1], user[3]
    return False, None, None, None

def cadastrar_agente_self(matricula, nome, graduacao, lotacao, senha):
    conn = get_connection()
    try:
        senha_cripto = make_hashes(senha)
        conn.execute("INSERT INTO agentes (matricula, nome, graduacao, lotacao, senha, primeiro_acesso) VALUES (?, ?, ?, ?, ?, 0)", 
                     (matricula, nome, graduacao, lotacao, senha_cripto))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def alterar_senha(tipo_usuario, id_usuario, nova_senha):
    conn = get_connection()
    nova_senha_hash = make_hashes(nova_senha)
    tabela = "administradores" if tipo_usuario == 'admin' else "agentes"
    conn.execute(f"UPDATE {tabela} SET senha = ?, primeiro_acesso = 0 WHERE id = ?", (nova_senha_hash, id_usuario))
    conn.commit()
    conn.close()

def criar_vaga(evento, data, h_inicio, h_fim, qtd, valor):
    conn = get_connection()
    conn.execute("INSERT INTO vagas_ras (evento, data_inicio, hora_inicio, hora_fim, vagas_totais, valor) VALUES (?, ?, ?, ?, ?, ?)",
                 (evento, data, str(h_inicio), str(h_fim), qtd, valor))
    conn.commit()
    conn.close()

def inscrever_ras(id_agente, id_vaga):
    conn = get_connection()

    # Verifica se já existe inscrição
    check = conn.execute("""
        SELECT status FROM inscricoes 
        WHERE id_agente = ? AND id_vaga = ?
    """, (id_agente, id_vaga)).fetchone()

    if check:
        conn.close()
        return False, "Você já está inscrito nesta escala."

    vagas_totais = conn.execute(
        "SELECT vagas_totais FROM vagas_ras WHERE id = ?", 
        (id_vaga,)
    ).fetchone()[0]

    ativos = conn.execute("""
        SELECT COUNT(*) FROM inscricoes 
        WHERE id_vaga = ? AND status = 'ATIVO'
    """, (id_vaga,)).fetchone()[0]

    if ativos < vagas_totais:
        status = 'ATIVO'
        msg = "Inscrição confirmada!"
    else:
        status = 'ESPERA'
        msg = "Vagas esgotadas. Você entrou na lista de espera."

    conn.execute("""
        INSERT INTO inscricoes (id_vaga, id_agente, status)
        VALUES (?, ?, ?)
    """, (id_vaga, id_agente, status))

    conn.commit()
    conn.close()

    return True, msg


def solicitar_desistencia(id_inscricao):
    conn = get_connection()
    conn.execute("UPDATE inscricoes SET status = 'PENDENTE_SAIDA' WHERE id = ?", (id_inscricao,))
    conn.commit()
    conn.close()

def cancelar_desistencia(id_inscricao):
    conn = get_connection()
    conn.execute("UPDATE inscricoes SET status = 'ATIVO' WHERE id = ?", (id_inscricao,))
    conn.commit()
    conn.close()

def admin_processar_desistencia(id_inscricao, aprovado):
    conn = get_connection()

    # Descobre qual vaga foi liberada
    vaga_id = conn.execute(
        "SELECT id_vaga FROM inscricoes WHERE id = ?", 
        (id_inscricao,)
    ).fetchone()[0]

    if aprovado:
        conn.execute("DELETE FROM inscricoes WHERE id = ?", (id_inscricao,))

        # Puxa o primeiro da lista de espera
        espera = conn.execute("""
            SELECT id FROM inscricoes
            WHERE id_vaga = ? AND status = 'ESPERA'
            ORDER BY data_inscricao ASC
            LIMIT 1
        """, (vaga_id,)).fetchone()

        if espera:
            conn.execute("""
                UPDATE inscricoes 
                SET status = 'ATIVO'
                WHERE id = ?
            """, (espera[0],))

    else:
        conn.execute("""
            UPDATE inscricoes 
            SET status = 'ATIVO'
            WHERE id = ?
        """, (id_inscricao,))

    conn.commit()
    conn.close()


# ================= TELA DE LOGIN / CADASTRO =================
if not st.session_state['logado']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("👮‍♂️ S.G.R.A.S")
        st.caption("Sistema Seguro (V6) - Base Zerada")
        
        tab_login, tab_cadastro = st.tabs(["🔑 Login", "📝 Cadastro de Agente"])
        
        with tab_login:
            tipo = st.radio("Entrar como:", ["Agente", "Administrador"], horizontal=True)
            
            if tipo == "Administrador":
                usuario_input = st.text_input("Usuário do Admin")
            else:
                usuario_input = st.text_input("Sua Matrícula (Número)")
            
            senha_input = st.text_input("Senha", type="password")
            
            if st.button("Entrar"):
                if tipo == "Administrador":
                    sucesso, uid, p_acesso = login_admin(usuario_input, senha_input)
                    if sucesso:
                        st.session_state['logado'] = True
                        st.session_state['tipo_usuario'] = 'admin'
                        st.session_state['usuario_id'] = uid
                        st.session_state['primeiro_acesso'] = bool(p_acesso)
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos")
                
                else: 
                    sucesso, uid, nome, p_acesso = login_agente(usuario_input, senha_input)
                    if sucesso:
                        st.session_state['logado'] = True
                        st.session_state['tipo_usuario'] = 'agente'
                        st.session_state['usuario_id'] = uid
                        st.session_state['nome_usuario'] = nome
                        st.session_state['primeiro_acesso'] = bool(p_acesso)
                        st.rerun()
                    else:
                        st.error("Matrícula ou senha incorretos")

        with tab_cadastro:
            st.write("Crie sua conta para acessar as escalas.")
            new_mat = st.text_input("Sua Matrícula")
            new_nome = st.text_input("Nome Completo")
            c1, c2 = st.columns(2)
            
            # --- CARGOS DINÂMICOS NA TELA DE CADASTRO ---
            lista_cargos = get_lista_cargos()
            new_grad = c1.selectbox("Graduação", lista_cargos)
            # --------------------------------------------
            
            new_lot = c2.text_input("Lotação")
            new_pass = st.text_input("Crie uma Senha", type="password")
            new_pass_conf = st.text_input("Confirme a Senha", type="password")
            
            if st.button("Criar Conta"):
                if new_pass != new_pass_conf:
                    st.error("As senhas não coincidem.")
                elif new_mat and new_pass and new_nome:
                    if cadastrar_agente_self(new_mat, new_nome, new_grad, new_lot, new_pass):
                        st.success("Conta criada! Redirecionando...")
                        time.sleep(2) 
                        st.rerun()
                    else:
                        st.error("Matrícula já cadastrada.")
                else:
                    st.warning("Preencha todos os campos obrigatórios.")

# ================= SISTEMA LOGADO =================
else:
    if st.session_state['primeiro_acesso']:
        st.warning("⚠️ Atenção: Por segurança, altere sua senha inicial agora.")
        with st.form("form_troca_senha"):
            nova_s1 = st.text_input("Nova Senha", type="password")
            nova_s2 = st.text_input("Confirme", type="password")
            if st.form_submit_button("Atualizar Senha"):
                if nova_s1 == nova_s2 and len(nova_s1) > 3:
                    alterar_senha(st.session_state['tipo_usuario'], st.session_state['usuario_id'], nova_s1)
                    st.session_state['primeiro_acesso'] = False
                    st.success("Sucesso!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Erro na senha.")
        st.stop() 

    sidebar = st.sidebar
    nome_display = st.session_state.get('nome_usuario', 'Admin')
    if not nome_display: nome_display = "Usuário"
    sidebar.write(f"Usuário: **{nome_display}**")
    if sidebar.button("Sair / Logout"):
        logout()
    st.sidebar.markdown("---")
    
    # === VISÃO DO ADMINISTRADOR ===
    if st.session_state['tipo_usuario'] == 'admin':
        st.header("Painel de Comando")
        
        # --- NOTIFICAÇÕES ---
        conn = get_connection()
        try:
            pedidos_saida = pd.read_sql('''
                SELECT i.id, a.nome, a.matricula, v.evento, v.data_inicio 
                FROM inscricoes i
                JOIN agentes a ON i.id_agente = a.id
                JOIN vagas_ras v ON i.id_vaga = v.id
                WHERE i.status = 'PENDENTE_SAIDA'
            ''', conn)
        except:
            pedidos_saida = pd.DataFrame()
        conn.close()
        
        if not pedidos_saida.empty:
            st.warning(f"🔔 Há {len(pedidos_saida)} desistências pendentes!")
            with st.expander("Ver Solicitações", expanded=True):
                for idx, row in pedidos_saida.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"**{row['nome']}** quer sair de **{row['evento']}**")
                    if c2.button("✅ Aprovar", key=f"apr_{row['id']}"):
                        admin_processar_desistencia(row['id'], True)
                        st.rerun()
                    if c3.button("❌ Negar", key=f"neg_{row['id']}"):
                        admin_processar_desistencia(row['id'], False)
                        st.rerun()
            st.markdown("---")

        op = st.sidebar.radio("Menu", ["📊 Relatórios Gerenciais", "Criar Escalas", "Lista de Inscrições", "Gerenciar Agentes", "⚙️ Configurações (Cargos)"])
        
        if op == "📊 Relatórios Gerenciais":
            st.subheader("Dashboard de Inteligência")
            conn = get_connection()
            df_inscricoes = pd.read_sql("""
                SELECT v.evento, v.valor, a.nome, i.status 
                FROM inscricoes i
                JOIN vagas_ras v ON i.id_vaga = v.id
                JOIN agentes a ON i.id_agente = a.id
                WHERE i.status = 'ATIVO'
            """, conn)
            conn.close()
            
            c1, c2 = st.columns(2)
            c1.metric("Escalas Confirmadas", len(df_inscricoes))
            c2.metric("Valor Total Previsto", f"R$ {df_inscricoes['valor'].sum():,.2f}" if not df_inscricoes.empty else "R$ 0,00")
            
            st.markdown("---")
            if not df_inscricoes.empty:
                st.bar_chart(df_inscricoes['nome'].value_counts().head(5))
            else:
                st.info("Sem dados suficientes para gráficos.")

        elif op == "Criar Escalas":
            st.subheader("Nova Escala RAS")
            evt = st.text_input("Nome do Evento")
            c1, c2, c3 = st.columns(3)
            dt = c1.date_input("Data")
            hi = c2.time_input("Início")
            hf = c3.time_input("Fim")
            c4, c5 = st.columns(2)
            qtd = c4.number_input("Vagas", 1, 100, 10)
            val = c5.number_input("Valor (R$)", 0.0, 1000.0, 200.0)
            if st.button("Publicar"):
                criar_vaga(evt, dt, hi, hf, qtd, val)
                st.success("Escala Criada!")
                
        elif op == "Lista de Inscrições":
            st.subheader("📋 Inscrições Realizadas")
            conn = get_connection()
            try:
                df = pd.read_sql('''
                    SELECT v.evento, v.data_inicio, a.nome, a.matricula, i.status 
                    FROM inscricoes i 
                    JOIN vagas_ras v ON i.id_vaga = v.id 
                    JOIN agentes a ON i.id_agente = a.id
                    ORDER BY v.data_inicio DESC
                ''', conn)
            except: df = pd.DataFrame()
            conn.close()
            
            col_f1, col_f2 = st.columns(2)
            with col_f1: filtro_evento = st.text_input("🔍 Evento")
            with col_f2: filtro_agente = st.text_input("👮 Agente")
            
            if not df.empty:
                if filtro_evento: df = df[df['evento'].str.contains(filtro_evento, case=False, na=False)]
                if filtro_agente: df = df[df['nome'].str.contains(filtro_agente, case=False, na=False) | df['matricula'].str.contains(filtro_agente, case=False, na=False)]
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Nada encontrado.")

        elif op == "Gerenciar Agentes":
            st.subheader("👮‍♂️ Gestão de Efetivo")
            conn = get_connection()
            df_agentes = pd.read_sql("SELECT id, matricula, nome, graduacao, lotacao FROM agentes", conn).fillna('')
            conn.close()
            
            if not df_agentes.empty:
                escolha = st.selectbox("Selecione:", df_agentes['matricula'] + " - " + df_agentes['nome'])
                id_agente_sel = int(df_agentes[df_agentes['matricula'] == escolha.split(" - ")[0]].iloc[0]['id'])
                
                # Pega dados atualizados
                conn = get_connection()
                agente_dados = pd.read_sql(f"SELECT * FROM agentes WHERE id={id_agente_sel}", conn).iloc[0]
                conn.close()

                with st.container(border=True):
                    with st.form("edit_user"):
                        nn = st.text_input("Nome", value=agente_dados['nome'])
                        
                        # --- CARGOS DINÂMICOS NA EDIÇÃO ---
                        lista_cargos = get_lista_cargos()
                        grad_atual = agente_dados['graduacao'] if agente_dados['graduacao'] in lista_cargos else lista_cargos[0]
                        ng = st.selectbox("Graduação", lista_cargos, index=lista_cargos.index(grad_atual))
                        # ----------------------------------
                        
                        nl = st.text_input("Lotação", value=agente_dados['lotacao'])
                        if st.form_submit_button("Salvar Alterações"):
                            conn = get_connection()
                            conn.execute("UPDATE agentes SET nome=?, graduacao=?, lotacao=? WHERE id=?", (nn, ng, nl, id_agente_sel))
                            conn.commit()
                            conn.close()
                            st.success("Salvo!")
                            time.sleep(1)
                            st.rerun()
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Resetar Senha (1234)"):
                        conn = get_connection()
                        hash_1234 = make_hashes('1234')
                        conn.execute("UPDATE agentes SET senha=?, primeiro_acesso=1 WHERE id=?", (hash_1234, id_agente_sel))
                        conn.commit()
                        conn.close()
                        st.success("Senha resetada.")
                    
                    if c2.button("Excluir Agente", type="primary"):
                        conn = get_connection()
                        conn.execute("DELETE FROM inscricoes WHERE id_agente=?", (id_agente_sel,))
                        conn.execute("DELETE FROM agentes WHERE id=?", (id_agente_sel,))
                        conn.commit()
                        conn.close()
                        st.rerun()

        # --- NOVA ABA: CONFIGURAÇÃO DE CARGOS ---
        elif op == "⚙️ Configurações (Cargos)":
            st.subheader("Gerenciar Cargos e Patentes")
            st.info("Aqui você define quais graduações aparecem no cadastro.")
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("##### Adicionar Novo Cargo")
                novo_cargo = st.text_input("Nome do Cargo (Ex: Coronel)")
                if st.button("Adicionar Cargo"):
                    if novo_cargo:
                        if adicionar_cargo(novo_cargo):
                            st.success(f"Cargo '{novo_cargo}' adicionado!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Erro: Esse cargo já existe.")
            
            with c2:
                st.markdown("##### Lista de Cargos Ativos")
                lista = get_lista_cargos()
                for cargo in lista:
                    col_a, col_b = st.columns([4, 1])
                    col_a.write(f"• {cargo}")
                    if col_b.button("🗑️", key=f"del_cargo_{cargo}"):
                        remover_cargo(cargo)
                        st.rerun()

    # === VISÃO DO AGENTE ===
    elif st.session_state['tipo_usuario'] == 'agente':
        nome_agente_logado = st.session_state.get('nome_usuario', 'Agente')
        st.header(f"Olá, {nome_agente_logado}")
        
        tab_vagas, tab_minhas = st.tabs(["📋 Vagas Disponíveis", "✅ Meus Agendamentos"])
        
        with tab_vagas:
            conn = get_connection()
            query = '''
            SELECT v.id, v.evento, v.data_inicio, v.hora_inicio, v.hora_fim, v.valor,
                   v.vagas_totais, COUNT(CASE WHEN i.status = 'ATIVO' THEN 1 END) AS inscritos
            FROM vagas_ras v
            LEFT JOIN inscricoes i ON v.id = i.id_vaga
            GROUP BY v.id
            ORDER BY v.data_inicio
            '''
            vagas_df = pd.read_sql(query, conn)
            
            if vagas_df.empty: st.info("Sem vagas no momento.")
            
            for index, row in vagas_df.iterrows():
                vagas_restantes = row['vagas_totais'] - row['inscritos']
                pct = row['inscritos'] / row['vagas_totais'] if row['vagas_totais'] > 0 else 0
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    with c1:
                        st.markdown(f"### {row['evento']}")
                        st.write(f"📅 {row['data_inicio']} | 🕒 {row['hora_inicio']} - {row['hora_fim']}")
                        st.write(f"💰 R$ {row['valor']:.2f}")
                    with c2:
                        st.write(f"Ocupação: {row['inscritos']}/{row['vagas_totais']}")
                        st.progress(pct)
                        if vagas_restantes <= 0: st.error("LOTADO")
                        elif vagas_restantes <= 5: st.warning("Últimas Vagas")
                        else: st.success("Disponível")
                    with c3:
                        st.write("")
                        st.write("")
                        btn_label = "Inscrever"
                        btn_help = None

                        if vagas_restantes <= 0:
                            btn_label = "Entrar na Lista de Espera"
                            btn_help = "Você será chamado caso alguém desista"

                        if st.button(btn_label, key=f"v_{row['id']}", use_container_width=True, help=btn_help):
                            ok, msg = inscrever_ras(st.session_state['usuario_id'], row['id'])
                            if ok:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)

            conn.close()
            
        with tab_minhas:
            st.subheader("Minhas Escalas")
            conn = get_connection()
            try:
                meus_ras = pd.read_sql(f'''
                    SELECT i.id as id_inscricao, v.evento, v.data_inicio, v.hora_inicio, v.hora_fim, i.status
                    FROM inscricoes i
                    JOIN vagas_ras v ON i.id_vaga = v.id
                    WHERE i.id_agente = {st.session_state['usuario_id']}
                    ORDER BY v.data_inicio
                ''', conn)
            except:
                 meus_ras = pd.DataFrame()

            conn.close()
            
            if meus_ras.empty:
                st.info("Você não tem agendamentos.")
            else:
                for idx, row in meus_ras.iterrows():
                    with st.container(border=True):
                        col_a, col_b = st.columns([4, 1])
                        col_a.write(f"**{row['evento']}** em {row['data_inicio']}")
                        
                        status_atual = row['status'] if 'status' in row else 'ATIVO'
                        
                        if status_atual == 'ATIVO':
                            col_a.success("Confirmado ✅")
                            if col_b.button("Solicitar Desistência", key=f"sair_{row['id_inscricao']}"):
                                solicitar_desistencia(row['id_inscricao'])
                                st.rerun()

                        elif status_atual == 'ESPERA':
                            col_a.info("🕒 Lista de Espera")        
                        
                        elif status_atual == 'PENDENTE_SAIDA':
                            col_a.warning("⏳ Aguardando Aprovação do Comando para sair")
                            if col_b.button("Cancelar Pedido", key=f"canc_sair_{row['id_inscricao']}"):
                                cancelar_desistencia(row['id_inscricao'])
                                st.rerun()
                        