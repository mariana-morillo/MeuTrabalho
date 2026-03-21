import streamlit as st
import pandas as pd
import sqlite3
import re
from datetime import datetime

# 1.1 Sincronização de Interface (Fix do emoji cortado e cards padronizados)
st.set_page_config(page_title="Portal do Aluno FAM", page_icon="🎓", layout="centered")

st.markdown("""
<style>
    /* 1. MATA O ESPAÇO EM BRANCO NO TOPO */
    .block-container {
        padding-top: 1.5rem !important;
        margin-top: 0rem !important;
    }

    /* 2. ESCONDE O MENU PADRÃO DO STREAMLIT (Dá cara de App de verdade) */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    /* 3. CORRIGE O CORTE DA ABA SEM PRECISAR DA BARRA INVERTIDA */
    button[data-baseweb="tab"] { 
        padding-top: 10px !important; 
        margin-top: 5px !important;
    }
    
    /* 4. CARD PADRÃO */
    .card-padrao {
        background-color: #ffffff; border: 1px solid #e0e6ed;
        border-radius: 12px; padding: 20px; margin-bottom: 15px;
        box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.02);
    }
    .card-titulo { color: #2c3e50; font-size: 18px; font-weight: bold; margin-bottom: 10px; border-bottom: 2px solid #f0f2f6; padding-bottom: 5px; }
    /* 5. ESMAGA O ESPAÇO ENTRE OS BLOCOS E BOTÕES */
    [data-testid="stVerticalBlock"] {
        gap: 0.5rem !important;
    }

    /* 6. REDUZ A MARGEM GIGANTE DAS LINHAS DIVISÓRIAS */
    hr {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# 1.2 O Motor de Preview (Copiado fielmente do seu código principal)
def gerar_preview_web(texto):
    if not texto: return ""
    prev = texto
    # Suporte total ao seu padrão £...£ (Negrito, Itálico, Cores, Tamanhos)
    prev = re.sub(r'£\\textbf\{(.*?)\}£', r'<b>\1</b>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textit\{(.*?)\}£', r'<i>\1</i>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\textcolor\{(.*?)\}\{(.*?)\}£', r'<span style="color:\1;">\2</span>', prev, flags=re.DOTALL)
    prev = re.sub(r'£\\Large\{(.*?)\}£', r'<span style="font-size:24px; font-weight:bold;">\1</span>', prev, flags=re.DOTALL)
    # Suporte a Listas
    prev = re.sub(r'£\\begin\{itemize\}(.*?)\\end\{itemize\}£', r'<ul>\1</ul>', prev, flags=re.DOTALL)
    prev = re.sub(r'\\item\s*(.*?)(?=<li>|</ul>|$)', r'<li>\1</li>', prev, flags=re.DOTALL)
    return prev.replace('£', '')

# --- PADRONIZAÇÃO DO BANCO DE DADOS (HELPERS) ---
DB_PATH = 'banco_provas.db'

def buscar_dados(query, params=()):
    """Função única para buscar dados e retornar um DataFrame"""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(query, conn, params=params)

def executar_comando(query, params=()):
    """Função única para inserir ou atualizar dados (INSERT/UPDATE)"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(query, params)
        conn.commit()
# --- ADICIONE ESTAS 4 LINHAS AQUI ---
try:
    executar_comando("ALTER TABLE diario ADD COLUMN disciplina TEXT DEFAULT 'Geral'")
except:
    pass
# ------------------------------------
# Setup Inicial de Tabelas (Usando o helper)
executar_comando('''CREATE TABLE IF NOT EXISTS correcoes_detalhadas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, disciplina TEXT, prova_nome TEXT, questao_num INTEGER, status TEXT, feedback_ia TEXT)''')
try: executar_comando("ALTER TABLE alunos ADD COLUMN avatar_opts TEXT DEFAULT ''")
except: pass
try: executar_comando("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial'")
except: pass
executar_comando("UPDATE alunos SET avatar_opts = '' WHERE avatar_opts LIKE '%7.x%' OR avatar_opts LIKE '%accessories%'")

# --- RECUPERAÇÃO DE SESSÃO ("Lembrar de mim") ---
if 'aluno_logado_ra' not in st.session_state:
    # Se o RA estiver salvo no link da página, ele puxa direto
    if "ra" in st.query_params:
        st.session_state.aluno_logado_ra = st.query_params["ra"]
    else:
        st.session_state.aluno_logado_ra = None

# --- 4. ÁREA DE LOGIN ---
with st.sidebar:
    st.markdown("### 🔑 Acesso Seguro")
    if not st.session_state.aluno_logado_ra:
        ra_login = st.text_input("Seu RA:")
        senha_login = st.text_input("Sua Senha:", type="password")
        
        # A NOVA CAIXINHA DE CONFIANÇA
        lembrar = st.checkbox("Lembrar de mim (Mantenha conectado)")
        
        if st.button("🚀 Entrar", use_container_width=True):
            res = buscar_dados("SELECT ra FROM alunos WHERE ra = ? AND senha = ?", (ra_login, senha_login))
            if not res.empty:
                st.session_state.aluno_logado_ra = ra_login
                
                # Se ele marcou a caixinha, salva o RA no link (como um cookie)
                if lembrar:
                    st.query_params["ra"] = ra_login
                
                st.rerun()
            else: st.error("RA ou Senha incorretos.")
    else:
        st.success("✅ Conectado")
        if st.button("🚪 Sair da Conta", use_container_width=True):
            # Limpa a sessão e apaga o rastro do link
            st.session_state.aluno_logado_ra = None
            if "ra" in st.query_params:
                del st.query_params["ra"]
            st.rerun()

# --- ÁREA LOGADA ---
if st.session_state.aluno_logado_ra:
    ra_ativo = st.session_state.aluno_logado_ra
    aluno = buscar_dados("SELECT * FROM alunos WHERE ra = ?", (ra_ativo,))
    
    st.header(f"Bem-vindo, {aluno['nome'].values[0]}! 👋")
    
    # 🟢 A NOVA ARQUITETURA DE NAVEGAÇÃO
    t_guia, t_perfil, t_discs = st.tabs([
        " 🏠 Guia do Portal", 
        "👤 Meu Perfil", 
        "🏫 Minhas Disciplinas"
    ])
    # ==========================================
    # ABA 1: BOAS VINDAS E GUIA
    # ==========================================
    with t_guia:
        st.markdown("""
        <div class="card-padrao">
            <div class="card-titulo"> 🏠 Como usar o seu Portal</div>
            Bem-vindo ao seu ambiente virtual de aprendizagem. Aqui você tem o controle da sua jornada:
            <ul>
                <li><b>👤 Meu Perfil:</b> Atualize seu e-mail, conte para a professora como você aprende melhor (TDAH, dificuldades) e crie seu Avatar do Dojo.</li>
                <li><b>🏫 Minhas Disciplinas:</b> Escolha a matéria que está cursando para mergulhar no conteúdo. Lá dentro você encontra o plano de ensino, faltas, ranking e notas.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    # ==========================================
    # ABA 2: PERFIL DO ALUNO (Integração Mão Dupla)
    # ==========================================
    with t_perfil:
        st.markdown("### 👤 Configurações Pessoais")
        
        # --- BLOCO 1: DADOS PESSOAIS E SENHA (TOPO) ---
        with st.container(border=True):
            st.markdown("**📝 Meus Dados (Visível para a Professora)**")
            
            # Divide apenas os campos de texto para não ficarem compridos demais
            col_email, col_senha1, col_senha2 = st.columns([0.4, 0.3, 0.3])
            
            # Garantia de extração segura de dados
            email_atual = aluno['email'].values[0] if hasattr(aluno['email'], 'values') else aluno['email']
            obs_atual = aluno['observacoes'].values[0] if hasattr(aluno['observacoes'], 'values') else aluno['observacoes']
            
            val_email = str(email_atual) if pd.notna(email_atual) else ""
            val_obs = str(obs_atual) if pd.notna(obs_atual) else ""
            
            n_email = col_email.text_input("E-mail de Contato:", value=val_email)
            n_s = col_senha1.text_input("Nova Senha (opcional):", type="password")
            c_s = col_senha2.text_input("Confirmação da Senha:", type="password")
            
            n_obs = st.text_area("Anotações Pedagógicas Privadas (Ex: TDAH, dificuldades específicas...):", value=val_obs, height=100)
                
            if st.button("💾 Salvar Dados e Senha", type="primary", use_container_width=True):
                if n_s:
                    if n_s == c_s and len(n_s) >= 4:
                        executar_comando("UPDATE alunos SET email=?, observacoes=?, senha=? WHERE ra=?", (n_email, n_obs, n_s, ra_ativo))
                        st.success("Dados e senha atualizados!")
                    else: st.error("As senhas não conferem ou são muito curtas.")
                else:
                    executar_comando("UPDATE alunos SET email=?, observacoes=? WHERE ra=?", (n_email, n_obs, ra_ativo))
                    st.success("Dados atualizados! A professora Mariana já pode ver essas informações.")
        # --- BLOCO 2: ESTÚDIO DE AVATAR (LARGURA TOTAL ABAIXO) ---
        estilo_atual = aluno['avatar_style'].values[0]
        
        
        with st.container(border=True):
                st.markdown("### 🎨 Estúdio de Avatares")
                
                # 1. AVATAR EM DESTAQUE NO TOPO
                img_prev = st.empty()
                btn_salvar = st.empty()
                
                # 2. BARRA DE ÍCONES (Abas)
                t_base, t_rosto, t_cabelo, t_roupa, t_acess = st.tabs(["⚙️ Estilo", "😀 Rosto", "💇 Cabelo", "👕 Roupa", "👓 Extra"])
                
                with t_base:
                    c1, c2 = st.columns([0.7, 0.3])
                    # Lista limpa, apenas com os 4 estilos principais
                    novo_est = c1.selectbox("Estilo Base:", ["bottts", "avataaars", "micah", "lorelei"], 
                                         index=["bottts", "avataaars", "micah", "lorelei"].index(estilo_atual) if estilo_atual in ["bottts", "avataaars", "micah", "lorelei"] else 0)
                    cor_bg = c2.color_picker("Cor do Fundo:", "#e8f4f8")
                
                opts = [f"backgroundType=solid", f"backgroundColor={cor_bg.replace('#','')}"]

                # --- 👨‍💼 AVATAAARS ---
                if novo_est == "avataaars":
                    m_cab = {"Longo e Liso":"straight01", "Longo e Liso 2":"straight02", "Longo e Liso 3":"straightAndStrand","Lateral Raspada":"shavedSides","Longo e Ondulado":"bigHair", "Longo e Ondulado 2":"curvy","Dreads":"dreads","Dreads 2":"dreads01","Dreads 3":"dreads02","Bob":"bob","Long Bob":"longButNotTooLong","Mia Wallace":"miaWallace","Encaracolado":"curly","Curto e Liso":"shortFlat","Curto e Liso 2":"shortRound","Curto ":"shortWaved","Curto 2 ":"shaggy","Curto e Cacheado":"shortCurly", "Mullet":"shaggyMullet","Afro":"fro","Afro 2":"froBand","Coque":"bun","Topete":"frizzle", "Careca":"sides","Frida":"frida", "O César":"theCaesar","O César 2":"theCaesarAndSidePart","Touca 1":"winterHat1", "Touca 2":"winterHat02", "Touca 3":"winterHat03","Touca 4":"winterHat04","Boné":"hat", "Turbante":"turban","Hijab":"hijab"}
                    m_rou = {"Camisa":"shirtCrewNeck", "Camisa 2":"shirtScoopNeck","Camisa gola V":"shirtVNeck","Camisa Estampada":"graphicShirt","Moletom":"hoodie", "Macacão":"overall","Blazer":"blazerAndShirt", "Blazer 2":"blazerAndSweater", "Sweater":"collarAndSweater"}
                    m_boc = {"Preocupada":"concerned", "Padrão":"default","Desacreditada":"disbelief","Comendo":"eating","Careta":"grimace", "Triste":"sad","Gritando":"screamOpen", "Séria":"serious", "Sorrindo":"smile", "Língua":"tongue", "Brilhante":"twinkle", "Vômito":"vomit"}
                    m_bar = {"Nenhuma":"NONE", "Barba Rala":"beardLight", "Barba Majestosa":"beardMajestic", "Barba Média":"beardMedium", "Bigode Fancy":"moustacheFancy", "Bigode Magnum":"moustacheMagnum"}
                    m_acc = {"Nenhum": "NONE", "Tapa-olho": "eyepatch", "Kurt": "kurt", "Prescrição 01": "prescription01", "Prescrição 02": "prescription02", "Redondo": "round", "Óculos de Sol": "sunglasses", "Wayfarers": "wayfarers"}
                    m_olhos_av = {"Padrão": "default", "Fechados": "closed", "Chorando": "cry", "Revirando": "eyeRoll", "Feliz": "happy", "Corações": "hearts", "Olhando pro lado": "side", "Semicerrados": "squint", "Surpreso": "surprised", "Piscando": "wink", "Piscada Maluca": "winkWacky", "Tonto (X)": "xDizzy"}

                    with t_rosto:
                        c1, c2, c3 = st.columns(3)
                        sel_olhos_av = c1.selectbox("Olhos:", list(m_olhos_av.keys()))
                        sel_m = c2.selectbox("Boca:", list(m_boc.keys()))
                        c_skin = c3.color_picker("Cor da Pele:", "#f8d25c")

                    with t_cabelo:
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_c = c1.selectbox("Cabelo/Chapéu:", list(m_cab.keys()))
                        c_hair = c2.color_picker("Cor Cabelo:", "#2c1b18")
                        
                        c3, c4 = st.columns([0.7, 0.3])
                        sel_b = c3.selectbox("Barba/Bigode:", list(m_bar.keys()))
                        cor_barba = c4.color_picker("Cor da Barba:", "#2c1b18")

                    with t_roupa:
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_r = c1.selectbox("Roupa:", list(m_rou.keys()))
                        c_cloth = c2.color_picker("Cor Roupa:", "#65c9ff")

                    with t_acess:
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_acc = c1.selectbox("Acessórios:", list(m_acc.keys()))
                        cor_acessorio = c2.color_picker("Cor Acessório:", "#3c4f5c")
                    
                    opts += [f"top={m_cab[sel_c]}", f"clothing={m_rou[sel_r]}", f"hairColor={c_hair.replace('#','')}", f"clothesColor={c_cloth.replace('#','')}", f"skinColor={c_skin.replace('#','')}", f"mouth={m_boc[sel_m]}", f"eyes={m_olhos_av[sel_olhos_av]}"]
                    if m_bar[sel_b] != "NONE": opts += [f"facialHair={m_bar[sel_b]}", f"facialHairColor={cor_barba.replace('#','')}", "facialHairProbability=100"]
                    # Acessórios (Óculos, etc.)
                    if m_acc[sel_acc] == "NONE":
                        opts.append("accessoriesProbability=0") # Força a tirar os óculos!
                    else:
                        opts.append(f"accessories={m_acc[sel_acc]}")
                        opts.append(f"accessoriesColor={cor_acessorio.replace('#','')}")
                        opts.append("accessoriesProbability=100")

                # --- 🤖 BOTTTS ---
                elif novo_est == "bottts":
                    # Mapeamento completo baseado na documentação v9 oficial
                    m_face_bot = {"Redondo 1":"round01", "Redondo 2":"round02", "Quadrado 1":"square01", "Quadrado 2":"square02", "Quadrado 3":"square03", "Quadrado 4":"square04"}
                    m_olhos_bot = {"Redondo":"round", "Feliz":"happy", "Corações":"hearts", "Robocop":"robocop", "Sensor":"sensor", "Eva":"eva", "Saltados":"bulging", "Tonto":"dizzy", "Armação 1":"frame1", "Armação 2":"frame2", "Brilhante":"glow", "Armação Redonda 1":"roundFrame01", "Armação Redonda 2":"roundFrame02", "Sombra":"shade01"}
                    m_boca_bot = {"Sorriso 1":"smile01", "Sorriso 2":"smile02", "Dentes":"bite", "Quadrada 1":"square01", "Quadrada 2":"square02", "Diagrama":"diagram", "Grade 1":"grill01", "Grade 2":"grill02", "Grade 3":"grill03"}
                    m_topo_bot = {"Antena":"antenna", "Antena Curta":"antennaCrooked", "Lâmpada":"bulb01", "Lâmpada Brilhante 1":"glowingBulb01", "Lâmpada Brilhante 2":"glowingBulb02", "Chifres":"horns", "Luzes":"lights", "Pirâmide":"pyramid", "Radar":"radar"}
                    m_laterais_bot = {"Antena 1":"antenna01", "Antena 2":"antenna02", "Cabos 1":"cables01", "Cabos 2":"cables02", "Redondo":"round", "Quadrado":"square", "Quadrado Assimétrico":"squareAssymetric"}
                    m_tex_bot = {"Lisa":"NONE", "Circuitos":"circuits", "Pontos":"dots", "Camuflado 1":"camo01", "Camuflado 2":"camo02", "Sujo 1":"dirty01", "Sujo 2":"dirty02"}
                    
                    # Aba: Rosto
                    with t_rosto:
                        c1, c2, c3 = st.columns(3)
                        sel_f = c1.selectbox("Formato do Rosto:", list(m_face_bot.keys()))
                        sel_o = c2.selectbox("Olhos:", list(m_olhos_bot.keys()))
                        sel_b = c3.selectbox("Boca:", list(m_boca_bot.keys()))
                    
                    # Aba: Cabelo (Usado para Topo e Laterais do Robô)
                    with t_cabelo:
                        c1, c2 = st.columns(2)
                        sel_t = c1.selectbox("Topo (Cabelo):", list(m_topo_bot.keys()))
                        sel_l = c2.selectbox("Laterais (Orelhas):", list(m_laterais_bot.keys()))
                    
                    # Aba: Roupa (Usado para Textura e Cor da Lataria)
                    with t_roupa:
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_x = c1.selectbox("Textura da Lataria:", list(m_tex_bot.keys()))
                        # No Bottts, baseColor é o que pinta o rosto/corpo principal
                        c_lat = c2.color_picker("Cor da Face:", "#039be5")
                        
                    # Construção da URL com todos os parâmetros do Bottts
                    opts += [
                        f"face={m_face_bot[sel_f]}",
                        f"eyes={m_olhos_bot[sel_o]}", 
                        f"mouth={m_boca_bot[sel_b]}", 
                        f"top={m_topo_bot[sel_t]}",
                        f"sides={m_laterais_bot[sel_l]}",
                        f"baseColor={c_lat.replace('#','')}"
                    ]
                    
                    # Garante que a textura e as laterais aparecem sempre se escolhidas
                    opts.append("sidesProbability=100")
                    if m_tex_bot[sel_x] != "NONE": 
                        opts.append(f"texture={m_tex_bot[sel_x]}")
                        opts.append("textureProbability=100")

                # --- 🎨 MICAH ---
                elif novo_est == "micah":
                    # Mapeamento oficial v9.x com base nos prints (incluindo o erro ortográfico do DiceBear no nariz!)
                    m_olhos_m = {"Padrão": "eyes", "Sombra": "eyesShadow", "Redondos": "round", "Sorridentes": "smiling", "Sorridentes c/ Sombra": "smilingShadow"}
                    m_sobr_m = {"Baixas": "down", "Cílios p/ Baixo": "eyelashesDown", "Cílios p/ Cima": "eyelashesUp", "Altas": "up"}
                    m_boca_m = {"Triste": "frown", "A Rir": "laughing", "Nervosa": "nervous", "Biquinho": "pucker", "Muito Triste": "sad", "Sorriso": "smile", "Sorriso de Lado": "smirk", "Surpresa": "surprised"}
                    m_nariz_m = {"Curvo": "curve", "Pontiagudo": "pointed", "Redondo": "tound"} # 'tound' exato como no print
                    m_orelhas_m = {"Juntas": "attached", "Separadas": "detached"}
                    m_barba_m = {"Nenhuma": "NONE", "Barba Cheia": "beard", "Barba Por Fazer": "scruff"}
                    m_roupa_m = {"Gola Polo": "collared", "Gola Careca": "crew", "Casaco Aberto": "open"}
                    m_oculos_m = {"Nenhum": "NONE", "Redondos": "round", "Quadrados": "square"}
                    m_brincos_m = {"Nenhum": "NONE", "Argola": "hoop", "Ponto": "stud"}
                    m_cabelo_m = {"Careca": "NONE", "Curto": "fonze", "Doug Funny": "dougFunny", "Longo": "full", "Danny Phantom": "dannyPhantom", "Careca brilhando": "mrClean", "Moicano": "mrT","Chanel": "pixie","Turbante": "turban"}
                    
                    with t_rosto:
                        c1, c2, c3 = st.columns(3)
                        c_skn = c1.color_picker("Cor da Pele:", "#f9c9b6")
                        sel_olho = c2.selectbox("Olhos:", list(m_olhos_m.keys()))
                        c_sombra = c3.color_picker("Cor da Sombra:", "#e0ddff")
                        
                        c4, c5, c6 = st.columns(3)
                        sel_sobr = c4.selectbox("Sobrancelhas:", list(m_sobr_m.keys()))
                        sel_boca = c5.selectbox("Boca:", list(m_boca_m.keys()))
                        sel_nariz = c6.selectbox("Nariz:", list(m_nariz_m.keys()))
                        
                        sel_orelha = st.selectbox("Orelhas:", list(m_orelhas_m.keys()))
                        

                    with t_cabelo:
                        # CABELO
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_cab = c1.selectbox("Cabelo:", list(m_cabelo_m.keys()))
                        c_cab = c2.color_picker("Cor do Cabelo:", "#000000")
                        
                        st.markdown("---")
                        
                        # BARBA (Agora juntos e fáceis de achar!)
                        c3, c4 = st.columns([0.7, 0.3])
                        sel_barba = c3.selectbox("Barba/Bigode:", list(m_barba_m.keys()))
                        c_barba = c4.color_picker("Cor da Barba:", "#000000")
                        
                    with t_roupa:
                        c1, c2 = st.columns([0.7, 0.3])
                        sel_r = c1.selectbox("Roupa:", list(m_roupa_m.keys()))
                        c_clt = c2.color_picker("Cor da Roupa:", "#9b59b6")
                        
                    with t_acess:
                        c1, c2 = st.columns(2)
                        sel_ocu = c1.selectbox("Óculos:", list(m_oculos_m.keys()))
                        c_ocu = c2.color_picker("Cor dos Óculos:", "#000000") 
                        
                        c3, c4 = st.columns(2)
                        sel_brinco = c3.selectbox("Brincos:", list(m_brincos_m.keys()))
                        c_brinco = c4.color_picker("Cor dos Brincos:", "#e0ddff")

                    # Compilação Segura dos Parâmetros Base
                    opts += [
                        f"baseColor={c_skn.replace('#','')}",
                        f"eyes={m_olhos_m[sel_olho]}",
                        f"eyeShadowColor={c_sombra.replace('#','')}",
                        f"eyebrows={m_sobr_m[sel_sobr]}",
                        f"mouth={m_boca_m[sel_boca]}",
                        f"nose={m_nariz_m[sel_nariz]}",
                        f"ears={m_orelhas_m[sel_orelha]}",
                        f"shirt={m_roupa_m[sel_r]}",
                        f"shirtColor={c_clt.replace('#','')}"
                    ]
                    
                    # Lógica do Cabelo (Com o truque para Careca)
                    if m_cabelo_m[sel_cab] == "NONE":
                        opts.append("hairProbability=0")
                    else:
                        opts.append(f"hair={m_cabelo_m[sel_cab]}")
                        opts.append("hairProbability=100")
                        opts.append(f"hairColor={c_cab.replace('#','')}")
                        
                    # Lógica Opcional: Barba
                    if m_barba_m[sel_barba] != "NONE":
                        opts.append(f"facialHair={m_barba_m[sel_barba]}")
                        opts.append("facialHairProbability=100")
                        opts.append(f"facialHairColor={c_barba.replace('#','')}")
                        
                    # Lógica Opcional: Acessórios (Óculos e Brincos)
                    if m_oculos_m[sel_ocu] != "NONE":
                        opts.append(f"glasses={m_oculos_m[sel_ocu]}")
                        opts.append("glassesProbability=100")
                        opts.append(f"glassesColor={c_ocu.replace('#','')}")
                        
                    # --- Lógica Opcional: Brincos ---
                    if m_brincos_m[sel_brinco] == "NONE":
                        opts.append("earringsProbability=0")
                    else:
                        opts.append(f"earrings={m_brincos_m[sel_brinco]}")
                        opts.append("earringsProbability=100")
                        opts.append(f"earringColor={c_brinco.replace('#','')}")

                # --- 👩 LORELEI ---
                elif novo_est == "lorelei":
                    # Geração dinâmica dos dicionários para poupar dezenas de linhas de código!
                    m_rosto_l = {f"Rosto {i:02d}": f"variant{i:02d}" for i in range(1, 5)}
                    m_olhos_l = {f"Olhos {i:02d}": f"variant{i:02d}" for i in range(1, 25)}
                    # Junta as bocas felizes e tristes no mesmo menu
                    m_boca_l = {**{f"Feliz {i:02d}": f"happy{i:02d}" for i in range(1, 19)}, **{f"Triste {i:02d}": f"sad{i:02d}" for i in range(1, 10)}}
                    m_nariz_l = {f"Nariz {i:02d}": f"variant{i:02d}" for i in range(1, 7)}
                    m_cabelo_l = {"Careca": "NONE", **{f"Cabelo {i:02d}": f"variant{i:02d}" for i in range(1, 49)}}
                    m_barba_l = {"Nenhuma": "NONE", "Barba 1": "variant01", "Barba 2": "variant02"}
                    m_sardas_l = {"Nenhuma": "NONE", "Sardas": "variant01"}
                    m_oculos_l = {"Nenhum": "NONE", **{f"Óculos {i:02d}": f"variant{i:02d}" for i in range(1, 6)}}
                    m_brincos_l = {"Nenhum": "NONE", "Brinco 1": "variant01", "Brinco 2": "variant02", "Brinco 3": "variant03"}

                    with t_rosto:
                        c1, c2, c3 = st.columns(3)
                        sel_rosto = c1.selectbox("Formato Rosto:", list(m_rosto_l.keys()))
                        sel_nariz = c2.selectbox("Nariz:", list(m_nariz_l.keys()))
                        sel_boca = c3.selectbox("Boca:", list(m_boca_l.keys()))

                        c4, c5 = st.columns(2)
                        sel_olho = c4.selectbox("Olhos:", list(m_olhos_l.keys()))
                        sel_sardas = c5.selectbox("Sardas:", list(m_sardas_l.keys()))

                    with t_cabelo:
                        c1, c2 = st.columns(2)
                        sel_cab = c1.selectbox("Cabelo:", list(m_cabelo_l.keys()))
                        sel_barba = c2.selectbox("Barba:", list(m_barba_l.keys()))

                    with t_roupa:
                        st.info("🎨 O estilo Lorelei é focado em traços em preto e branco. Não possui personalização de roupas ou cores.")

                    with t_acess:
                        c1, c2 = st.columns(2)
                        sel_oculos = c1.selectbox("Óculos:", list(m_oculos_l.keys()))
                        sel_brinco = c2.selectbox("Brincos:", list(m_brincos_l.keys()))

                    # Montagem segura da URL (Sem parâmetros de cor)
                    opts += [
                        f"head={m_rosto_l[sel_rosto]}",
                        f"nose={m_nariz_l[sel_nariz]}",
                        f"mouth={m_boca_l[sel_boca]}",
                        f"eyes={m_olhos_l[sel_olho]}"
                    ]

                    # Lógica do Cabelo
                    if m_cabelo_l[sel_cab] == "NONE":
                        opts.append("hairProbability=0")
                    else:
                        opts.append(f"hair={m_cabelo_l[sel_cab]}")
                        opts.append("hairProbability=100")

                    # Barba
                    if m_barba_l[sel_barba] != "NONE":
                        opts.append(f"beard={m_barba_l[sel_barba]}")
                        opts.append("beardProbability=100")

                    # Sardas (Lógica corrigida de probabilidade)
                    if m_sardas_l[sel_sardas] == "NONE":
                        opts.append("frecklesProbability=0")
                    else:
                        opts.append(f"freckles={m_sardas_l[sel_sardas]}")
                        opts.append("frecklesProbability=100")

                    # Óculos
                    if m_oculos_l[sel_oculos] != "NONE":
                        opts.append(f"glasses={m_oculos_l[sel_oculos]}")
                        opts.append("glassesProbability=100")

                    # Brincos
                    if m_brincos_l[sel_brinco] != "NONE":
                        opts.append(f"earrings={m_brincos_l[sel_brinco]}")
                        opts.append("earringsProbability=100")

                # ==========================================
                # RENDERIZAÇÃO FINAL 
                # ==========================================
                final_opts_str = "&" + "&".join(opts) if opts else ""
                url_v9 = f"https://api.dicebear.com/9.x/{novo_est}/svg?seed={str(ra_ativo).strip()}{final_opts_str}"
                
                # A tag <img> agora está limpa, sem a variável {pixel_css}
                img_prev.markdown(f"""
                    <div style='text-align:center; padding:15px; background:white; border-radius:15px; border:1px solid #ddd; margin-bottom:10px;'>
                        <img src='{url_v9}' style='width:100%; max-width:250px; border-radius:10px;' onerror="this.onerror=null; this.src='https://api.dicebear.com/9.x/initials/svg?seed=Error';">
                    </div>
                """, unsafe_allow_html=True)
                
                if btn_salvar.button("💾 Salvar Visual", type="primary", use_container_width=True):
                    with sqlite3.connect('banco_provas.db') as c:
                        c.execute("UPDATE alunos SET avatar_style=?, avatar_opts=? WHERE ra=?", (novo_est, final_opts_str, ra_ativo))
                    st.success("Visual salvo!")
                    st.rerun()

        
    # ==========================================
    # ABA 3: MINHAS DISCIPLINAS (Ambiente Central)
    # ==========================================
    with t_discs:
         # Extrai o ID do aluno com segurança
        id_seguro = int(aluno['id'].iloc[0]) if isinstance(aluno, pd.DataFrame) else int(aluno['id'])
        
        # Busca as disciplinas e turmas vinculadas ao aluno
        df_m = buscar_dados("SELECT m.turma_id, m.disciplina, t.nome as turma_nome FROM matriculas_disciplina m JOIN turmas t ON m.turma_id = t.id WHERE m.aluno_id = ?", (id_seguro,))
        
        if not df_m.empty:
            # 1. Seleção de Disciplina
            d_ativa = st.selectbox("📚 Selecione a Disciplina para navegar:", df_m['disciplina'].unique())
            t_id_ativa = df_m[df_m['disciplina'] == d_ativa]['turma_id'].iloc[0]
            ra_aluno = str(aluno['ra'].iloc[0] if isinstance(aluno, pd.DataFrame) else aluno['ra'])
            # --- 🚨 NOVO: PAINEL DE ALERTAS AUTOMÁTICO ---
            try:
                df_alertas = buscar_dados(f"SELECT nome_avaliacao, data_prevista FROM planejamento_notas WHERE turma_id = {int(t_id_ativa)} AND disciplina = '{d_ativa}' AND data_prevista IS NOT NULL AND data_prevista != ''")
                if not df_alertas.empty:
                    df_alertas['data_dt'] = pd.to_datetime(df_alertas['data_prevista'], format='%d/%m/%Y', errors='coerce').dt.date
                    hoje = datetime.today().date()
                    futuras = df_alertas[df_alertas['data_dt'] >= hoje].sort_values('data_dt')
                    
                    if not futuras.empty:
                        proxima = futuras.iloc[0]
                        dias_faltando = (proxima['data_dt'] - hoje).days
                        
                        if dias_faltando == 0:
                            st.error(f"🚨 **É HOJE!** Hoje tem **{proxima['nome_avaliacao']}**! Boa sorte!")
                        elif dias_faltando <= 7:
                            st.warning(f"⚠️ **Atenção!** Faltam só {dias_faltando} dias para a **{proxima['nome_avaliacao']}** (Data: {proxima['data_prevista']}).")
                        else:
                            st.info(f"📅 **Próximo evento:** {proxima['nome_avaliacao']} em {proxima['data_prevista']} (Faltam {dias_faltando} dias).")
            except Exception:
                pass # Se houver erro nas datas, passa direto sem travar o portal
            # --- 🥋 NOVO: LÓGICA DE FAIXAS DO DOJO ---
            def calcular_faixa(xp):
                if xp < 10: return "Faixa Branca ⚪", "#ecf0f1", "#2c3e50"
                elif xp < 30: return "Faixa Azul 🔵", "#3498db", "white"
                elif xp < 50: return "Faixa Roxa 🟣", "#9b59b6", "white"
                elif xp < 80: return "Faixa Marrom 🟤", "#8b4513", "white"
                else: return "Faixa Preta ⚫", "#2c3e50", "white"

            # --- RANKING DO DOJO COM FAIXAS (SIDEBAR) ---
            with st.sidebar:
                st.write("---")
                st.subheader("🥋 Ranking do Dojo")
                query_ranking = f"SELECT a.nome, SUM(l.pontos) as total_xp, a.avatar_style, a.ra, a.avatar_opts FROM alunos a JOIN logs_comportamento l ON a.ra = l.aluno_ra WHERE a.turma_id = {t_id_ativa} GROUP BY a.ra ORDER BY total_xp DESC LIMIT 5"
                try:
                    df_rank = buscar_dados(query_ranking)
                    if not df_rank.empty:
                        for i, r_row in df_rank.iterrows():
                            medalha = ["🥇", "🥈", "🥉", "4º", "5º"][i]
                            opts = r_row['avatar_opts'] if pd.notna(r_row['avatar_opts']) else ""
                            url_mini = f"https://api.dicebear.com/9.x/{r_row['avatar_style']}/svg?seed={r_row['ra']}{opts}"
                            
                            # Descobre qual é a faixa do aluno
                            faixa_nome, bg_color, txt_color = calcular_faixa(r_row['total_xp'])
                            
                            # Card do aluno gamificado
                            st.markdown(f"""
                            <div style='display:flex;align-items:center;margin-bottom:10px; background:white; padding:8px; border-radius:10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #f0f2f6;'>
                                <span style='font-size:20px;margin-right:10px; width:25px; text-align:center;'>{medalha}</span>
                                <img src='{url_mini}' width='40' style='border-radius:50%;margin-right:10px;background:#f0f2f6;'>
                                <div style='flex-grow:1; line-height: 1.3;'>
                                    <b style='font-size:14px; color:#2c3e50;'>{r_row['nome'].split()[0]}</b><br>
                                    <span style='background:{bg_color}; color:{txt_color}; font-size:10px; padding:2px 6px; border-radius:10px; font-weight:bold;'>{faixa_nome}</span>
                                    <span style='color:#2ecc71; font-weight:bold; font-size:12px; float:right;'>{r_row['total_xp']:.1f} XP</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else: st.caption("Ainda sem pontos nesta turma. Comece os treinos!")
                except Exception: 
                    pass
            # AS 5 SUB-ABAS DO AMBIENTE ACADÊMICO
            sub_plano, sub_aula, sub_atividades, sub_faltas, sub_dojo, sub_notas = st.tabs([
                "📄 Plano de Ensino", 
                "🏭 O que vimos na aula", 
                "🎯 Minhas Atividades",
                "🙋 Presença", 
                "🎮 Meu Dojo",
                "📊 Meu Boletim"
            ])

            # --- 3.1 PLANO DE ENSINO (Layout de Acordeão com Títulos Institucionais) ---
            with sub_plano:
                plano_df = buscar_dados("SELECT * FROM modelos_ensino WHERE titulo_modelo=?", (d_ativa,))
                if not plano_df.empty:
                    p = plano_df.iloc[0]
                    
                    def formata_texto(txt):
                        if pd.isna(txt) or not str(txt).strip(): return "_Não cadastrado pela professora._"
                        return str(txt).replace('\n', '\n\n')

                    st.markdown(f"### 📄 Plano de Ensino: {d_ativa}")
                    
                    # Acordeão de Tópicos
                    with st.expander("📖 Ementa", expanded=True):
                        st.info(formata_texto(p.get('ementa')))
                    
                    with st.expander("🏁 Objetivos Gerais"):
                        st.markdown(formata_texto(p.get('objetivos_gerais')))

                    with st.expander("🏅 Competências e Habilidades"):
                        st.markdown(formata_texto(p.get('competencias')))

                    with st.expander("🎓 Perfil do Egresso"):
                        st.markdown(formata_texto(p.get('egresso')))

                    with st.expander("📁 Conteúdo Programático"):
                        cont = formata_texto(p.get('conteudo_programatico'))
                        st.markdown(re.sub(r'(?<!^)\s+(?=\d+(?:\.\d+)*\s)', r'\n\n**•** ', cont))

                    with st.expander("♟️ Metodologia de Ensino"):
                        st.markdown(formata_texto(p.get('metodologia')))

                    with st.expander("🪄 Recursos Didáticos"):
                        st.markdown(formata_texto(p.get('recursos')))
                        
                    with st.expander("🏠 Atividades Práticas (APS)"):
                        st.markdown(formata_texto(p.get('aps')))

                    with st.expander("📈 Sistema de Avaliação"):
                        st.error(formata_texto(p.get('avaliacao')))
                    
                    st.markdown("##### 📚 Referências")
                    with st.expander("📘 Referência Básica"):
                        st.markdown(formata_texto(p.get('bib_basica')))
                    with st.expander("📗 Referência Complementar"):
                        st.markdown(formata_texto(p.get('bib_complementar')))
                    if pd.notna(p.get('outras_ref')) and str(p.get('outras_ref')).strip():
                        with st.expander("📙 Outras Referências"):
                            st.markdown(formata_texto(p.get('outras_ref')))
                else:
                    st.info("O Plano de Ensino desta disciplina ainda está sendo processado.")

            # --- 3.2 AULAS, MATERIAIS E DÚVIDAS (NOVO LAYOUT) ---
            with sub_aula:
                # 1. CRIAR TABELA DE DÚVIDAS SE NÃO EXISTIR (Garantia anti-erro)
                try:
                    with sqlite3.connect('banco_provas.db') as c_duv:
                        c_duv.execute('''CREATE TABLE IF NOT EXISTS duvidas_alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, aluno_ra TEXT, data TEXT, mensagem TEXT, respondida BOOLEAN DEFAULT 0)''')
                except Exception: 
                    pass

                st.markdown("#### 🏭 Central de Aulas e Materiais")
                
                # 2. DIVIDINDO EM 3 SUB-ABAS INTERNAS
                aba_linha, aba_biblio, aba_duvidas = st.tabs(["🗺️ Linha do Tempo", "📂 Biblioteca (Materiais)", "📩 Caixinha de Dúvidas"])
                
                query_aulas = f"""
                    SELECT c.*, d.conteudo_real 
                    FROM cronograma_detalhado c 
                    LEFT JOIN diario_conteudo d ON c.turma_id = d.turma_id AND c.disciplina = d.disciplina AND c.data = d.data 
                    WHERE c.turma_id={t_id_ativa} AND c.disciplina='{d_ativa}' 
                    ORDER BY c.num_aula
                """
                try: 
                    aulas_df = buscar_dados(query_aulas)
                except Exception: 
                    aulas_df = pd.DataFrame()

                # --- SUB-ABA 1: LINHA DO TEMPO ORIGINAL ---
                with aba_linha:
                    if not aulas_df.empty:
                        for _, r in aulas_df.iterrows():
                            concluida = pd.notna(r.get('conteudo_real')) and str(r.get('conteudo_real')).strip() != ""
                            icon = "✅" if concluida else "📅"
                            data_aula = r['data']
                            
                            with st.expander(f"{icon} Aula {r['num_aula']} ({data_aula}) - {r['tema']}"):
                                
                                # --- RESUMO DO DIA ---
                                col_d1, col_d2, col_d3 = st.columns([0.4, 0.3, 0.3])
                                with col_d1:
                                    st.markdown(f"**📖 Diário da Professora:**")
                                    if concluida: st.info(gerar_preview_web(str(r['conteudo_real'])))
                                    else: st.caption("_Diário ainda não preenchido._")

                                with col_d2:
                                    st.markdown("**📌 Meu Status:**")
                                    try:
                                        frequencia = buscar_dados("SELECT status FROM diario WHERE aluno_ra=? AND data=? AND turma_id=?", (ra_aluno, data_aula, int(t_id_ativa)))
                                        ativ_sala = buscar_dados("SELECT entregou FROM atividades_sala WHERE aluno_ra=? AND data=? AND disciplina=?", (ra_aluno, data_aula, d_ativa))
                                        
                                        if not frequencia.empty:
                                            status_f = frequencia['status'].iloc[0]
                                            cor_f = "green" if status_f == "Presente" else "orange" if status_f == "Atrasado" else "red"
                                            st.markdown(f"Presença: <b style='color:{cor_f};'>{status_f}</b>", unsafe_allow_html=True)
                                        else: st.caption("Frequência não lançada.")

                                        if not ativ_sala.empty:
                                            fez = ativ_sala['entregou'].iloc[0]
                                            if fez == 1: st.markdown("Atividade: <b style='color:green;'>✅ Entregue</b>", unsafe_allow_html=True)
                                            else: st.markdown("Atividade: <b style='color:red;'>❌ Não entregue</b>", unsafe_allow_html=True)
                                        else: st.caption("Sem atividade registrada.")
                                    except Exception: 
                                        st.caption("Dados indisponíveis.")

                                with col_d3:
                                    st.markdown("**⭐ Feedback Dojo:**")
                                    try:
                                        dojo_feedback = buscar_dados("SELECT pontos, comentario FROM logs_comportamento WHERE aluno_ra = ? AND data = ? AND turma_id = ?", (ra_aluno, data_aula, int(t_id_ativa)))
                                        if not dojo_feedback.empty:
                                            for _, f in dojo_feedback.iterrows():
                                                cor = "green" if f['pontos'] > 0 else "red"
                                                st.markdown(f"<div style='border-left: 3px solid {cor}; padding-left: 8px; margin-bottom: 3px;'><small><b>{f['pontos']} pts</b>: {f['comentario']}</small></div>", unsafe_allow_html=True)
                                        else: st.caption("_Sem notas comportamentais._")
                                    except Exception: 
                                        st.caption("_Sem notas comportamentais._")

                                st.markdown("---")

                                # --- PLANEJAMENTO PEDAGÓGICO ---
                                st.markdown(f"**🎯 Objetivos de Aprendizagem:**")
                                st.write(r['objetivos_aula'] if pd.notna(r.get('objetivos_aula')) and str(r['objetivos_aula']).strip() else "_Aguardando definição da professora._")
                                
                                st.markdown(f"**📚 Conteúdo Detalhado:**")
                                if pd.notna(r.get('conteudo_detalhado')) and str(r['conteudo_detalhado']).strip():
                                    st.write(gerar_preview_web(r['conteudo_detalhado']))
                                else:
                                    st.write("_Aguardando definição da professora._")

                                c_plan1, c_plan2 = st.columns(2)
                                with c_plan1:
                                    with st.container(border=True):
                                        st.markdown("**♟️ Metodologia de Ensino:**")
                                        st.caption(r['metodologia'] if pd.notna(r.get('metodologia')) and str(r['metodologia']).strip() else "_Padrão institucional._")
                                with c_plan2:
                                    with st.container(border=True):
                                        st.markdown("**🏠 Atividades Práticas (APS):**")
                                        st.caption(r['aps_aula'] if pd.notna(r.get('aps_aula')) and str(r['aps_aula']).strip() else "_Sem APS específica._")

                                st.markdown(f"**📑 Referências Específicas desta Aula:**")
                                if pd.notna(r.get('referencias_aula')) and str(r['referencias_aula']).strip():
                                    st.caption(r['referencias_aula'])
                                else:
                                    st.caption("_Consulte a bibliografia básica no Plano de Ensino da disciplina._")
                    else:
                        st.info("O cronograma detalhado ainda não está disponível.")

                # --- SUB-ABA 2: BIBLIOTECA (MATERIAIS ESTRUTURADOS) ---
                with aba_biblio:
                    st.markdown("**📚 Acervo de Arquivos da Disciplina**")
                    st.caption("Encontre todos os PDFs, slides e links do Overleaf de forma rápida para estudar.")
                    
                    if not aulas_df.empty:
                        # Filtra apenas as aulas que tem algum link preenchido
                        tem_slide = aulas_df['link_slides'].apply(lambda x: pd.notna(x) and str(x).strip() != "")
                        tem_overleaf = aulas_df['link_overleaf'].apply(lambda x: pd.notna(x) and str(x).strip() != "")
                        tem_extra = aulas_df['link_extras'].apply(lambda x: pd.notna(x) and str(x).strip() != "")
                        
                        materiais = aulas_df[tem_slide | tem_overleaf | tem_extra]
                        
                        if not materiais.empty:
                            for _, mat in materiais.iterrows():
                                with st.container(border=True):
                                    st.markdown(f"**Aula {mat['num_aula']} ({mat['data']}) - {mat['tema']}**")
                                    cm1, cm2, cm3 = st.columns(3)
                                    if pd.notna(mat.get('link_slides')) and str(mat['link_slides']).strip():
                                        cm1.link_button("📥 Baixar Slides", mat['link_slides'], use_container_width=True, type="primary")
                                    if pd.notna(mat.get('link_overleaf')) and str(mat['link_overleaf']).strip():
                                        cm2.link_button("🔗 Projeto Overleaf", mat['link_overleaf'], use_container_width=True)
                                    if pd.notna(mat.get('link_extras')) and str(mat['link_extras']).strip():
                                        cm3.link_button("🌐 Material Extra", mat['link_extras'], use_container_width=True)
                        else:
                            st.info("A professora ainda não disponibilizou materiais para download.")
                    else:
                        st.info("O cronograma de aulas ainda não foi gerado.")

                # --- SUB-ABA 3: CAIXINHA DE DÚVIDAS ---
                with aba_duvidas:
                    st.markdown("**📩 Fale Diretamente com a Professora**")
                    st.caption("Ficou com dúvida na hora de resolver a lista? Mande aqui que a mensagem cai no painel da professora!")
                    
                    duvida_txt = st.text_area("Escreva sua dúvida de forma clara:", height=130, placeholder="Ex: Professora, não entendi muito bem como aplicar a equação na lista 3...")
                    
                    if st.button("🚀 Enviar Dúvida", type="primary", use_container_width=True):
                        if duvida_txt.strip():
                            try:
                                with sqlite3.connect('banco_provas.db') as conn_duv:
                                    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    conn_duv.execute("INSERT INTO duvidas_alunos (turma_id, disciplina, aluno_ra, data, mensagem) VALUES (?, ?, ?, ?, ?)", (int(t_id_ativa), d_ativa, ra_aluno, agora, duvida_txt))
                                    conn_duv.commit()
                                st.success("✅ Dúvida enviada com sucesso! Fique de olho na próxima aula para o retorno.")
                            except Exception as e:
                                st.error(f"Erro ao enviar a dúvida. Detalhe: {e}")
                        else:
                            st.warning("Escreva algo antes de enviar!")

            # --- 3.3 ATIVIDADES E APS (Bancos Separados, XP e Correção) ---
            with sub_atividades:
                st.markdown("#### ✍️ Central de Estudo e APS")
                st.caption("Resolva as APS e vença os desafios de XP para subir no Ranking!")
                
                # Filtra aulas que têm atividades cadastradas
                df_ativ_base = aulas_df[aulas_df['atividades'].notna() & (aulas_df['atividades'] != "")]

                if not df_ativ_base.empty:
                    for _, ra in df_ativ_base.iterrows():
                        with st.container(border=True):
                            st.markdown(f"📅 **Aula {ra['num_aula']} - {ra['tema']}**")
                            assunto_aula = ra['tema']
                            ra_aluno = str(aluno['ra'].iloc[0] if isinstance(aluno, pd.DataFrame) else aluno['ra'])
                            
                            # --- PARTE A: LISTA DE APS (Fácil + Média) ---
                            st.markdown("##### 📝 Lista de APS (Fixação)")
                            questoes_aps = buscar_dados(
                                """SELECT * FROM questoes 
                                WHERE disciplina = ? AND assunto = ? 
                                AND dificuldade IN ('Fácil', 'Média') 
                                AND uso_quest != 'Prova Oficial'""", 
                                (d_ativa, assunto_aula)
                            )
                            
                            if not questoes_aps.empty:
                                with st.expander(f"📥 Ver Exercícios de Fixação ({len(questoes_aps)} questões)"):
                                    for idx_aps, r_aps in questoes_aps.iterrows():
                                        st.write(f"**Questão {idx_aps+1}:**")
                                        st.markdown(gerar_preview_web(r_aps['enunciado']), unsafe_allow_html=True)
                                    st.caption("⚠️ Estes exercícios devem ser entregues em folha separada.")
                            else:
                                st.caption("_Sem questões de APS para este tema._")

                            st.write("---")

                            # --- PARTE B: TREINAMENTO XP (Apenas Difíceis) ---
                            st.markdown("##### 🚀 Desafio de Elite (XP para o Dojo)")
                            if st.button(f"Iniciar Quiz Difícil: {assunto_aula}", key=f"btn_xp_{ra['num_aula']}"):
                                st.session_state[f"quiz_xp_{ra['num_aula']}"] = True

                            if st.session_state.get(f"quiz_xp_{ra['num_aula']}"):
                                # Busca as DIFÍCEIS blindando as Provas Oficiais
                                questoes_hard = buscar_dados(
                                    """SELECT * FROM questoes 
                                    WHERE disciplina = ? AND assunto = ? 
                                    AND dificuldade = 'Difícil' 
                                    AND uso_quest != 'Prova Oficial' 
                                    ORDER BY RANDOM() LIMIT 2""",
                                    (d_ativa, assunto_aula)
                                )
                                
                                if not questoes_hard.empty:
                                    with st.form(key=f"form_xp_{ra['num_aula']}"):
                                        respostas = {}
                                        for i_q, q_r in questoes_hard.iterrows():
                                            st.markdown(f"**Desafio {i_q+1}:** {gerar_preview_web(q_r['enunciado'])}", unsafe_allow_html=True)
                                            alts = buscar_dados("SELECT texto FROM alternativas WHERE questao_id = ?", (q_r['id'],))
                                            respostas[q_r['id']] = st.radio("Sua resposta:", alts['texto'].tolist(), key=f"ans_{q_r['id']}")
                                        
                                        if st.form_submit_button("Finalizar e Computar XP"):
                                            acertos = 0
                                            for i_q, q_r in questoes_hard.iterrows():
                                                gabarito = buscar_dados("SELECT texto FROM alternativas WHERE questao_id=? AND correta=1", (q_r['id'],))['texto'].iloc[0]
                                                if respostas[q_r['id']] == gabarito:
                                                    acertos += 1
                                            
                                            if acertos > 0:
                                                pontos = acertos * 1.0  # Dobro de pontos por ser difícil
                                                import sqlite3
                                                with sqlite3.connect('banco_provas.db') as conn_xp:
                                                    conn_xp.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", 
                                                                (ra_aluno, int(t_id_ativa), datetime.now().strftime("%d/%m/%Y"), pontos, f"Desafio XP: {assunto_aula}", "Acadêmico"))
                                                    conn_xp.commit()
                                                st.success(f"🔥 Sensacional! +{pontos} pontos de XP ganhos!")
                                                st.balloons()
                                            else:
                                                st.error("Desta vez não houve acertos. Revise o conteúdo e tente novamente!")
                                else:
                                    st.warning("Ainda não há desafios 'Difíceis' para este tema.")
                else:
                    st.info("Nenhuma atividade registrada para esta disciplina.")
        # --- 3.4 PRESENÇA (Frequência Detalhada) ---
            with sub_faltas:
                st.markdown("#### 🙋 Controle de Frequência")
                
                # Busca o histórico de faltas do aluno
                df_presenca = buscar_dados(
                    "SELECT data, status FROM diario WHERE aluno_ra=? AND turma_id=?",
                    (ra_aluno, int(t_id_ativa))
                )
                
                if not df_presenca.empty:
                    total_aulas = len(df_presenca)
                    faltas = len(df_presenca[df_presenca['status'].isin(['Ausente', 'Falta'])])
                    presencas = total_aulas - faltas
                    percentual = (presencas / total_aulas) * 100 if total_aulas > 0 else 100
                    
                    # Resumo em métricas
                    c_f1, c_f2, c_f3 = st.columns(3)
                    c_f1.metric("Total de Aulas", total_aulas)
                    c_f2.metric("Total de Faltas", faltas, delta_color="inverse")
                    c_f3.metric("Frequência", f"{percentual:.1f}%")

                    if faltas > 0:
                        st.warning("📅 **Datas em que você faltou:**")
                        # Lista apenas as datas de ausência
                        datas_faltas = df_presenca[df_presenca['status'].isin(['Ausente', 'Falta'])]['data'].tolist()
                        for data_f in datas_faltas:
                            st.write(f"❌ Falta registrada em: **{data_f}**")
                    else:
                        st.success("✅ Parabéns! Você não possui faltas nesta disciplina.")
                else:
                    st.info("O registro de chamadas ainda não foi iniciado.")

            # --- 3.5 DOJO (Histórico de Pontos e Comportamento) ---
            with sub_dojo: # Reutilizando a variável de aba ou ajuste para 'sub_dojo'
                st.markdown("#### 🥋 Meu Histórico no Dojo")
                
                # Busca todos os logs de comportamento/XP do aluno
                df_dojo_hist = buscar_dados(
                    "SELECT data, pontos, comentario, tipo FROM logs_comportamento WHERE aluno_ra=? AND turma_id=? ORDER BY id DESC",
                    (ra_aluno, int(t_id_ativa))
                )
                
                if not df_dojo_hist.empty:
                    total_xp = df_dojo_hist['pontos'].sum()
                    
                    c_d1, c_d2 = st.columns([0.3, 0.7])
                    with c_d1:
                        st.markdown(f"""
                            <div style="background-color:#f0f2f6; padding:20px; border-radius:15px; text-align:center; border: 2px solid #2ecc71;">
                                <span style="font-size:14px; color:#666;">SALDO TOTAL</span><br>
                                <span style="font-size:40px; font-weight:bold; color:#2ecc71;">{total_xp:.1f}</span><br>
                                <span style="font-size:16px; font-weight:bold;">XP</span>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with c_d2:
                        st.write("**📜 Histórico de Conquistas e Observações:**")
                        for _, log in df_dojo_hist.iterrows():
                            cor_ponto = "green" if log['pontos'] > 0 else "red"
                            simbolo = "🔼" if log['pontos'] > 0 else "🔽"
                            st.markdown(f"""
                                <div style="border-bottom: 1px solid #ddd; padding: 5px 0;">
                                    <small>{log['data']} | <b>{log['tipo']}</b></small><br>
                                    <span style="color:{cor_ponto};">{simbolo} <b>{log['pontos']:.1f} pts</b></span> - {log['comentario']}
                                </div>
                            """, unsafe_allow_html=True)
                else:
                    st.info("Você ainda não possui interações registradas no Dojo.")
            # --- 3.6 MEU BOLETIM UNIFICADO (TRANSPARENTE E MATEMÁTICO) ---
            with sub_notas:
                st.markdown("#### 📊 Meu Boletim e Desempenho")
                
                # 1. Puxa as Configurações de Pesos da Professora (AGORA NA TABELA CERTA!)
                try:
                    df_pesos = buscar_dados(f"SELECT nome_avaliacao, peso FROM planejamento_notas WHERE turma_id = {int(t_id_ativa)} AND disciplina = '{d_ativa}'")
                    pesos = dict(zip(df_pesos['nome_avaliacao'], df_pesos['peso'])) if not df_pesos.empty else {}
                    
                    nome_col_ativ = next((n for n in pesos.keys() if "(Dojo)" in str(n) or "Ativ" in str(n)), "Ativ (Dojo)")
                    peso_ativ = float(pesos.get(nome_col_ativ, 10.0))
                except Exception:
                    df_pesos = pd.DataFrame()
                    pesos = {}
                    nome_col_ativ, peso_ativ = "Ativ (Dojo)", 10.0

                st.write("---")
                col_boletim1, col_boletim2 = st.columns([0.55, 0.45])
                
                soma_produtos = 0.0
                soma_pesos = 0.0
                
                # --- LADO ESQUERDO: NOTAS OFICIAIS (Frações exatas) ---
                with col_boletim1:
                    st.markdown("**📝 Avaliações Oficiais**")
                    try:
                        df_notas = buscar_dados(f"SELECT avaliacao as Avaliação, nota as Nota FROM notas_flexiveis WHERE matricula='{ra_ativo}' AND disciplina='{d_ativa}' AND turma_id={t_id_ativa}")
                    except Exception:
                        df_notas = pd.DataFrame()
                        
                    extrato_provas = []
                    if not df_pesos.empty:
                        for _, row_p in df_pesos.iterrows():
                            av_nome = row_p['nome_avaliacao']
                            peso_pct = float(row_p['peso'])
                            
                            # Ignora a Atividade de Sala (Dojo), pois tem painel próprio na direita
                            if av_nome == nome_col_ativ: continue
                                
                            nota_lancada = "---"
                            pts_ganhos = "---"
                            
                            if not df_notas.empty and av_nome in df_notas['Avaliação'].values:
                                v_nota = df_notas.loc[df_notas['Avaliação'] == av_nome, 'Nota'].values[0]
                                if pd.notna(v_nota) and str(v_nota).strip() != "":
                                    try: 
                                        nota_num = float(v_nota)
                                        nota_lancada = f"{nota_num:.1f}"
                                        pts = (nota_num * peso_pct) / 100.0
                                        pts_ganhos = f"{pts:.2f}"
                                        
                                        soma_produtos += (nota_num * peso_pct)
                                        soma_pesos += peso_pct
                                    except: pass
                            
                            # Aqui o aluno vê que se o Lab vale 1 ponto (10%) dividido em 2, cada Lab vale 0.5 pts
                            extrato_provas.append({
                                "Avaliação": av_nome,
                                "Vale (pts)": f"{(peso_pct/10.0):.2f}",
                                "Sua Nota": nota_lancada,
                                "Pts Ganhos": pts_ganhos
                            })
                            
                        if extrato_provas:
                            df_ep = pd.DataFrame(extrato_provas)
                            st.dataframe(df_ep, hide_index=True, use_container_width=True)
                        else:
                            st.info("Plano de avaliações ainda não definido.")
                    else:
                        st.info("O planejamento de pesos ainda não foi salvo pela professora.")

                # --- LADO DIREITO: ATIVIDADES DE SALA ---
                with col_boletim2:
                    pts_totais_ativ = peso_ativ / 10.0
                    st.markdown(f"**📖 {nome_col_ativ}**")
                    
                    try:
                        df_sala = buscar_dados("SELECT data, entregou FROM atividades_sala WHERE aluno_ra = ? AND disciplina = ? ORDER BY data", (ra_ativo, d_ativa))
                    except Exception:
                        df_sala = pd.DataFrame()

                    if not df_sala.empty:
                        tot_aulas_dadas = df_sala['data'].nunique()
                        # A margem de erro/corte (25%) aplicada na quantidade de aulas
                        meta_entregas = tot_aulas_dadas - int(tot_aulas_dadas * 0.25) if tot_aulas_dadas > 0 else 0
                        entregas_aluno = df_sala[df_sala['entregou'] == 1].shape[0]

                        # A nota do aluno (0 a 10) proporcional às entregas (Limitado a 10)
                        nota_participacao = min(10.0, (entregas_aluno / meta_entregas) * 10.0) if meta_entregas > 0 else 0.0
                        pts_ganhos_ativ = (nota_participacao * peso_ativ) / 100.0

                        st.markdown(f"""
                        <div style="background-color:#f0f2f6; padding:15px; border-radius:8px; font-size:14px;">
                            📌 <b>Aulas com atividade:</b> {tot_aulas_dadas}<br>
                            🎯 <b>Sua Meta (75%):</b> {meta_entregas} entregas<br>
                            ✍️ <b>Você entregou:</b> {entregas_aluno}<br>
                            <hr style="margin: 10px 0;">
                            <b>Sua Nota Base (0 a 10):</b> {nota_participacao:.1f}<br>
                            👉 <b style="color:#2ecc71; font-size:15px;">Pontos Ganhos: {pts_ganhos_ativ:.2f} / {pts_totais_ativ:.2f} pts</b>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        soma_produtos += (nota_participacao * peso_ativ)
                        soma_pesos += peso_ativ
                        
                        with st.expander("Ver os dias das atividades"):
                            df_sala_view = df_sala.copy()
                            df_sala_view['Status'] = df_sala_view['entregou'].apply(lambda x: "✅ Entregue" if x == 1 else "❌ Faltou")
                            st.dataframe(df_sala_view[['data', 'Status']].rename(columns={'data': 'Data'}), hide_index=True, use_container_width=True)
                    else:
                        st.info("Nenhuma atividade de sala registrada ainda.")

                # --- CÁLCULO FINAL DA MÉDIA PONDERADA ---
                st.markdown("---")
                media_ponderada = (soma_produtos / soma_pesos) if soma_pesos > 0 else 0.0
                cor_media = "#2ecc71" if media_ponderada >= 6.0 else "#e74c3c"
                
                lbl_media = "MÉDIA PARCIAL" if soma_pesos < 99 else "MÉDIA FINAL"
                
                st.markdown(f"""
                <div style="text-align:center; padding: 20px; border: 2px solid {cor_media}; border-radius: 10px;">
                    <span style="font-size: 18px; color: #7f8c8d;">{lbl_media} PONDERADA</span><br>
                    <span style="font-size: 40px; font-weight: bold; color: {cor_media};">{media_ponderada:.2f}</span>
                    <br><small style="color:gray;">Cálculo baseado em {soma_pesos:.1f}% das avaliações que já aconteceram.</small>
                </div>
                """, unsafe_allow_html=True)

                # --- PROVAS CORRIGIDAS POR IA ---
                st.markdown("---")
                st.markdown("#### 🎯 Minhas Provas Corrigidas (IA)")
                try:
                    provas = buscar_dados("SELECT DISTINCT prova_nome FROM correcoes_detalhadas WHERE aluno_ra = ? AND disciplina = ?", (ra_ativo, d_ativa))
                    if not provas.empty:
                        p_sel = st.selectbox("Selecione a prova para ver o gabarito:", provas['prova_nome'])
                        det = buscar_dados("SELECT * FROM correcoes_detalhadas WHERE aluno_ra = ? AND prova_nome = ? ORDER BY questao_num", (ra_ativo, p_sel))
                        for _, q in det.iterrows():
                            with st.expander(f"{'✅' if q['status']=='Correta' else '❌'} Questão {q['questao_num']}"):
                                st.markdown(gerar_preview_web(q['feedback_ia']), unsafe_allow_html=True)
                    else: 
                        st.caption("Ainda não há gabaritos comentados disponíveis para esta disciplina.")
                except Exception:
                    st.caption("Ainda não há gabaritos comentados disponíveis para esta disciplina.")
        else: st.warning("Arthur, você ainda não tem disciplinas vinculadas.")               
# with t_boletim:
    #     with sqlite3.connect('banco_provas.db') as conn:
    #         # Busca as disciplinas em que o aluno está matriculado
    #         df_discs = pd.read_sql(f"SELECT m.turma_id, m.disciplina, t.nome as turma_nome FROM matriculas_disciplina m JOIN turmas t ON m.turma_id = t.id WHERE m.aluno_id = {aluno['id'].values[0]}", conn)
        
    #     if df_discs.empty:
    #         st.info("Você ainda não possui matrículas registradas.")
    #     else:
    #         # Seleção de Disciplina
    #         opcoes_disc = [f"{r['disciplina']} ({r['turma_nome']})" for _, r in df_discs.iterrows()]
    #         disc_sel_str = st.selectbox("Selecione a Disciplina:", opcoes_disc)
    #         idx_sel = opcoes_disc.index(disc_sel_str)
    #         d_sel = df_discs.iloc[idx_sel]['disciplina']
    #         t_id_sel = df_discs.iloc[idx_sel]['turma_id']

    #         # --- 1. PAINEL DE FREQUÊNCIA (FALTAS E PRESENÇAS) ---
    #         with st.container(border=True):
    #             st.markdown(f"#### 📊 Frequência em {d_sel}")
    #             with sqlite3.connect('banco_provas.db') as conn:
    #                 faltas = pd.read_sql(f"SELECT COUNT(*) as f FROM diario WHERE aluno_ra='{ra_ativo}' AND turma_id={t_id_sel} AND status='Ausente'", conn).iloc[0]['f']
    #                 pres = pd.read_sql(f"SELECT COUNT(*) as p FROM diario WHERE aluno_ra='{ra_ativo}' AND turma_id={t_id_sel} AND status='Presente'", conn).iloc[0]['p']
                
    #             total_aulas = faltas + pres
    #             perc_presenca = (pres / total_aulas * 100) if total_aulas > 0 else 100

    #             c1, c2, c3 = st.columns([1, 1, 2])
    #             c1.metric("🔴 Faltas", f"{faltas}")
    #             c2.metric("🟢 Presenças", f"{pres}")
                
    #             # Barra de Assiduidade colorida (Verde >= 75%, caso contrário Vermelha)
    #             cor_frequencia = "green" if perc_presenca >= 75 else "red"
    #             c3.markdown(f"""
    #                 <p style='margin-bottom:5px; font-size:14px; color:gray;'>Assiduidade: {perc_presenca:.0f}%</p>
    #                 <div style="width: 100%; background-color: #f0f2f6; border-radius: 10px; height: 15px;">
    #                     <div style="width: {perc_presenca}%; background-color: {cor_frequencia}; height: 15px; border-radius: 10px;"></div>
    #                 </div>
    #             """, unsafe_allow_html=True)

    #         st.markdown("---")

    #         # --- 2. BOLETIM E GRÁFICO DE EVOLUÇÃO ---
    #         try:
    #             with sqlite3.connect('banco_provas.db') as conn:
    #                 df_n = pd.read_sql(f"SELECT avaliacao as Avaliação, nota as Nota FROM notas_flexiveis WHERE matricula='{ra_ativo}' AND disciplina='{d_sel}' AND turma_id={t_id_sel} ORDER BY avaliacao", conn)
                
    #             if not df_n.empty:
    #                 # Garantir que as notas sejam tratadas como números para o gráfico
    #                 df_n['Nota'] = pd.to_numeric(df_n['Nota'], errors='coerce')
                    
    #                 col_tabela, col_grafico = st.columns([0.4, 0.6])
                    
    #                 with col_tabela:
    #                     st.markdown("**📝 Boletim de Notas**")
    #                     st.dataframe(df_n, hide_index=True, use_container_width=True)
    #                     media = df_n['Nota'].mean()
    #                     st.markdown(f"Média Atual: **{media:.1f}**")
                    
    #                 with col_grafico:
    #                     st.markdown("**📈 Evolução**")
    #                     if len(df_n) >= 2:
    #                         # Só gera o gráfico se houver 2 ou mais avaliações
    #                         chart_data = df_n.set_index('Avaliação')[['Nota']]
    #                         st.line_chart(chart_data, height=230)
    #                     else:
    #                         # Mensagem amigável para apenas 1 nota
    #                         st.info("Aguardando mais notas para traçar o gráfico de evolução.")
    #             else:
    #                 st.info("Nenhuma nota lançada para esta disciplina até o momento.")
    #         except Exception as e: 
    #             st.info("O sistema de notas está sendo carregado...")

    # # --- ABA 2: RANKING E DOJO (O MURAL DE HONRA) ---
    # with t_dojo:
    #     c_logs, c_rank = st.columns([0.6, 0.4])

    #     with c_logs:
    #         st.markdown("#### 📜 Meu Histórico de Pontos")
    #         with sqlite3.connect('banco_provas.db') as conn:
    #             logs = pd.read_sql(f"SELECT data as Data, pontos as Pontos, comentario as Motivo FROM logs_comportamento WHERE aluno_ra = '{ra_ativo}' ORDER BY id DESC", conn)
            
    #         if not logs.empty:
    #             st.dataframe(logs, use_container_width=True, hide_index=True)
    #         else:
    #             st.info("Você ainda não possui registros no Dojo. Participe das aulas para ganhar pontos!")

        # with c_rank:
        #     st.markdown("#### 👑 Top 5 - Mural de Honra")
        #     with sqlite3.connect('banco_provas.db') as conn:
        #         df_rank = pd.read_sql("""
        #             SELECT a.nome, a.avatar_style, a.ra, a.avatar_opts, SUM(l.pontos) as total 
        #             FROM logs_comportamento l 
        #             JOIN alunos a ON l.aluno_ra = a.ra 
        #             WHERE l.aluno_ra != 'TURMA_INTEIRA' 
        #             GROUP BY l.aluno_ra 
        #             ORDER BY total DESC 
        #             LIMIT 5
        #         """, conn)

        #     if not df_rank.empty:
        #         for i, r in df_rank.iterrows():
        #             # --- Lógica de Destaque para o Aluno Logado ---
        #             sou_eu = r['ra'] == ra_ativo
        #             cor_borda = "#3498db" if sou_eu else "#f0f2f6"
        #             cor_fundo = "#e8f4f8" if sou_eu else "#ffffff"
        #             peso_fonte = "bold" if sou_eu else "normal"
                    
        #             opts_rank = r['avatar_opts'] if pd.notna(r['avatar_opts']) else ""
        #             url_rank = f"https://api.dicebear.com/9.x/{r['avatar_style']}/svg?seed={r['ra']}{opts_rank}"
                    
        #             st.markdown(f"""
        #                 <div style='display: flex; align-items: center; background-color: {cor_fundo}; 
        #                             border: 2px solid {cor_borda}; padding: 10px; border-radius: 12px; 
        #                             margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);'>
        #                     <div style='font-size: 18px; font-weight: bold; color: #7f8c8d; width: 30px;'>#{i+1}</div>
        #                     <img src='{url_rank}' width='45' style='margin-right: 15px; border-radius: 50%; background: #eee;'>
        #                     <div style='flex-grow: 1;'>
        #                         <div style='font-weight: {peso_fonte}; font-size: 14px; color: #2c3e50;'>{r['nome'].split()[0]}</div>
        #                         <div style='font-size: 12px; color: #27ae60; font-weight: bold;'>⭐ {int(r['total'])} pontos</div>
        #                     </div>
        #                     { " <span style='font-size: 10px; background: #3498db; color: white; padding: 2px 6px; border-radius: 10px;'>VOCÊ</span>" if sou_eu else "" }
        #                 </div>
        #             """, unsafe_allow_html=True)
        #     else:
        #         st.info("O ranking ainda está sendo processado.")

    
    # --- ABA 4: MINHAS PROVAS (Gabarito e Correção) ---
#     with t_provas:
#         st.markdown("### 🔍 Detalhes das Minhas Provas")
#         provas_disponiveis = buscar_dados("SELECT DISTINCT prova_nome FROM correcoes_detalhadas WHERE aluno_ra = ?", (ra_ativo,))
        
#         if not provas_disponiveis.empty:
#             p_sel = st.selectbox("Selecione a prova:", provas_disponiveis['prova_nome'])
#             detalhes = buscar_dados("SELECT * FROM correcoes_detalhadas WHERE aluno_ra = ? AND prova_nome = ? ORDER BY questao_num", (ra_ativo, p_sel))
            
#             total_q = len(detalhes)
#             certas = len(detalhes[detalhes['status'] == 'Correta'])
#             nota_calculada = (certas / total_q) * 10 if total_q > 0 else 0
#             cor_nota = "#27ae60" if nota_calculada >= 6.0 else "#e74c3c"

#             # USANDO O NOSSO CARD PADRONIZADO DO CSS:
#             st.markdown(f"""
#             <div class="card-padrao" style="border-left: 5px solid {cor_nota};">
#                 <div class="card-titulo">Desempenho: {p_sel}</div>
#                 Acertos: {certas} de {total_q} <br>
#                 Nota Final: <span style="color: {cor_nota}; font-weight: bold; font-size: 20px;">{nota_calculada:.1f}</span> / 10.0
#             </div>
#             """, unsafe_allow_html=True)

#             st.markdown("#### 📝 Correção Detalhada")
#             for _, q in detalhes.iterrows():
#                 icone = "✅" if q['status'] == "Correta" else "❌"
#                 with st.expander(f"{icone} Questão {q['questao_num']} - {q['status']}"):
#                     st.write(q['feedback_ia'])
#         else:
#             st.info("Ainda não há feedbacks detalhados disponíveis.")
# # --- ABA 5: O QUE VIMOS NA AULA (DIÁRIO E CRONOGRAMA) ---
#     with t_diario:
#         st.markdown("### 📚 Diário de Bordo e Planejamento")
        
#         with sqlite3.connect('banco_provas.db') as conn:
#             # Reutiliza a busca de disciplinas para o aluno selecionar
#             df_discs_aula = pd.read_sql(f"SELECT m.turma_id, m.disciplina, t.nome as turma_nome FROM matriculas_disciplina m JOIN turmas t ON m.turma_id = t.id WHERE m.aluno_id = {aluno['id'].values[0]}", conn)
            
#         if df_discs_aula.empty:
#             st.info("Você não possui matrículas registradas.")
#         else:
#             opcoes_aula = [f"{r['disciplina']} ({r['turma_nome']})" for _, r in df_discs_aula.iterrows()]
#             aula_sel_str = st.selectbox("Selecione a Disciplina:", opcoes_aula, key="sel_aula_aba5")
#             idx_aula = opcoes_aula.index(aula_sel_str)
#             d_aula_sel = df_discs_aula.iloc[idx_aula]['disciplina']
#             t_id_aula_sel = df_discs_aula.iloc[idx_aula]['turma_id']

#             st.markdown("---")
#             col_diario, col_crono = st.columns([0.5, 0.5])
            
#             with col_diario:
#                 st.markdown("#### 📖 Conteúdo Ministrado")
#                 st.caption("O que já rolou nas aulas anteriores.")
#                 with sqlite3.connect('banco_provas.db') as conn:
#                     # Lê a tabela diario_conteudo (se ela já existir no seu banco)
#                     try:
#                         df_diario = pd.read_sql(f"SELECT data, conteudo FROM diario_conteudo WHERE turma_id={t_id_aula_sel} AND disciplina='{d_aula_sel}' ORDER BY data DESC", conn)
#                         if not df_diario.empty:
#                             for _, row in df_diario.iterrows():
#                                 with st.expander(f"📅 Aula do dia {row['data']}"):
#                                     st.write(row['conteudo'])
#                         else:
#                             st.info("Nenhum registro de conteúdo para esta disciplina.")
#                     except:
#                         st.warning("Tabela de diário de conteúdo ainda não iniciada.")

#             with col_crono:
#                 st.markdown("#### 🗺️ Planejamento do Semestre")
#                 st.caption("O que está por vir (Cronograma Detalhado).")
#                 with sqlite3.connect('banco_provas.db') as conn:
#                     # Lê a tabela cronograma_detalhado
#                     try:
#                         df_crono = pd.read_sql(f"SELECT aula_num as Aula, tema as Tema, tipo_aula as Tipo FROM cronograma_detalhado WHERE turma_id={t_id_aula_sel} AND disciplina='{d_aula_sel}' ORDER BY aula_num", conn)
#                         if not df_crono.empty:
#                             st.dataframe(df_crono, use_container_width=True, hide_index=True)
#                         else:
#                             st.info("Cronograma não cadastrado pela professora.")
#                     except:
#                         st.warning("Tabela de cronograma ainda não iniciada.")    