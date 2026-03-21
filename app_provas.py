import streamlit as st
import sqlite3
import pandas as pd  # Resolvendo o erro do 'pd'
import os
import cv2
import numpy as np
import plotly.express as plex 
import random
import json
import qrcode
from datetime import datetime, timedelta

# 1. Seus módulos personalizados
from latex_utils import sanitizar_nome, escapar_latex, gerar_preview_web, configurar_jinja, compilar_latex_mac
from correcao import renderizar_aba_correcao
from sala import renderizar_aba_sala
from planejamento import renderizar_aba_fabrica
from turmas import renderizar_aba_turmas

# 2. O COMBO COMPLETO E REVISADO DO DB.PY (Agora com excluir_questao!)
from db import (
    baixar_banco_do_cofre, salvar_banco_no_cofre, criar_base_de_dados, 
    carregar_configuracoes, salvar_configuracoes, criar_backup_banco, 
    backup_para_icloud, obter_estatisticas_questoes, limpar_dados_teste, 
    inserir_questao, buscar_e_embaralhar_alternativas, buscar_alternativas_originais, 
    obter_assuntos_da_disciplina, buscar_questoes_filtradas, salvar_resultado_prova, 
    detectar_duplicata, buscar_questoes_proximas, excluir_questao
)

# 3. A PRIMEIRA linha de comando Streamlit (obrigatório ser a primeira)
st.set_page_config(page_title="Meu Estudei - FAM", page_icon="🎓", layout="wide")
def mostrar_tela_login():
    st.image("https://api.dicebear.com/9.x/shapes/svg?seed=MeuEstudei", width=100)
    st.title("🔐 Acesso Restrito - FAM")
    st.markdown("Bem-vindo ao sistema de gestão de provas e turmas da Profª Mariana.")

    usuarios_permitidos = {
        "mariana": "senha123",
        "junior": "fam2026",
        "samara": "fam2026",
        "Alfredo": "fam2026"
    }

    with st.form("login_form"):
        user = st.text_input("Usuário").lower().strip()
        pw = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar no Sistema", use_container_width=True):
            if user in usuarios_permitidos and usuarios_permitidos[user] == pw:
                st.session_state.usuario_logado = user
                
                with st.spinner("Buscando seus dados no cofre... ☁️"):
                    baixar_banco_do_cofre() # Puxa o seu arquivo .db
                    criar_base_de_dados()   # Garante que as tabelas estão lá
                st.rerun()
            else:
                st.error("⚠️ Usuário ou senha incorretos.")
if "usuario_logado" not in st.session_state:
    mostrar_tela_login() # <--- Aqui tem 1 TAB de espaço
    st.stop()            # <--- Aqui também tem 1 TAB                

# =========================================================================
# SE CHEGOU AQUI, O PROFESSOR ESTÁ LOGADO!
# Aqui começa o seu código original do app_provas.py (st.set_page_config, menu lateral, abas...)
# =========================================================================

# --- NO MENU LATERAL (ADICIONE O BOTÃO DE SALVAR) ---
with st.sidebar:
    # --- NOVO BLOCO DE CONTROLE (Passo 4) ---
    st.success(f"📌 **Prof. {st.session_state.usuario_logado.capitalize()}**")
    
    # Botão para salvar na nuvem
    if st.button("☁️ Salvar Alterações na Nuvem", type="primary", use_container_width=True):
        with st.spinner("Sincronizando com o cofre..."):
            salvar_banco_no_cofre() # Essa função está lá no seu db.py
        st.toast("Dados salvos com sucesso!", icon="✅")

    # Botão para sair
    if st.button("🚪 Sair (Logout)", use_container_width=True):
        salvar_banco_no_cofre() # Salva automaticamente antes de fechar
        del st.session_state.usuario_logado
        st.rerun()
    
    st.divider() # Uma linha para separar do seu menu original

# ... (continua com as suas abas: aba_correcao, aba_turmas, etc.) ...
# =========================================================================
# --- 1. MANUTENÇÃO E BACKUP ---
# =========================================================================
def limpar_arquivos_temporarios():
    extensoes_lixo = ['.tex', '.log', '.aux', '.out', '.toc']
    arquivos_protegidos = ['logo.png', 'banco_provas.db', 'app_provas.py', 'template_profissional.tex', 'template_gabarito.tex']
    removidos = 0
    for f in os.listdir('.'):
        is_lixo_padrao = any(f.endswith(ext) for ext in extensoes_lixo)
        is_qr_code = f.startswith('qr_') and f.endswith('.png')
        if is_lixo_padrao or is_qr_code:
            if f not in arquivos_protegidos and not f.endswith('.pdf'):
                try:
                    os.remove(f)
                    removidos += 1
                except Exception as e:
                    print(f"Não foi possível remover {f}: {e}")
    return removidos

# =========================================================================
# --- 2. LISTAS DE SÍMBOLOS E PAINEL FLUTUANTE ---
# =========================================================================
# A NOVA LISTA DE ESTILOS GERAIS (COM CÓDIGOS CORRIGIDOS)
estilo = [
    ("𝐁 Negrito", r"\textbf{texto}"), 
    ("𝐼 Itálico", r"\textit{texto}"), 
    ("U̲ Sublinh.", r"\underline{texto}"), 
    ("T Grande", r"\Large{texto}"), 
    ("t Pequeno", r"\small{texto}"), 
    ("🔴 Cor", r"\textcolor{red}{texto}"), 
    ("H1 Título", r"\section*{texto}"), 
    ("H2 Subtít.", r"\subsection*{texto}"), 
    ("• Tópicos", r"\begin{itemize} \item item 1 \item item 2 \end{itemize}"), 
    ("1. Lista", r"\begin{enumerate} \item item 1 \item item 2 \end{enumerate}"), 
    ("Tabela", r"\begin{tabular}{|c|c|} \hline Coluna A & Coluna B \\ \hline Dado 1 & Dado 2 \\ \hline \end{tabular}"), 
    ("Citação", r"\cite{referencia}"), 
    ("Referência", r"\ref{label}"),
    ("</> Código", r"\texttt{codigo}")
]
gregas = [("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("δ", r"\delta"), ("ε", r"\epsilon"), ("ζ", r"\zeta"), ("η", r"\eta"), ("θ", r"\theta"), ("κ", r"\kappa"), ("λ", r"\lambda"), ("μ", r"\mu"), ("ν", r"\nu"), ("ξ", r"\xi"), ("π", r"\pi"), ("ρ", r"\rho"), ("σ", r"\sigma"), ("τ", r"\tau"), ("φ", r"\phi"), ("χ", r"\chi"), ("ψ", r"\psi"), ("ω", r"\omega"), ("Γ", r"\Gamma"), ("Δ", r"\Delta"), ("Θ", r"\Theta"), ("Λ", r"\Lambda"), ("Σ", r"\Sigma"), ("Φ", r"\Phi"), ("Ω", r"\Omega")]
matematica = [(r"x/y", r"\frac{x}{y}"), ("xⁿ", r"x^{n}"), ("xₙ", r"x_{n}"), ("xₙʸ", r"x_{n}^{y}"), ("√x", r"\sqrt{x}"), ("ⁿ√x", r"\sqrt[n]{x}"), ("( )", r"\left(  \right)"), ("[ ]", r"\left[  \right]"), ("{ }", r"\left\{  \right\}"), ("[]₂ₓ₂", r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}"), ("v⃗", r"\vec{v}"), ("n̂", r"\hat{n}"), ("ẋ", r"\dot{x}"), ("ẍ", r"\ddot{x}"), ("x̄", r"\bar{x}"), ("≥", r"\geq"), ("≤", r"\leq"), ("≠", r"\neq"), ("≈", r"\approx"), ("∞", r"\infty"), ("→", r"\to"), ("°C", r"^\circ C"), (" ±", r"\pm"), (" ×", r"\times")]
calculo = [("Lim", r"\lim_{x \to \infty}"), ("∫", r"\int"), ("∫ₐᵇ", r"\int_{a}^{b}"), ("∬", r"\iint"), ("∮", r"\oint"), ("Σ", r"\sum_{i=1}^{n}"), ("Π", r"\prod_{i=1}^{n}"), ("d/dx", r"\frac{d}{dx}"), ("d²/dx²", r"\frac{d^2}{dx^2}"), ("∂", r"\partial"), ("∇", r"\nabla"), ("∇⋅F", r"\nabla \cdot"), ("∇×F", r"\nabla \times")]
fluidos = [("Bernoulli", r"P_1 + \frac{1}{2}\rho v_1^2 + \rho g z_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g z_2"), ("Darcy-Weisbach", r"h_f = f \cdot \frac{L}{D} \cdot \frac{v^2}{2g}"), ("Reynolds", r"Re = \frac{\rho v D}{\mu}"), ("Continuidade", r"A_1 v_1 = A_2 v_2"), ("Empuxo", r"E = \rho_{liq} \cdot V_{sub} \cdot g"), ("Pressão Hidro.", r"P = P_{atm} + \rho g h")]
termo = [("1ª Lei", r"\Delta U = Q - W"), ("Gás Ideal", r"P V = n R T"), ("Trabalho Exp.", r"W = \int_{V_1}^{V_2} P dV"), ("Rendimento η", r"\eta = \frac{W_{liq}}{Q_{q}}"), ("Carnot", r"\eta_{max} = 1 - \frac{T_f}{T_q}"), ("Entropia ΔS", r"\Delta S = \int \frac{dQ_{rev}}{T}"), ("Calor Sensível", r"Q = m \cdot c \cdot \Delta T")]

def injetar_direto(comando, target_key):
    if target_key in st.session_state: st.session_state[target_key] += f" ${comando}$ "
    else: st.session_state[target_key] = f" ${comando}$ "
# NOVA FUNÇÃO (para Textos, Tabelas e Tópicos com £)
def injetar_texto(comando, target_key):
    if target_key in st.session_state: st.session_state[target_key] += f" £{comando}£ "
    else: st.session_state[target_key] = f" £{comando}£ "

    

# =========================================================================
# --- 3. INICIALIZAÇÃO DA INTERFACE (STREAMLIT) ---
# =========================================================================
criar_base_de_dados()
st.set_page_config(page_title="Gerador da Mari", layout="wide", initial_sidebar_state="collapsed")
# === 🎨 AJUSTE DE DESIGN PROFISSIONAL CALIBRADO (CSS) ===
st.markdown("""
    <style>
    /* 1. TOPO DA TELA: Devolve espaço para as abas não sumirem */
    .block-container {
        padding-top: 3.5rem !important; 
        margin-top: 4px !important;
    }

    /* 2. BOTÕES: Mantém o tamanho slim e força a altura EXATA para todos */
    div[data-testid="stPopover"] button, 
    div.stButton button {
        height: 40px !important;
        min-height: 40px !important;
        max-height: 40px !important; 
        width: 100% !important; /* 🔥 A MÁGICA ACONTECE AQUI: Força a esticar! 🔥 */
        box-sizing: border-box !important; 
        padding: 0px 10px !important;
        font-size: 14px !important;
        line-height: 1.2 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        white-space: nowrap !important; 
        overflow: hidden !important;    
    }
    

    /* 3. TÍTULOS (ENUNCIADO): Ajustado para NÃO encavalar nos botões */
    .stMarkdown p strong {
        font-size: 15px !important;
        color: #31333F !important;
        display: block !important;
        margin-bottom: 2px !important; /* Tiramos o negativo para não subir no texto */
        margin-top: 5px !important;
    }

    /* 4. COMPACTAÇÃO GERAL: Diminui o buraco entre as linhas */
    [data-testid="stVerticalBlock"] {
        gap: 0.7rem !important;
    }

    /* 5. LINHA DIVISÓRIA: Fina e discreta */
    hr { margin: 0.5rem 0 !important; }

    /* Ajuste para o texto dentro do botão não sumir */
    div[data-testid="stPopover"] p { font-size: 14px !important; margin: 0 !important; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ Manutenção do Sistema")
    
    # 1. Limpeza de arquivos (Evita conflitos no LaTeX)
    if st.button("🧹 Limpar Arquivos Temporários", use_container_width=True):
        qtd_removidos = limpar_arquivos_temporarios()
        if qtd_removidos > 0: 
            st.success(f"Limpeza concluída! {qtd_removidos} arquivos apagados.")
        else: 
            st.info("A pasta já está limpa.")

    # 2. Segurança de Dados (Backups)
    if st.button("💾 Fazer Backup Local", use_container_width=True):
        nome_bkp = criar_backup_banco()
        if nome_bkp: st.success(f"Backup criado: {nome_bkp}")
        else: st.error("Falha ao criar o backup local.")
            
    if st.button("☁️ Forçar Backup iCloud", use_container_width=True):
        if backup_para_icloud(): st.success("Sincronizado com o iCloud!")
        else: st.error("Falha na sincronização.")

    with st.popover("🐞 Reportar Erro aos Desenvolvedores"):
        msg_erro = st.text_area("O que aconteceu?")
        if st.button("Enviar Relato"):
            with sqlite3.connect('banco_provas.db') as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS bugs (id INTEGER PRIMARY KEY, msg TEXT, data TEXT)")
                conn.execute("INSERT INTO bugs (msg, data) VALUES (?,?)", (msg_erro, datetime.now().strftime("%d/%m %H:%M")))
            st.success("Relato salvo! Vou analisar em breve.")
    # 3. O NOVO DEPURADOR (Sua "Caixa-Preta")
    st.write("---")
    st.subheader("🕵️ Depurador LaTeX")
    with st.expander("🐛 Ver Log de Compilação", expanded=False):
        if 'latex_log' in st.session_state and st.session_state.latex_log:
            st.code(st.session_state.latex_log, language="log")
            if st.button("🧹 Limpar Histórico do Log"):
                st.session_state.latex_log = ""
                st.rerun()
        else:
            st.info("Nenhum log gerado. Tente compilar uma prova.")

    st.write("---")
    st.subheader("⚠️ Zona de Perigo")
    if st.button("🚨 RESETAR DADOS DE TESTE", use_container_width=True):
        if limpar_dados_teste():
            st.success("Banco de dados resetado!")
            st.balloons()

# 🟢 OS 4 PILARES MESTRES DA SUA ARQUITETURA
aba_inicio, aba_avaliacoes, aba_fabrica, aba_turmas, aba_sala = st.tabs([
    " 🏠 Início", "🎯 Central de Avaliações", "🏭 Fábrica de Disciplinas", "🏫 Semestres e Turmas", "🎮 Sala de Aula (Dojo)"
])
# =========================================================================
# PILAR 1: TELA DE BOAS VINDAS E TUTORIAL
# =========================================================================
with aba_inicio:
    st.markdown("<h1 style='text-align: center; color: #2c3e50;'>👋 Bem-vinda ao Gerador da Mari!</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 18px; color: #7f8c8d;'>Sua central completa de gestão acadêmica e ensino de Engenharia.</p>", unsafe_allow_html=True)
    st.write("---")

    col_h1, col_h2 = st.columns(2)
    
    with col_h1:
        st.markdown("""
        <div style="background-color: #e8f4fd; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #0c5460; font-size: 16px;">🎯 Central de Avaliações</b><br><br>
            <span style="color: #0c5460; font-size: 15px;">Crie questões, gere provas em PDF com QR Code e corrija lotes inteiros de forma automática usando nossa visão computacional.</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background-color: #edf7ed; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #1e4620; font-size: 16px;">🏫 Semestres e Turmas</b><br><br>
            <span style="color: #1e4620; font-size: 15px;">Importe seus alunos, gerencie matrículas, configure os pesos das notas (Provas, Listas, Labs) e gere o Boletim Mestre final.</span>
        </div>
        """, unsafe_allow_html=True)

    with col_h2:
        st.markdown("""
        <div style="background-color: #fff8e1; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #663c00; font-size: 16px;">🏭 Fábrica de Disciplinas</b><br><br>
            <span style="color: #663c00; font-size: 15px;">Monte o seu Plano de Ensino estruturado (Ementa, Bibliografia) e planeje o roteiro completo de aulas do semestre.</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background-color: #fdeded; padding: 15px; border-radius: 8px; height: 140px; margin-bottom: 15px;">
            <b style="color: #5f2120; font-size: 16px;">🎮 Sala de Aula (Dojo)</b><br><br>
            <span style="color: #5f2120; font-size: 15px;">Seu painel ao vivo: faça chamadas rápidas, registre o diário, controle o tempo, sorteie alunos e aplique feedbacks de comportamento.</span>
        </div>
        """, unsafe_allow_html=True)

    st.write("---")
    st.subheader("💡 Como começar um novo semestre?")
    
    with st.expander("1️⃣ Preparando o Terreno (Passo a Passo)"):
        st.write("""
        1. **Crie a Turma:** Vá na aba *Semestres e Turmas* e cadastre a sua turma (Ex: Turma 2026.1).
        2. **Importe os Alunos:** Ainda na mesma aba, suba sua planilha de Excel/CSV com as colunas NOME e RA.
        3. **Crie a Disciplina:** Vá na *Fábrica de Disciplinas* e crie o molde (Ex: Termodinâmica ou Mecânica dos Fluidos) preenchendo o plano de aulas.
        4. **Faça as Matrículas:** Volte em *Semestres e Turmas*, selecione a turma e a disciplina, e matricule os alunos.
        5. **Defina as Notas:** Na sub-aba *Pesos de Notas*, configure quantas provas, listas e laboratórios a disciplina terá para gerar o Boletim.
        """)
        
    with st.expander("2️⃣ Dicas de Ouro 🏆"):
        st.write("""
        * **Fórmulas Matemáticas Rápidas:** Na hora de cadastrar questões, use a ferramenta `f(x)` para injetar equações complexas de fluidos e termodinâmica sem precisar digitar o código LaTeX inteiro.
        * **Modo Grupos:** No Dojo (Sala de Aula), a aba "Grupos" permite dividir a sala e lançar a nota de uma atividade prática para 4 ou 5 alunos de uma vez só!
        * **Segurança dos Dados:** Use a barra lateral 🛠️ para fazer backups regulares do seu banco de dados e sincronizar com a nuvem.
        """)
# =========================================================================
# PILAR 2: CENTRAL DE AVALIAÇÕES
# =========================================================================
with aba_avaliacoes:
    # A LINHA st.header FOI APAGADA DAQUI 
    
    # Substituição: declarando de forma explícita para o Pylance entender
    abas_centrais = st.tabs([
        "➕ 1. Cadastrar Questão", "🗂️ 2. Editar Banco", "🖨️ 3. Gerar Prova (PDF)", "📸 4. Corrigir Lote"
    ])
    sub_cad = abas_centrais[0]
    sub_edit = abas_centrais[1]
    sub_gen = abas_centrais[2]
    sub_corr = abas_centrais[3]
    
    # --- SUB-ABA 1.1: CADASTRAR ---
    with sub_cad:
        if st.session_state.get('limpar_proxima_cad'):
            keys_texto = ["enun_input", "gab_input_cad"]
            for k in list(st.session_state.keys()):
                if k.startswith("t_alt_cad_") or k in keys_texto: st.session_state[k] = ""
            st.session_state.uploader_reset_cad = st.session_state.get('uploader_reset_cad', 0) + 1
            st.session_state.limpar_proxima_cad = False
        st.markdown("**⚙️ Configuração**")
        
        c1, c2, c3, c_uso = st.columns([0.2, 0.25, 0.3, 0.25])
        with c1: t_q = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], key="cad_tipo")
        with c2: d_c = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="cad_disc")
        with c3: ass_c = st.text_input("Assunto", placeholder="Ex: Ciclos", key="cad_ass")
        with c_uso: uso_c = st.selectbox("Uso da Questão", ["Prova Oficial", "Lista de Treino", "Dojo / Sala"], key="cad_uso")

        c4, c5, c6, c7 = st.columns([0.2, 0.2, 0.3, 0.3])
        with c4: dif_c = st.selectbox("Dificuldade", ["Fácil", "Média", "Difícil"], key="cad_dif")
        with c5: p_c = st.number_input("Pontos", min_value=0.1, value=1.0, key="cad_pt")
        with c6: esp_c = st.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], key="cad_esp")
        with c7: tam_c = st.number_input("Tamanho (cm)", min_value=1, value=4, key="cad_tam")

        # --- BLOCO UNIFICADO: ELABORAÇÃO DO ENUNCIADO (SUB-ABA 1.1) ---
        st.write("---")
        
       
        
        st.markdown("**💬 Enunciado**")
        
        # 1. BARRA DE FERRAMENTAS (Lado a Lado no Topo)
        col_ferramentas = st.columns([0.15, 0.15, 0.15, 0.55])
         # Puxamos o reset_id para garantir que o upload de imagem limpe após salvar
        reset_id = st.session_state.get('uploader_reset_cad', 0)
        with col_ferramentas[0]:
            with st.popover("🖋️ Estilo", use_container_width=True):
                c = st.columns(2)
                for i, (l, cmd) in enumerate(estilo): 
                    c[i%2].button(l, key=f"cad_est_{i}", on_click=injetar_texto, args=(cmd, "enun_input"))
        
        with col_ferramentas[1]:
            with st.popover("🧮 f(x)", use_container_width=True):
                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                with tg:
                    c = st.columns(4)
                    for i, (l, cmd) in enumerate(gregas): c[i%4].button(l, key=f"cad_gr_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tm:
                    c = st.columns(3)
                    for i, (l, cmd) in enumerate(matematica): c[i%3].button(l, key=f"cad_mt_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tc:
                    c = st.columns(3)
                    for i, (l, cmd) in enumerate(calculo): c[i%3].button(l, key=f"cad_cl_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tf:
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(fluidos): c[i%2].button(l, key=f"cad_fl_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))
                with tt:
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(termo): c[i%2].button(l, key=f"cad_tr_{i}", on_click=injetar_direto, args=(cmd, "enun_input"))

        with col_ferramentas[2]:
            with st.popover("🖼️ Imagem", use_container_width=True):
                i_c = st.file_uploader("Anexar Imagem", type=["png", "jpg", "jpeg"], key=f"up_enun_cad_{reset_id}", label_visibility="collapsed")
                if i_c: 
                    st.image(i_c, caption="Preview da Imagem", use_container_width=True)

        # 2. CAIXA DE TEXTO (Largura Total)
        e_c = st.text_area("Enunciado", key="enun_input", height=180, label_visibility="collapsed", placeholder="Escreva o enunciado aqui...")

        # 3. PREVIEW E LÓGICA DE SEGURANÇA (DUPLICATAS)
        pode_gravar = True
        if e_c.strip():
            with st.expander("👁️ Pré-visualização", expanded=True): 
                # O \u200b força o Streamlit a renderizar LaTeX misturado com HTML (tabelas/cores)
                st.markdown("\u200b" + gerar_preview_web(e_c), unsafe_allow_html=True)
            
            # Verificação de Duplicatas (Evita questões repetidas no seu banco)
            id_duplicado = detectar_duplicata(e_c, d_c)
            if id_duplicado:
                st.error(f"⚠️ **Questão idêntica!** Já existe no banco (ID: {id_duplicado}).")
                pode_gravar = False
            else:
                similares = buscar_questoes_proximas(e_c, d_c, limite=0.75)
                if similares:
                    st.warning(f"🔔 **Atenção:** Encontrei {len(similares)} questões muito parecidas.")
                    with st.expander("Ver similares para comparar"):
                        for s in similares[:3]: st.write(f"- ID {s['id']} ({s['percentual']:.1f}% similar): {s['texto'][:100]}...")
                    confirmar_similar = st.checkbox("Esta questão é diferente. Quero salvar mesmo assim.", key="chk_sim")
                    if not confirmar_similar: pode_gravar = False
        # --- FIM DO BLOCO UNIFICADO ---
        st.write("---")
        st.markdown("**💡 Resposta**")
        alts_final, gab_d_final, gab_img_final = [], None, None
        letras = "ABCDEFGHIJ"
        
        if t_q == "Múltipla Escolha":
            if "n_opt" not in st.session_state: st.session_state.n_opt = 4
            
            cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
            if cb1.button("➕ Linha", key="cad_add_l"): st.session_state.n_opt += 1; st.rerun()
            if cb2.button("➖ Linha", key="cad_rm_l") and st.session_state.n_opt > 2: st.session_state.n_opt -= 1; st.rerun()
            
            

            for i in range(st.session_state.n_opt):
                # Cada alternativa em um card visual separado
                with st.container(border=True):
                    # Linha 1: Barra de Ferramentas (Agora com Imagem em Popover)
                    c_check, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])

                    corr = c_check.checkbox(letras[i], key=f"c_alt_cad_{i}")
                    
                    with c_est:
                        with st.popover("🖋️ Estilo", use_container_width=True):
                            c = st.columns(2)
                            for idx, (l, cmd) in enumerate(estilo): 
                                c[idx%2].button(l, key=f"alt_e_{i}_{idx}", on_click=injetar_texto, args=(cmd, f"t_alt_cad_{i}"))
                    
                    with c_fx:
                        with st.popover("🧮 f(x)", use_container_width=True):
                            tg, tm, tc, tf, tt = st.tabs(["α", "M", "C", "🌊", "🔥"])
                            with tg:
                                c = st.columns(4)
                                for idx, (l, cmd) in enumerate(gregas): c[idx%4].button(l, key=f"alt_g_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tm:
                                c = st.columns(3)
                                for idx, (l, cmd) in enumerate(matematica): c[idx%3].button(l, key=f"alt_m_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tc:
                                c = st.columns(3)
                                for idx, (l, cmd) in enumerate(calculo): c[idx%3].button(l, key=f"alt_c_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tf:
                                c = st.columns(1)
                                for idx, (l, cmd) in enumerate(fluidos): c[0].button(l, key=f"alt_f_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))
                            with tt:
                                c = st.columns(1)
                                for idx, (l, cmd) in enumerate(termo): c[0].button(l, key=f"alt_t_{i}_{idx}", on_click=injetar_direto, args=(cmd, f"t_alt_cad_{i}"))

                    with c_img:
                        # Botão de imagem idêntico ao do enunciado
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            img_alt = st.file_uploader(f"Imagem {letras[i]}", type=["png", "jpg", "jpeg"], key=f"i_alt_cad_{i}_{reset_id}", label_visibility="collapsed")

                    # Linha 2: Campo de Texto
                    txt = st.text_input(f"Texto da {letras[i]}", key=f"t_alt_cad_{i}", label_visibility="collapsed", placeholder=f"Alternativa {letras[i]}...")
                    
                    # Linha 3: Previews (Texto e Imagem)
                    if txt.strip():
                        st.markdown(f'<span style="color:#2ecc71;">↳</span> {gerar_preview_web(txt)}', unsafe_allow_html=True)
                    
                    if img_alt:
                        # Preview da imagem aparece automático após o upload
                        st.image(img_alt, width=150)
                    
                    alts_final.append((txt, corr, img_alt))
        
        elif t_q == "Verdadeiro ou Falso":
            resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], horizontal=True)
            alts_final = [("Verdadeiro", resp == "Verdadeiro", None), ("Falso", resp == "Falso", None)]
        
        elif t_q == "Numérica":
            
            gab_num = st.number_input("Resposta Exata (0 a 99):", min_value=0, max_value=99, step=1)
            gab_d_final = str(gab_num).zfill(2) 
            c_g1, c_g2 = st.columns([0.85, 0.15])
            with c_g1: st.info(f"O gabarito será salvo como: **{gab_d_final}**")
            gab_img_final = st.file_uploader("Upload de Imagem da Resolução", type=["png", "jpg", "jpeg"], key=f"gab_img_cad_{reset_id}")
            
        else: # Discursiva
            st.markdown("**💡 Resolução Detalhada**")
            
            # 1. BARRA DE FERRAMENTAS SUPERIOR (Lado a Lado)
            col_gab_ferr = st.columns([0.15, 0.15, 0.15, 0.55])
            
            with col_gab_ferr[0]:
                with st.popover("🖋️ Estilo", use_container_width=True):
                    c = st.columns(2)
                    for i, (l, cmd) in enumerate(estilo): 
                        c[i%2].button(l, key=f"gab_est_{i}", on_click=injetar_texto, args=(cmd, "gab_input_cad"))
            
            with col_gab_ferr[1]:
                with st.popover("🧮 f(x)", use_container_width=True):
                    tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                    with tg:
                        c = st.columns(4)
                        for i, (l, cmd) in enumerate(gregas): c[i%4].button(l, key=f"gab_gr_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tm:
                        c = st.columns(3)
                        for i, (l, cmd) in enumerate(matematica): c[i%3].button(l, key=f"gab_mt_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tc:
                        c = st.columns(3)
                        for i, (l, cmd) in enumerate(calculo): c[i%3].button(l, key=f"gab_cl_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tf:
                        # Coluna única para nomes longos (Bernoulli, Reynolds...)
                        c = st.columns(1)
                        for i, (l, cmd) in enumerate(fluidos): c[0].button(l, key=f"gab_fl_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))
                    with tt:
                        c = st.columns(1)
                        for i, (l, cmd) in enumerate(termo): c[0].button(l, key=f"gab_tr_{i}", on_click=injetar_direto, args=(cmd, "gab_input_cad"))

            with col_gab_ferr[2]:
                with st.popover("🖼️ Imagem", use_container_width=True):
                    # O uploader fica aqui dentro, mas o preview aparece fora para você conferir
                    gab_img_final = st.file_uploader("Upload da Resolução", type=["png", "jpg", "jpeg"], key=f"gab_img_cad_{reset_id}", label_visibility="collapsed")

            # 2. CAIXA DE TEXTO (Largura Total para fórmulas longas)
            gab_d_final = st.text_area("Texto da Resolução", key="gab_input_cad", height=150, label_visibility="collapsed", placeholder="Explique o passo a passo da solução aqui...")

            # 3. PREVIEWS REATIVOS (Texto e Imagem)
            if gab_d_final.strip():
                with st.expander("👁️ Pré-visualização da Resolução", expanded=True):
                    # O \u200b garante que o Streamlit processe a matemática corretamente
                    st.markdown("\u200b" + gerar_preview_web(gab_d_final), unsafe_allow_html=True)
            
            if gab_img_final:
                st.image(gab_img_final, caption="👁️ Preview da Imagem da Resolução", width=400)
        st.write("---")
        if st.button("💾 Guardar Questão", type="primary", width="stretch", disabled=not pode_gravar):
            img_n = sanitizar_nome(i_c.name) if i_c else None
            if i_c:
                with open(img_n, "wb") as f: f.write(i_c.getbuffer())
            
            gab_img_n = sanitizar_nome(gab_img_final.name) if gab_img_final else None
            if gab_img_final:
                with open(gab_img_n, "wb") as f: f.write(gab_img_final.getbuffer())
            
            alts_para_banco = []
            for txt, corr, img_obj in alts_final:
                nome_img_alt = sanitizar_nome(img_obj.name) if img_obj else None
                if img_obj:
                    with open(nome_img_alt, "wb") as f: f.write(img_obj.getbuffer())
                alts_para_banco.append((txt, corr, nome_img_alt))

            # Adicione , uso_c no final dos parênteses da função:
            inserir_questao(d_c, ass_c, dif_c, e_c, alts_para_banco, p_c, t_q, gab_d_final, img_n, esp_c, tam_c, gab_img_n, uso_c)
            st.success("✅ Questão guardada com sucesso!")
            st.session_state.limpar_proxima_cad = True
            st.rerun()

    # --- SUB-ABA 1.2: EDITAR BANCO ---
    with sub_edit:
        conn = sqlite3.connect('banco_provas.db')
        df_todas = pd.read_sql('SELECT id, disciplina, assunto, dificuldade, tipo, enunciado FROM questoes ORDER BY id DESC', conn)
        conn.close()
        st.markdown("**🔍 Filtro**")
        if not df_todas.empty:
            col_f1, col_f2 = st.columns(2)
            disc_filtro = col_f1.selectbox("Filtrar por Disciplina:", ["Todas"] + list(df_todas['disciplina'].unique()), key="ed_filtro_disc")
            tipo_filtro = col_f2.selectbox("Filtrar por Tipo:", ["Todas"] + list(df_todas['tipo'].unique()), key="ed_filtro_tipo")

            df_filtrado = df_todas.copy()
            if disc_filtro != "Todas": df_filtrado = df_filtrado[df_filtrado['disciplina'] == disc_filtro]
            if tipo_filtro != "Todas": df_filtrado = df_filtrado[df_filtrado['tipo'] == tipo_filtro]

            opcoes_q = ["Escolha uma questão..."] + [f"ID {row['id']} | {row['disciplina']} | {row['assunto']} | {row['enunciado'][:50]}..." for _, row in df_filtrado.iterrows()]
            q_sel = st.selectbox("Selecione a questão para editar:", opcoes_q, key="ed_q_sel")
            
            
            if q_sel != "Escolha uma questão...":
                st.write("---")
                st.markdown("**⚙️ Configuração**")
                id_editar = int(q_sel.split(" | ")[0].replace("ID ", ""))
                conn = sqlite3.connect('banco_provas.db')
                c = conn.cursor()
                
                # --- MIGRATION DE SEGURANÇA: Cria a coluna nas questões antigas se ela não existir ---
                try: c.execute("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
                except: pass
                
                c.execute('SELECT disciplina, assunto, dificuldade, enunciado, imagem, pontos, tipo, gabarito_discursivo, espaco_resposta, espaco_linhas, gabarito_imagem, uso_quest FROM questoes WHERE id=?', (id_editar,))
                q_data = c.fetchone()
                
                if q_data:
                    q_disc, q_ass, q_dif, q_enun, q_img, q_pts, q_tipo, q_gab_disc, q_esp, q_esp_l, q_gab_img, q_uso = q_data

                    # --- 1. CONFIGURAÇÕES (LINHA COMPACTA) ---
                    c1, c2, c3, c_uso = st.columns([0.2, 0.25, 0.3, 0.25])
                    with c1: n_tipo = st.selectbox("Tipo", ["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"], index=["Múltipla Escolha", "Verdadeiro ou Falso", "Discursiva", "Numérica"].index(q_tipo), key=f"ed_tipo_{id_editar}")
                    with c2: n_disc = st.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], index=["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"].index(q_disc) if q_disc in ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"] else 0, key=f"ed_disc_{id_editar}")
                    with c3: n_ass = st.text_input("Assunto", value=q_ass if q_ass else "", key=f"ed_ass_{id_editar}")
                    
                    lista_usos = ["Prova Oficial", "Lista de Treino", "Dojo / Sala"]
                    idx_uso = lista_usos.index(q_uso) if q_uso in lista_usos else 0
                    with c_uso: n_uso = st.selectbox("Uso da Questão", lista_usos, index=idx_uso, key=f"ed_uso_{id_editar}")

                    c4, c5, c6, c7 = st.columns([0.2, 0.15, 0.3, 0.35])
                    with c4: n_dif = st.selectbox("Dificuldade", ["Fácil", "Média", "Difícil"], index=["Fácil", "Média", "Difícil"].index(q_dif) if q_dif in ["Fácil", "Média", "Difícil"] else 1, key=f"ed_dif_{id_editar}")
                    with c5: n_pts = st.number_input("Pontos", min_value=0.1, value=float(q_pts), step=0.5, key=f"ed_pts_{id_editar}")
                    with c6: n_esp = st.selectbox("Espaço", ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"], index=["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"].index(q_esp) if q_esp in ["Linhas", "Quadriculado", "Caixa Vazia", "Nenhum"] else 0, key=f"ed_esp_{id_editar}")
                    with c7: n_tam = st.number_input("Tamanho (cm)", min_value=1, value=int(q_esp_l), key=f"ed_tam_{id_editar}")
                    st.write("---")
                    # --- 2. ENUNCIADO (LAYOUT MAGNÉTICO + FÓRMULAS) ---
                    st.markdown("**💬 Enunciado**")
                    key_enun = f"ed_enun_input_{id_editar}"
                    if key_enun not in st.session_state: st.session_state[key_enun] = q_enun

                    # Declarando e usando as colunas desempacotadas
                    col_ed_1, col_ed_2, col_ed_3, _ = st.columns([0.15, 0.15, 0.15, 0.55])

                    with col_ed_1:
                        with st.popover("🖋️ Estilo", use_container_width=True):
                            ce = st.columns(2)
                            for idx, (l, cmd) in enumerate(estilo): ce[idx%2].button(l, key=f"ed_e_{id_editar}_{idx}", on_click=injetar_texto, args=(cmd, key_enun))
                    with col_ed_2:
                        with st.popover("🧮 f(x)", use_container_width=True):
                            tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                            with tg: 
                                cg_g = st.columns(4)
                                for i, (l, cmd) in enumerate(gregas): cg_g[i%4].button(l, key=f"ed_g_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tm: 
                                cg_m = st.columns(3)
                                for i, (l, cmd) in enumerate(matematica): cg_m[i%3].button(l, key=f"ed_m_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tc: 
                                cg_c = st.columns(3)
                                for i, (l, cmd) in enumerate(calculo): cg_c[i%3].button(l, key=f"ed_gc_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tf: 
                                cg_f = st.columns(1)
                                for i, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"ed_f_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                            with tt: 
                                cg_t = st.columns(1)
                                for i, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"ed_t_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, key_enun))
                    with col_ed_3:
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            n_img_up = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"ed_up_enun_{id_editar}", label_visibility="collapsed")

                    n_enun_final = st.text_area("Enunciado", key=key_enun, height=150, label_visibility="collapsed")
                    
                    if q_img or n_img_up:
                        ci1, ci2 = st.columns(2)
                        if q_img: ci1.image(q_img, caption="🖼️ Atual", width=150)
                        if n_img_up: ci2.image(n_img_up, caption="🆕 Nova", width=150)
                    # --- 3. LÓGICA DE RESPOSTAS E GABARITOS PADRONIZADA ---
                    c.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (id_editar,))
                    alts_q = c.fetchall(); alts_modificadas, alts_imagens_novas = [], {}
                    st.write("---")
                    
                    if n_tipo == "Múltipla Escolha":
                        st.markdown("**💡 Resposta (Alternativas)**")
                        n_opt_key = f"ed_n_opt_{id_editar}"
                        if n_opt_key not in st.session_state: st.session_state[n_opt_key] = max(len(alts_q), 4)
                        
                        cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
                        if cb1.button("➕ Linha", key=f"ed_add_alt_{id_editar}"): st.session_state[n_opt_key] += 1; st.rerun()
                        if cb2.button("➖ Linha", key=f"ed_rm_alt_{id_editar}") and st.session_state[n_opt_key] > 2: st.session_state[n_opt_key] -= 1; st.rerun()

                        for j in range(st.session_state[n_opt_key]):
                            with st.container(border=True):
                                c_chk, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])
                                
                                corr_v = bool(alts_q[j][1]) if j < len(alts_q) else False
                                corr = c_chk.checkbox(letras[j], value=corr_v, key=f"ed_c_alt_{id_editar}_{j}")
                                
                                k_alt = f"ed_t_alt_v_{id_editar}_{j}"
                                if k_alt not in st.session_state: st.session_state[k_alt] = alts_q[j][0] if j < len(alts_q) else ""
                                
                                with c_est:
                                    with st.popover("🖋️ Estilo", use_container_width=True):
                                        c_b = st.columns(2)
                                        for idx, (l, cmd) in enumerate(estilo): 
                                            c_b[idx%2].button(l, key=f"ed_ae_{id_editar}_{j}_{idx}", on_click=injetar_texto, args=(cmd, k_alt))
                                
                                with c_fx:
                                    with st.popover("🧮 f(x)", use_container_width=True):
                                        tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                        with tg:
                                            cb_g = st.columns(4)
                                            for idx, (l, cmd) in enumerate(gregas): cb_g[idx%4].button(l, key=f"ed_ag_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tm:
                                            cb_m = st.columns(3)
                                            for idx, (l, cmd) in enumerate(matematica): cb_m[idx%3].button(l, key=f"ed_am_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tc:
                                            cb_c = st.columns(3)
                                            for idx, (l, cmd) in enumerate(calculo): cb_c[idx%3].button(l, key=f"ed_ac_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tf:
                                            cb_f = st.columns(1)
                                            for idx, (l, cmd) in enumerate(fluidos): cb_f[0].button(l, key=f"ed_af_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tt:
                                            cb_t = st.columns(1)
                                            for idx, (l, cmd) in enumerate(termo): cb_t[0].button(l, key=f"ed_at_{id_editar}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))

                                with c_img:
                                    with st.popover("🖼️ Imagem", use_container_width=True):
                                        up_ia = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"ed_ia_{id_editar}_{j}", label_visibility="collapsed")

                                txt_a = st.text_input("Texto", key=k_alt, label_visibility="collapsed")
                                if txt_a.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(txt_a)}', unsafe_allow_html=True)
                                
                                if (j < len(alts_q) and alts_q[j][2]) or up_ia:
                                    cia = st.columns(2)
                                    if j < len(alts_q) and alts_q[j][2]: cia[0].image(alts_q[j][2], width=80, caption="Atual")
                                    if up_ia: cia[1].image(up_ia, width=80, caption="Nova")

                                alts_imagens_novas[j] = up_ia if up_ia else (alts_q[j][2] if j < len(alts_q) else None)
                                alts_modificadas.append((txt_a, corr))

                    elif n_tipo == "Verdadeiro ou Falso":
                        idx_banco = 0 if any(a[0] == "Verdadeiro" and a[1] for a in alts_q) else 1
                        st.markdown("**💡 Resposta**")
                        resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=idx_banco, horizontal=True, key=f"ed_vf_{id_editar}", label_visibility="collapsed")
                        alts_modificadas = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]

                    elif n_tipo == "Numérica":
                        st.markdown("**💡 Resposta Exata (Numérica)**")
                        val_atual = int(q_gab_disc) if str(q_gab_disc).isdigit() else 0
                        gab_num = st.number_input("Valor (0 a 99):", min_value=0, max_value=99, step=1, value=val_atual, key=f"ed_num_{id_editar}")
                        gab_d_final = str(gab_num).zfill(2)
                        
                        c_g1, c_gi = st.columns([0.85, 0.15])
                        with c_g1: st.info(f"O gabarito exato salvo será: **{gab_d_final}**")
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                n_img_g_up = st.file_uploader("Upload da Resolução", type=["png", "jpg", "jpeg"], key=f"ed_ig_num_{id_editar}", label_visibility="collapsed")
                        
                        if q_gab_img or locals().get('n_img_g_up'):
                            cg1, cg2 = st.columns(2)
                            if q_gab_img: cg1.image(q_gab_img, caption="Atual no Banco", width=150)
                            if locals().get('n_img_g_up'): cg2.image(n_img_g_up, caption="Nova Imagem", width=150)

                    elif n_tipo == "Discursiva":
                        st.markdown("**💡 Resolução Detalhada:**")
                        k_gab = f"ed_gab_input_{id_editar}"
                        if k_gab not in st.session_state: st.session_state[k_gab] = q_gab_disc if q_gab_disc else ""
                        
                        cge, cgf, cgi, _ = st.columns([0.15, 0.15, 0.15, 0.55])
                        with cge:
                            with st.popover("🖋️ Estilo", use_container_width=True):
                                c_gb = st.columns(2)
                                for i, (l, cmd) in enumerate(estilo): c_gb[i%2].button(l, key=f"ed_ge_{id_editar}_{i}", on_click=injetar_texto, args=(cmd, k_gab))
                        with cgf:
                            with st.popover("🧮 f(x)", use_container_width=True):
                                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                with tg: 
                                    cg_g = st.columns(4)
                                    for i, (l, cmd) in enumerate(gregas): cg_g[i%4].button(l, key=f"ed_gg_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tm: 
                                    cg_m = st.columns(3)
                                    for i, (l, cmd) in enumerate(matematica): cg_m[i%3].button(l, key=f"ed_gm_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tc: 
                                    cg_c = st.columns(3)
                                    for i, (l, cmd) in enumerate(calculo): cg_c[i%3].button(l, key=f"ed_gcalc_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tf: 
                                    cg_f = st.columns(1)
                                    for i, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"ed_gf_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                                with tt: 
                                    cg_t = st.columns(1)
                                    for i, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"ed_gt_{id_editar}_{i}", on_click=injetar_direto, args=(cmd, k_gab))
                        with cgi:
                            with st.popover("🖼️ Imagem", use_container_width=True): 
                                n_img_g_up = st.file_uploader("Trocar Resolução", type=["png","jpg","jpeg"], key=f"ed_ig_disc_{id_editar}", label_visibility="collapsed")
                        
                        gab_d_final = st.text_area("Gabarito", key=k_gab, height=120, label_visibility="collapsed")
                        
                        if gab_d_final.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(gab_d_final)}', unsafe_allow_html=True)
                            
                        if q_gab_img or locals().get('n_img_g_up'):
                            cg1, cg2 = st.columns(2)
                            if q_gab_img: cg1.image(q_gab_img, caption="Atual no Banco", width=150)
                            if locals().get('n_img_g_up'): cg2.image(n_img_g_up, caption="Nova", width=150)

                    
                    # --- 5. SALVAMENTO (MOTOR CORRIGIDO SEM ERRO DE SINTAXE) ---
                    st.write("---")
                    cb_s, cb_d, cb_e = st.columns([1, 1, 1])
                    
                    if cb_s.button("💾 Salvar Alterações", type="primary", use_container_width=True):
                        i_f = q_img
                        if n_img_up: 
                            i_f = sanitizar_nome(n_img_up.name)
                            with open(i_f, "wb") as f: f.write(n_img_up.getbuffer())
                        i_g_f = q_gab_img
                        if 'n_img_g_up' in locals() and n_img_g_up:
                            i_g_f = sanitizar_nome(n_img_g_up.name)
                            with open(i_g_f, "wb") as f: f.write(n_img_g_up.getbuffer())

                        val_gab = gab_d_final if 'gab_d_final' in locals() else q_gab_disc
                        c.execute('''UPDATE questoes SET disciplina=?, assunto=?, dificuldade=?, enunciado=?, pontos=?, espaco_resposta=?, espaco_linhas=?, tipo=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=?, uso_quest=? WHERE id=?''', (n_disc, n_ass, n_dif, n_enun_final, n_pts, n_esp, n_tam, n_tipo, i_f, i_g_f, val_gab, n_uso, id_editar))
                        
                        if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                            c.execute('DELETE FROM alternativas WHERE questao_id = ?', (id_editar,))
                            for j, (t, co) in enumerate(alts_modificadas):
                                img_obj = alts_imagens_novas.get(j); img_bd = None
                                if hasattr(img_obj, 'getbuffer'):
                                    nome_f = sanitizar_nome(img_obj.name)
                                    with open(nome_f, "wb") as f: f.write(img_obj.getbuffer())
                                    img_bd = nome_f
                                else: img_bd = img_obj
                                c.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (id_editar, t, co, img_bd))
                        conn.commit(); st.success("✅ Tudo atualizado!"); st.rerun()

                    # O NOVO BOTÃO DE DUPLICAR AQUI:
                    if cb_d.button("💾 Salvar como Nova", use_container_width=True, help="Cria uma CÓPIA exata no banco (ideal para mudar valores)"):
                        i_f = q_img
                        if n_img_up: 
                            i_f = sanitizar_nome(n_img_up.name)
                            with open(i_f, "wb") as f: f.write(n_img_up.getbuffer())
                        i_g_f = q_gab_img
                        if 'n_img_g_up' in locals() and n_img_g_up:
                            i_g_f = sanitizar_nome(n_img_g_up.name)
                            with open(i_g_f, "wb") as f: f.write(n_img_g_up.getbuffer())
                            
                        val_gab = gab_d_final if 'gab_d_final' in locals() else q_gab_disc
                        
                        alts_para_inserir = []
                        if n_tipo in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                            for j, (t, co) in enumerate(alts_modificadas):
                                img_obj = alts_imagens_novas.get(j); img_bd = None
                                if hasattr(img_obj, 'getbuffer'):
                                    nome_f = sanitizar_nome(img_obj.name)
                                    with open(nome_f, "wb") as f: f.write(img_obj.getbuffer())
                                    img_bd = nome_f
                                else: img_bd = img_obj
                                alts_para_inserir.append((t, co, img_bd))
                        
                        # Injeta como uma QUESTÃO NOVA em vez de fazer Update
                        # Injeta como uma QUESTÃO NOVA em vez de fazer Update (agora com n_uso)
                        inserir_questao(n_disc, n_ass, n_dif, n_enun_final, alts_para_inserir, n_pts, n_tipo, val_gab, i_f, n_esp, n_tam, i_g_f, n_uso)
                        st.success("✅ Nova cópia salva no banco de dados!")
                        st.rerun()

                    if cb_e.button("🗑️ Excluir Permanente", use_container_width=True):
                        excluir_questao(id_editar); st.warning("Excluída!"); st.rerun()
                conn.close()
        else: st.info("O seu banco de questões ainda está vazio.")

    
    
    # --- SUB-ABA 1.3: GERAR PROVA (O SEU MOTOR DE PDF) ---
    with sub_gen:
        
        if "arquivos" not in st.session_state: st.session_state.arquivos = []
        if "prova_atual" not in st.session_state: st.session_state.prova_atual = []
        st.markdown("**📌1. Cabeçalho**")
        
        # Leve ajuste de segurança aqui para não dar erro na descompactação se o banco retornar vazio
        if "cabecalho_carregado" not in st.session_state:
            cfg = carregar_configuracoes()
            if cfg:
                st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = cfg
            else:
                st.session_state.inp_inst, st.session_state.inp_prof, st.session_state.inp_dep, st.session_state.inp_cur, st.session_state.inp_instruc = "", "", "", "", ""
            st.session_state.inp_turma, st.session_state.inp_data = "", ""
            st.session_state.cabecalho_carregado = True

        c_cab1, c_cab2 = st.columns(2)
        inst_nome = c_cab1.text_input("Instituição", key="inp_inst")
        prof_nome = c_cab2.text_input("Professor(a)", key="inp_prof")
        c_cab3, c_cab4, c_cab5 = st.columns(3)
        depto, curs, turma_p = c_cab3.text_input("Disciplina", key="inp_dep"), c_cab4.text_input("Curso", key="inp_cur"), c_cab5.text_input("Turma", key="inp_turma")
        c_cab6, c_cab7 = st.columns(2)
        data_p = c_cab6.text_input("Data", key="inp_data")
        titulo_doc = c_cab7.text_input("Título do Documento", value="Avaliação 01", key="inp_titulo")
        # --- A GRANDE NOVIDADE: O OBJETIVO DO DOCUMENTO ---
        tipo_doc_gen = st.radio("🎯 Objetivo do Documento:", ["Prova Oficial (Boletim)", "Atividade de Treino (Só Feedback)"], horizontal=True)
        logo_up = st.file_uploader("Logo da Instituição (PNG/JPG)", type=["png", "jpg", "jpeg"])
      
        instrucoes = st.text_area("Instruções", key="inp_instruc")
        
        # --- 🎮 SEUS BOTÕES DE CONTROLE DO CABEÇALHO ADICIONADOS AQUI ---
        cc1, cc2, cc3 = st.columns([0.4, 0.3, 0.3])
        if cc1.button("💾 Salvar como Padrão", use_container_width=True):
            salvar_configuracoes(inst_nome, prof_nome, depto, curs, instrucoes)
            st.success("✅ Cabeçalho salvo no banco de dados!")
            
        if cc2.button("🔄 Puxar do Banco", use_container_width=True):
            if "cabecalho_carregado" in st.session_state:
                del st.session_state["cabecalho_carregado"]
            st.rerun()
            
        if cc3.button("🧹 Limpar Campos", use_container_width=True):
            st.session_state.inp_inst = ""
            st.session_state.inp_prof = ""
            st.session_state.inp_dep = ""
            st.session_state.inp_cur = ""
            st.session_state.inp_instruc = ""
            st.rerun()
        
        st.write("---")

        st.markdown("**🆔 2. Identificação dos Alunos nas Provas**")
        
        modo_id = st.radio("Como deseja identificar as provas?", ["Em Branco (Sem Nome/RA)", "Usar Turma Cadastrada", "Upload Temporário de Lista"], horizontal=True)
        arquivo_lista = None
        alunos_selecionados_df = None
        q_a = 1

        if modo_id == "Em Branco (Sem Nome/RA)":
            st.info("🔔 O sistema gerará cópias genéricas (ex: Versão A-001, A-002).")
            q_a = st.number_input("Quantas provas deseja gerar?", min_value=1, max_value=300, value=30)
        elif modo_id == "Upload Temporário de Lista":
            arquivo_lista = st.file_uploader("Upload da Lista", type=['xlsx', 'csv'], key="up_lista_alunos")
        elif modo_id == "Usar Turma Cadastrada":
            conn = sqlite3.connect('banco_provas.db')
            turmas_db = pd.read_sql('SELECT * FROM turmas', conn)
            if not turmas_db.empty:
                t_escolhida = st.selectbox("Escolha a Turma:", turmas_db['nome'].tolist())
                id_t_escolhida = turmas_db[turmas_db['nome'] == t_escolhida]['id'].values[0]
                alunos_da_turma = pd.read_sql(f'SELECT nome as NOME, ra as RA FROM alunos WHERE turma_id = {id_t_escolhida}', conn)
                if not alunos_da_turma.empty:
                    opcoes_alunos = alunos_da_turma['NOME'].tolist()
                    selecao = st.multiselect("Selecione os alunos (vazio = turma toda):", opcoes_alunos)
                    if selecao: alunos_selecionados_df = alunos_da_turma[alunos_da_turma['NOME'].isin(selecao)]
                    else: alunos_selecionados_df = alunos_da_turma
                    st.success(f"{len(alunos_selecionados_df)} aluno(s) selecionado(s).")
                else: st.warning("Esta turma ainda não tem alunos cadastrados.")
            else: st.warning("Nenhuma turma cadastrada.")
            conn.close()
        st.write("---")
        st.markdown("**☑️ 3. Seleção de Questões**")
        col_p1, col_p2, col_p3 = st.columns(3) 
        d_p = col_p1.selectbox("Disciplina", ["Termodinâmica", "Mecânica dos Fluidos", "TCC 1"], key="g_disc")
        q_v = col_p2.number_input("Versões", 1, 10, 1)
        layout_colunas = col_p3.radio("Layout", ["1 Coluna", "2 Colunas"], horizontal=True)
        num_colunas = 2 if layout_colunas == "2 Colunas" else 1

        modo_selecao = st.radio("Modo", ["Sorteio Automático", "Escolha Manual"], horizontal=True)

        if modo_selecao == "Sorteio Automático":
            st.markdown("**🎰 Regras de Sorteio**")
            if "num_regras" not in st.session_state: st.session_state.num_regras = 1

            with st.container(border=True):
                c_h1, c_h2, c_h3, c_h4, c_h5 = st.columns([0.1, 0.25, 0.2, 0.2, 0.25])
                c_h1.markdown("**Qtd**")
                c_h2.markdown("**Assunto**")
                c_h3.markdown("**Dificuldade**")
                c_h4.markdown("**Tipo**")
                c_h5.markdown("**Objetivo**")

                regras = []
                for i in range(st.session_state.num_regras):
                    c1, c2, c3, c4, c5 = st.columns([0.1, 0.25, 0.2, 0.2, 0.25])
                    regras.append({
                        "qtd": c1.number_input(f"Qtd_{i}", 1, value=1, key=f"r_qtd_{i}", label_visibility="collapsed"), 
                        "assunto": c2.selectbox(f"Ass_{i}", obter_assuntos_da_disciplina(d_p), key=f"r_ass_{i}", label_visibility="collapsed"), 
                        "dificuldade": c3.selectbox(f"Dif_{i}", ["Todos", "Fácil", "Média", "Difícil"], key=f"r_dif_{i}", label_visibility="collapsed"), 
                        "tipo": c4.selectbox(f"Tip_{i}", ["Todos", "Múltipla", "V/F", "Discursiva", "Numérica"], key=f"r_tip_{i}", label_visibility="collapsed"),
                        "uso": c5.selectbox(f"Uso_{i}", ["Prova Oficial", "Lista de Treino", "Dojo / Sala", "Todos"], key=f"r_uso_{i}", label_visibility="collapsed")
                    })
                
                st.write("") 
                c_btn_r1, c_btn_r2, _ = st.columns([0.15, 0.15, 0.7])
                if c_btn_r1.button("➕ Regra", use_container_width=True): st.session_state.num_regras += 1; st.rerun()
                if c_btn_r2.button("➖ Regra", use_container_width=True) and st.session_state.num_regras > 1: st.session_state.num_regras -= 1; st.rerun()

            if st.button("🎲 Sortear Prova", type="primary", use_container_width=True):
                base, usados = [], []
                for r in regras:
                    tipo_mapeado = "Múltipla Escolha" if r['tipo'] == "Múltipla" else ("Verdadeiro ou Falso" if r['tipo'] == "V/F" else r['tipo'])
                    sorteadas = buscar_questoes_filtradas(d_p, r['qtd'], r['assunto'], r['dificuldade'], tipo_mapeado, True, usados, r['uso'])
                    base.extend(sorteadas)
                    usados.extend([q[0] for q in sorteadas])
                st.session_state.prova_atual = [{"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]} for q in base]
                st.rerun()
        else:
            todas_q = buscar_questoes_filtradas(d_p)
            # A mágica aqui: o q[11] mostra a tag [Prova Oficial] ou [Lista de Treino] no menu dropdown!
            opcoes = {f"[{q[11]}] ID {q[0]} | {q[1][:50]}...": q for q in todas_q}
            
            sel = st.multiselect("Selecione as questões (Cuidado para não vazar questões de Prova Oficial em Listas!):", list(opcoes.keys()))
            if st.button("➕ Adicionar à Prova/Lista"):
                for n in sel:
                    q = opcoes[n]
                    if q[0] not in [x['id'] for x in st.session_state.prova_atual]:
                        st.session_state.prova_atual.append({"id": q[0], "enunciado": q[1], "imagem": q[2], "pontos": q[3], "tipo": q[4], "gabarito": q[5], "espaco": q[6], "espaco_linhas": q[7], "dificuldade": q[8], "assunto": q[9], "gabarito_imagem": q[10]})
                st.rerun()

        if st.session_state.prova_atual:
            st.write("---")
            st.markdown("**🎛️ 4. Ajustes Finos da Prova**")
            pontos_totais, remover = 0, []
            for i, q in enumerate(st.session_state.prova_atual):
                with st.expander(f"Q{i+1} | {q['tipo']} | ID: {q['id']}"):
                    
                    # --- 1. EDIÇÃO DO ENUNCIADO ---
                    st.markdown("**💬 Enunciado**")
                    key_enun_adj = f"adj_enun_{i}_{q['id']}"
                    if key_enun_adj not in st.session_state: st.session_state[key_enun_adj] = q['enunciado']
                    
                    col_adj_1, col_adj_2, col_adj_3, col_adj_4 = st.columns([0.15, 0.15, 0.15, 0.55])
                    with col_adj_1:
                        with st.popover("🖋️ Estilo", use_container_width=True):
                            c_b = st.columns(2)
                            for k, (l, cmd) in enumerate(estilo): c_b[k%2].button(l, key=f"adj_e_{i}_{k}", on_click=injetar_texto, args=(cmd, key_enun_adj))
                    with col_adj_2:
                        with st.popover("🧮 f(x)", use_container_width=True):
                            tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                            with tg: 
                                cg = st.columns(4)
                                for k, (l, cmd) in enumerate(gregas): cg[k%4].button(l, key=f"adj_g_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            with tm: 
                                cm = st.columns(3)
                                for k, (l, cmd) in enumerate(matematica): cm[k%3].button(l, key=f"adj_m_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            with tc: 
                                cc = st.columns(3)
                                for k, (l, cmd) in enumerate(calculo): cc[k%3].button(l, key=f"adj_c_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            with tf: 
                                cf = st.columns(1)
                                for k, (l, cmd) in enumerate(fluidos): cf[0].button(l, key=f"adj_f_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                            with tt: 
                                ct = st.columns(1)
                                for k, (l, cmd) in enumerate(termo): ct[0].button(l, key=f"adj_t_{i}_{k}", on_click=injetar_direto, args=(cmd, key_enun_adj))
                    with col_adj_3:
                        with st.popover("🖼️ Imagem", use_container_width=True):
                            adj_img_up = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"adj_img_{i}_{q['id']}", label_visibility="collapsed")

                    novo_enun = st.text_area("Enunciado", key=key_enun_adj, height=100, label_visibility="collapsed")
                    st.session_state.prova_atual[i]['enunciado'] = novo_enun
                    
                    img_temp = q.get('imagem')
                    if adj_img_up:
                        img_temp = sanitizar_nome(f"temp_prova_{adj_img_up.name}")
                        with open(img_temp, "wb") as f: f.write(adj_img_up.getbuffer())
                        st.session_state.prova_atual[i]['imagem'] = img_temp
                    
                    if q.get('imagem') or adj_img_up:
                        ci1, ci2 = st.columns(2)
                        if q.get('imagem'): ci1.image(q['imagem'], caption="🖼️ Imagem Original", width=150)
                        if adj_img_up: ci2.image(adj_img_up, caption="🆕 Imagem para a Prova", width=150)

                    if novo_enun.strip():
                        st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(novo_enun)}', unsafe_allow_html=True)
                    
                    # --- 2. EDIÇÃO DO GABARITO E ALTERNATIVAS (PADRONIZADO) ---
                    novo_gab = q.get('gabarito', '')
                    img_gab_temp = q.get('gabarito_imagem') 
                    adj_ig_up = None 
                    
                    alts_modificadas_adj = [] 
                    alts_imagens_novas_adj = {}

                    if q['tipo'] == "Múltipla Escolha":
                        st.write("---")
                        st.markdown("**💡 Resposta (Alternativas)**")
                        st.caption("⚠️ Atenção: Edições nas alternativas SÓ vão para o PDF se você clicar em 'Atualizar no Banco' abaixo.")
                        
                        import sqlite3
                        with sqlite3.connect('banco_provas.db') as c_temp:
                            cursor_t = c_temp.cursor()
                            cursor_t.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q['id'],))
                            alts_q_adj = cursor_t.fetchall()
                            
                        n_opt_key_adj = f"adj_n_opt_{i}_{q['id']}"
                        if n_opt_key_adj not in st.session_state: st.session_state[n_opt_key_adj] = max(len(alts_q_adj), 4)
                        
                        cb1, cb2, _ = st.columns([0.12, 0.12, 0.76])
                        if cb1.button("➕ Linha", key=f"adj_add_alt_{i}"): st.session_state[n_opt_key_adj] += 1; st.rerun()
                        if cb2.button("➖ Linha", key=f"adj_rm_alt_{i}") and st.session_state[n_opt_key_adj] > 2: st.session_state[n_opt_key_adj] -= 1; st.rerun()

                        letras_adj = "ABCDEFGHIJ"
                        for j in range(st.session_state[n_opt_key_adj]):
                            with st.container(border=True):
                                c_chk, c_est, c_fx, c_img = st.columns([0.1, 0.25, 0.25, 0.25])
                                corr_v = bool(alts_q_adj[j][1]) if j < len(alts_q_adj) else False
                                corr = c_chk.checkbox(letras_adj[j], value=corr_v, key=f"adj_c_alt_{i}_{j}")
                                
                                k_alt = f"adj_t_alt_v_{i}_{j}"
                                if k_alt not in st.session_state: st.session_state[k_alt] = alts_q_adj[j][0] if j < len(alts_q_adj) else ""
                                
                                with c_est:
                                    with st.popover("🖋️ Estilo", use_container_width=True):
                                        c_b = st.columns(2)
                                        for idx, (l, cmd) in enumerate(estilo): c_b[idx%2].button(l, key=f"adj_ae_{i}_{j}_{idx}", on_click=injetar_texto, args=(cmd, k_alt))
                                with c_fx:
                                    with st.popover("🧮 f(x)", use_container_width=True):
                                        tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                        with tg: 
                                            cg_g = st.columns(4)
                                            for idx, (l, cmd) in enumerate(gregas): cg_g[idx%4].button(l, key=f"adj_ag_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tm: 
                                            cg_m = st.columns(3)
                                            for idx, (l, cmd) in enumerate(matematica): cg_m[idx%3].button(l, key=f"adj_am_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tc: 
                                            cg_c = st.columns(3)
                                            for idx, (l, cmd) in enumerate(calculo): cg_c[idx%3].button(l, key=f"adj_ac_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tf: 
                                            cg_f = st.columns(1)
                                            for idx, (l, cmd) in enumerate(fluidos): cg_f[0].button(l, key=f"adj_af_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        with tt: 
                                            cg_t = st.columns(1)
                                            for idx, (l, cmd) in enumerate(termo): cg_t[0].button(l, key=f"adj_at_{i}_{j}_{idx}", on_click=injetar_direto, args=(cmd, k_alt))
                                        
                                with c_img:
                                    with st.popover("🖼️ Imagem", use_container_width=True):
                                        up_ia = st.file_uploader("Trocar", type=["png", "jpg", "jpeg"], key=f"adj_ia_{i}_{j}", label_visibility="collapsed")

                                txt_a = st.text_input("Texto", key=k_alt, label_visibility="collapsed")
                                if txt_a.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(txt_a)}', unsafe_allow_html=True)
                                
                                if (j < len(alts_q_adj) and alts_q_adj[j][2]) or up_ia:
                                    cia = st.columns(2)
                                    if j < len(alts_q_adj) and alts_q_adj[j][2]: cia[0].image(alts_q_adj[j][2], width=80, caption="Atual")
                                    if up_ia: cia[1].image(up_ia, width=80, caption="Nova")

                                alts_imagens_novas_adj[j] = up_ia if up_ia else (alts_q_adj[j][2] if j < len(alts_q_adj) else None)
                                alts_modificadas_adj.append((txt_a, corr))

                    elif q['tipo'] == "Verdadeiro ou Falso":
                        import sqlite3
                        with sqlite3.connect('banco_provas.db') as c_temp:
                            cursor_t = c_temp.cursor()
                            cursor_t.execute('SELECT texto, correta, imagem FROM alternativas WHERE questao_id = ? ORDER BY id', (q['id'],))
                            alts_q_adj = cursor_t.fetchall()
                            
                        idx_banco = 0 if any(a[0] == "Verdadeiro" and a[1] for a in alts_q_adj) else 1
                        st.write("---")
                        st.markdown("**💡 Resposta (V/F)**")
                        st.caption("⚠️ Atenção: Alterações aqui SÓ vão para o PDF se você clicar em 'Atualizar no Banco'.")
                        resp = st.radio("Gabarito:", ["Verdadeiro", "Falso"], index=idx_banco, horizontal=True, key=f"adj_vf_{i}_{q['id']}", label_visibility="collapsed")
                        alts_modificadas_adj = [("Verdadeiro", resp == "Verdadeiro"), ("Falso", resp == "Falso")]

                    elif q['tipo'] == "Numérica":
                        st.write("---")
                        st.markdown("**💡 Resposta Exata (Numérica)**")
                        val_atual = int(novo_gab) if str(novo_gab).isdigit() else 0
                        novo_gab_num = st.number_input("Valor (0 a 99):", min_value=0, max_value=99, step=1, value=val_atual, key=f"adj_num_{i}_{q['id']}")
                        novo_gab = str(novo_gab_num).zfill(2)
                        st.session_state.prova_atual[i]['gabarito'] = novo_gab
                        
                        c_g1, c_gi = st.columns([0.85, 0.15])
                        with c_g1: st.info(f"O gabarito na prova será: **{novo_gab}**")
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                adj_ig_up = st.file_uploader("Upload", type=["png","jpg","jpeg"], key=f"adj_ig_num_{i}_{q['id']}", label_visibility="collapsed")
                                
                    elif q['tipo'] == "Discursiva":
                        st.write("---")
                        st.markdown("**💡 Resolução Detalhada:**")
                        key_gab_adj = f"adj_gab_{i}_{q['id']}"
                        if key_gab_adj not in st.session_state: st.session_state[key_gab_adj] = str(novo_gab)
                        
                        c_ge, c_gf, c_gi, _ = st.columns([0.15, 0.15, 0.15, 0.55])
                        with c_ge:
                            with st.popover("🖋️ Estilo", use_container_width=True):
                                c_gb = st.columns(2)
                                for k, (l, cmd) in enumerate(estilo): c_gb[k%2].button(l, key=f"adj_ge_{i}_{k}", on_click=injetar_texto, args=(cmd, key_gab_adj))
                        with c_gf:
                            with st.popover("🧮 f(x)", use_container_width=True):
                                tg, tm, tc, tf, tt = st.tabs(["αβγ", "Mat", "Cálc", "🌊", "🔥"])
                                with tg: 
                                    cg_g = st.columns(4)
                                    for k, (l, cmd) in enumerate(gregas): cg_g[k%4].button(l, key=f"adj_gg_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tm: 
                                    cg_m = st.columns(3)
                                    for k, (l, cmd) in enumerate(matematica): cg_m[k%3].button(l, key=f"adj_gm_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tc: 
                                    cg_c = st.columns(3)
                                    for k, (l, cmd) in enumerate(calculo): cg_c[k%3].button(l, key=f"adj_gc_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tf: 
                                    c_f = st.columns(1)
                                    for k, (l, cmd) in enumerate(fluidos): c_f[0].button(l, key=f"adj_gf_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                                with tt: 
                                    c_t = st.columns(1)
                                    for k, (l, cmd) in enumerate(termo): c_t[0].button(l, key=f"adj_gt_{i}_{k}", on_click=injetar_direto, args=(cmd, key_gab_adj))
                        with c_gi:
                            with st.popover("🖼️ Imagem", use_container_width=True):
                                adj_ig_up = st.file_uploader("Upload", type=["png","jpg","jpeg"], key=f"adj_ig_disc_{i}_{q['id']}", label_visibility="collapsed")
                                
                        novo_gab_edit = st.text_area("Gabarito", key=key_gab_adj, height=120, label_visibility="collapsed")
                        st.session_state.prova_atual[i]['gabarito'] = novo_gab_edit
                        novo_gab = novo_gab_edit
                        
                        if novo_gab.strip(): st.markdown(f'<span style="color:#3498db;">↳</span> {gerar_preview_web(novo_gab)}', unsafe_allow_html=True)
                    
                    # Lógica de processamento de imagem compartilhada
                    if adj_ig_up:
                        img_gab_temp = sanitizar_nome(f"temp_gab_{adj_ig_up.name}")
                        with open(img_gab_temp, "wb") as f: f.write(adj_ig_up.getbuffer())
                        st.session_state.prova_atual[i]['gabarito_imagem'] = img_gab_temp
                        
                    if q['tipo'] in ["Discursiva", "Numérica"] and (q.get('gabarito_imagem') or adj_ig_up):
                        cg1, cg2 = st.columns(2)
                        if q.get('gabarito_imagem'): cg1.image(q['gabarito_imagem'], caption="Atual no Banco", width=150)
                        if adj_ig_up: cg2.image(adj_ig_up, caption="Nova", width=150)

                    st.write("---")

                    # --- 3. CONTROLES: NOTA, SALVAR NO BANCO E REMOVER ---
                    c_e1, c_e2, c_e_dup, c_e3 = st.columns([0.25, 0.25, 0.25, 0.25], vertical_alignment="bottom")
                    novo_pt = c_e1.number_input("Pontos", value=float(q['pontos']), step=0.5, key=f"prev_pt_gen_{i}")
                    
                    if c_e2.button("🆙 Atualizar", key=f"sv_banco_{i}_{q['id']}", use_container_width=True):
                        with sqlite3.connect('banco_provas.db') as conn_upd:
                            conn_upd.execute("UPDATE questoes SET enunciado=?, pontos=?, imagem=?, gabarito_imagem=?, gabarito_discursivo=? WHERE id=?", 
                                             (novo_enun, novo_pt, img_temp, img_gab_temp, novo_gab, q['id']))
                            
                            if q['tipo'] in ["Múltipla Escolha", "Verdadeiro ou Falso"]:
                                conn_upd.execute('DELETE FROM alternativas WHERE questao_id = ?', (q['id'],))
                                for j, (t, co) in enumerate(alts_modificadas_adj):
                                    img_obj = alts_imagens_novas_adj.get(j)
                                    img_bd = None
                                    if hasattr(img_obj, 'getbuffer'):
                                        nome_f = sanitizar_nome(img_obj.name)
                                        with open(nome_f, "wb") as f:
                                            f.write(img_obj.getbuffer())
                                        img_bd = nome_f
                                    else: img_bd = img_obj
                                    conn_upd.execute('INSERT INTO alternativas (questao_id, texto, correta, imagem) VALUES (?, ?, ?, ?)', (q['id'], t, co, img_bd))
                            
                            conn_upd.commit()
                        st.success(f"Questão atualizada no banco de dados!")

                    if c_e_dup.button("🧬 Clonar", key=f"dup_p_gen_{i}_{q['id']}", use_container_width=True, help="Duplica a questão aqui mesmo"):
                        import random
                        nova_q = q.copy() 
                        nova_q['id'] = f"{q['id']}_copy_{random.randint(1000,9999)}"
                        st.session_state.prova_atual.insert(i + 1, nova_q)
                        st.rerun()
                    
                    if c_e3.button("🗑️ Remover", key=f"rm_p_gen_{i}", use_container_width=True): 
                        remover.append(i)
                    
                    st.session_state.prova_atual[i]['pontos'] = novo_pt
                    pontos_totais += novo_pt
                    
                    

            if remover:
                for idx in sorted(remover, reverse=True): st.session_state.prova_atual.pop(idx)
                st.rerun()
            
            st.info(f"**Total de Pontos da Prova:** {pontos_totais}")
            st.write("---")
            col_emb1, col_emb2 = st.columns(2)
            opt_emb_q = col_emb1.checkbox("Embaralhar Ordem das Questões", value=True)
            opt_emb_a = col_emb2.checkbox("Embaralhar Alternativas", value=True)

            if st.button("✅ Confirmar e Gerar PDFs", type="primary", use_container_width=True):
                st.session_state.arquivos = {} 
                if modo_id == "Em Branco (Sem Nome/RA)":
                    df_alunos = pd.DataFrame({'NOME': ['__________________________'] * q_a, 'RA': ['__________'] * q_a})
                elif modo_id == "Usar Turma Cadastrada" and alunos_selecionados_df is not None:
                    df_alunos = alunos_selecionados_df
                elif modo_id == "Upload Temporário de Lista" and arquivo_lista is not None:
                    if arquivo_lista.name.endswith('.xlsx'): df_alunos = pd.read_excel(arquivo_lista)
                    else: df_alunos = pd.read_csv(arquivo_lista, sep=None, engine='python')
                    df_alunos.columns = df_alunos.columns.str.strip().str.upper()
                    colunas_lidas = df_alunos.columns.tolist()
                    sinonimos_nome = ['NOME', 'ALUNO', 'CANDIDATO', 'ESTUDANTE', 'NOME COMPLETO']
                    sinonimos_ra = ['RA', 'REGISTRO', 'MATRICULA', 'ID']
                    col_n = next((col for col in colunas_lidas if col in sinonimos_nome), None)
                    col_r = next((col for col in colunas_lidas if col in sinonimos_ra), None)
                    if not col_n or not col_r:
                        st.error("🚫 Erro na Planilha! Colunas NOME e RA não identificadas.")
                        st.stop()
                    df_alunos = df_alunos.rename(columns={col_n: 'NOME', col_r: 'RA'}).dropna(subset=['NOME', 'RA'])

                nome_logo = "logo.png"
                if logo_up is not None:
                    nome_logo = sanitizar_nome(logo_up.name)
                    with open(nome_logo, "wb") as f: f.write(logo_up.getbuffer())
                elif not os.path.exists("logo.png"):
                    cv2.imwrite("logo.png", np.zeros((100, 100, 3), dtype=np.uint8) + 255)

                pdfs_provas, pdfs_gabaritos = [], []

                for index, linha in df_alunos.iterrows():
                    aluno_nome = str(linha['NOME'])
                    aluno_ra = str(linha['RA']).replace('.0', '')
                    v_num = index % q_v 
                    let_v = "ABCDEFGHIJ"[v_num]
                    
                    if modo_id == "Em Branco (Sem Nome/RA)":
                        id_unico = f"{index+1:03d}" 
                        let_v = f"{let_v}-{id_unico}"
                        titulo_gabarito = f"Cópia {id_unico} (Prova em Branco)"
                    else:
                        titulo_gabarito = f"Aluno(a): {aluno_nome} (RA: {aluno_ra})"
                    
                    q_list = list(st.session_state.prova_atual)
                    if opt_emb_q: random.shuffle(q_list)
                        
                    d_pdf, qr_obj = [], {}
                    for idx, q_item in enumerate(q_list, 1):
                        en_s = escapar_latex(q_item['enunciado'])
                        img_q = q_item.get('imagem')
                        if img_q and not os.path.exists(img_q): img_q = None 
                        gab_txt = escapar_latex(str(q_item.get('gabarito', '')))
                        if gab_txt == "None": gab_txt = ""
                        gab_img = q_item.get('gabarito_imagem')
                        if gab_img and not os.path.exists(gab_img): gab_img = None
                        
                        # NOVO: O tipo da questão é salvo com segurança no dicionário d_pdf para ajudar o gabarito
                        
                        if q_item['tipo'] == "Múltipla Escolha":
                            if opt_emb_a: alts = buscar_e_embaralhar_alternativas(q_item['id'])
                            else: alts = buscar_alternativas_originais(q_item['id'])
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "ABCDE"[ia]
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}|ME" # Na Múltipla Escolha
                        elif q_item['tipo'] == "Verdadeiro ou Falso":
                            alts = buscar_alternativas_originais(q_item['id']) 
                            l_c, t_alts = "", []
                            for ia, (txt, corr, img_alt) in enumerate(alts): 
                                if img_alt and not os.path.exists(img_alt): img_alt = None
                                t_alts.append({"texto": escapar_latex(txt), "imagem": img_alt, "correta": corr})
                                if corr: l_c = "V" if ia == 0 else "F" 
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": t_alts, "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{l_c}|{q_item['pontos']}|VF" # No Verdadeiro ou Falso
                        elif q_item['tipo'] == "Numérica":
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = f"{str(q_item['gabarito']).zfill(2)}|{q_item['pontos']}|NUM" # Na Numérica
                                
                        else:
                            d_pdf.append({"enunciado": en_s, "imagem": img_q, "pontos": q_item['pontos'], "tipo": q_item['tipo'], "alternativas": [], "espaco": q_item['espaco'], "espaco_linhas": q_item['espaco_linhas'], "resposta_esperada": gab_txt, "gabarito_imagem": gab_img})
                            qr_obj[idx] = "DISC|0.0|DISC" # Na Discursiva
                    
                    sufixo_arquivo = f"{sanitizar_nome(aluno_ra)}_{index}"
                    cod_secreto = f"0{v_num + 1}"
                    if modo_id == "Em Branco (Sem Nome/RA)": cod_secreto += f"-{id_unico}"
                    
                    tipo_salvar = "Treino" if "Treino" in tipo_doc_gen else "Oficial"
                    dados_qrcode = {"ra": aluno_ra, "nome": aluno_nome, "v": let_v, "gab": qr_obj, "d": d_p, "tp": tipo_salvar}
                    qr_fn = f"qr_{sufixo_arquivo}.png"
                    qrcode.make(json.dumps(dados_qrcode)).save(qr_fn)

                    cab = {
                        "titulo_documento": escapar_latex(titulo_doc), "logo_path": nome_logo, "instituicao": escapar_latex(inst_nome),
                        "professor_nome": escapar_latex(prof_nome), "disciplina_nome": escapar_latex(d_p), "data": escapar_latex(data_p),
                        "turma": escapar_latex(turma_p), "curso": escapar_latex(curs), "instrucoes_texto": escapar_latex(instrucoes),
                        "num_copias": 1, "qr_path": qr_fn, "versao_letra": let_v, "colunas": num_colunas,
                        "aluno_nome": escapar_latex(aluno_nome) if modo_id != "Em Branco (Sem Nome/RA)" else "",
                        "aluno_ra": aluno_ra if modo_id != "Em Branco (Sem Nome/RA)" else "",
                        "titulo_gabarito": escapar_latex(titulo_gabarito), "codigo_secreto": cod_secreto
                    }
                    env = configurar_jinja()
                    n_p = f"Prova_{sufixo_arquivo}"
                    with open(f"{n_p}.tex", 'w', encoding='utf-8') as f: f.write(env.get_template('template_profissional.tex').render(**cab, questoes=d_pdf))
                    if compilar_latex_mac(f"{n_p}.tex"): pdfs_provas.append(f"{n_p}.pdf")
                        
                    n_g = f"Gabarito_{sufixo_arquivo}"
                    with open(f"{n_g}.tex", 'w', encoding='utf-8') as f: f.write(env.get_template('template_gabarito.tex').render(**cab, questoes=d_pdf))
                    if compilar_latex_mac(f"{n_g}.tex"): pdfs_gabaritos.append(f"{n_g}.pdf")

                if pdfs_provas:
                    st.info("📦 Unificando provas...")
                    # Usamos 'empty' no pagestyle para não numerar o merge (as provas já têm sua numeração)
                    tex_merge_provas = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{pdfpages}\n\\begin{document}\n\\pagestyle{empty}\n"
                    for p in pdfs_provas: 
                        # 'fitpaper' ajusta o PDF final ao tamanho real da prova gerada
                        tex_merge_provas += f"\\includepdf[pages=-, fitpaper=true]{{{p}}}\n"
                    tex_merge_provas += "\\end{document}"
                    
                    with open("Lote_Provas_Turma.tex", 'w', encoding='utf-8') as f: f.write(tex_merge_provas)
                    if compilar_latex_mac("Lote_Provas_Turma.tex"): 
                        st.session_state.arquivos['provas'] = "Lote_Provas_Turma.pdf"

                if pdfs_gabaritos:
                    st.info("✅ Unificando gabaritos...")
                    # Configuramos o documento LaTeX para o merge
                    tex_merge_gabs = "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{pdfpages}\n\\begin{document}\n\\pagestyle{empty}\n"
                    
                    for p in pdfs_gabaritos: 
                        # O 'fitpaper=true' garante que tabelas largas não sejam cortadas
                        tex_merge_gabs += f"\\includepdf[pages=-, fitpaper=true]{{{p}}}\n"
                    
                    tex_merge_gabs += "\\end{document}"
                    
                    # Guardamos o ficheiro .tex e compilamos
                    with open("Lote_Gabaritos_Turma.tex", 'w', encoding='utf-8') as f: 
                        f.write(tex_merge_gabs)
                    
                    if compilar_latex_mac("Lote_Gabaritos_Turma.tex"): 
                        st.session_state.arquivos['gabaritos'] = "Lote_Gabaritos_Turma.pdf"

                for p in pdfs_provas + pdfs_gabaritos:
                    if os.path.exists(p): os.remove(p)
                st.success("Processamento finalizado com sucesso!")
                limpar_arquivos_temporarios()

        if st.session_state.get("arquivos"):
            st.write("---")
            st.markdown("**📦 Arquivos Prontos**")
            c_dl1, c_dl2 = st.columns(2)
            arq_provas = st.session_state.arquivos.get('provas')
            if arq_provas and os.path.exists(arq_provas):
                with open(arq_provas, "rb") as pdf_file:
                    c_dl1.download_button(label="📥 Baixar Lote de PROVAS (Único PDF)", data=pdf_file, file_name=f"Provas_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", type="primary", use_container_width=True, key="btn_dl_provas_mestre")
                    
            arq_gabs = st.session_state.arquivos.get('gabaritos')
            if arq_gabs and os.path.exists(arq_gabs):
                with open(arq_gabs, "rb") as pdf_file:
                    c_dl2.download_button(label="🗝️ Baixar Lote de GABARITOS (Único PDF)", data=pdf_file, file_name=f"Gabaritos_Turma_{datetime.now().strftime('%Y%m%d')}.pdf", use_container_width=True, key="btn_dl_gabs_mestre")
    
    # --- SUB-ABA 1.4: CORREÇÃO AUTOMÁTICA (O SEU MOTOR OPENCV) ---
    with sub_corr:
        renderizar_aba_correcao()
# =========================================================================
# PILAR 3: SEMESTRES E TURMAS (A OPERAÇÃO REAL + BOLETIM)
# =========================================================================
with aba_fabrica:
    renderizar_aba_fabrica()
# =========================================================================
# PILAR 4: SEMESTRES E TURMAS (A OPERAÇÃO REAL + BOLETIM)
# =========================================================================
with aba_turmas:
    renderizar_aba_turmas() # <--- ESSA ÚNICA LINHA SUBSTITUI AS 400 QUE VOCÊ APAGOU!
# =========================================================================
# PILAR 5: GESTÃO DE AULA - VERSÃO INTEGRAL E SINCRONIZADA (V9.X)
# =========================================================================
with aba_sala:
    renderizar_aba_sala() # <--- ESSA ÚNICA LINHA SUBSTITUI TUDO!