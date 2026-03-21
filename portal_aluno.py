import streamlit as st
import pandas as pd
import sqlite3

from datetime import datetime

# --- 1. SETUP INICIAL E LIMPEZA ---
with sqlite3.connect('banco_provas.db') as conn:
    # Garante que a tabela de feedbacks detalhados exista (Evita erro na Aba Provas)
    conn.execute('''CREATE TABLE IF NOT EXISTS correcoes_detalhadas (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_ra TEXT, disciplina TEXT, prova_nome TEXT, questao_num INTEGER, status TEXT, feedback_ia TEXT)''')
    
    try: 
        conn.execute("ALTER TABLE alunos ADD COLUMN avatar_opts TEXT DEFAULT ''")
    except: 
        pass
    
    # Limpa vestígios de versões antigas para garantir o motor 9.x
    conn.execute("UPDATE alunos SET avatar_opts = '' WHERE avatar_opts LIKE '%7.x%' OR avatar_opts LIKE '%accessories%'")
    conn.commit()

st.set_page_config(page_title="Portal do Aluno FAM", page_icon="🎓", layout="centered")
st.title("🎓 Portal do Aluno")

if 'aluno_logado_ra' not in st.session_state:
    st.session_state.aluno_logado_ra = None

# --- 2. LOGIN ---
with st.sidebar:
    st.markdown("### 🔑 Acesso Seguro")
    if not st.session_state.aluno_logado_ra:
        ra_login = st.text_input("Seu RA:")
        senha_login = st.text_input("Sua Senha:", type="password")
        if st.button("🚀 Entrar", use_container_width=True):
            with sqlite3.connect('banco_provas.db') as conn:
                aluno_check = pd.read_sql("SELECT ra FROM alunos WHERE ra = ? AND senha = ?", conn, params=[ra_login, senha_login])
                if not aluno_check.empty:
                    st.session_state.aluno_logado_ra = ra_login
                    st.rerun()
                else:
                    st.error("RA ou Senha incorretos.")
    else:
        st.success("✅ Conectado")
        if st.button("🚪 Sair da Conta", use_container_width=True):
            st.session_state.aluno_logado_ra = None
            st.rerun()

# --- 3. ÁREA LOGADA ---
if st.session_state.aluno_logado_ra:
    ra_ativo = st.session_state.aluno_logado_ra
    with sqlite3.connect('banco_provas.db') as conn:
        aluno = pd.read_sql("SELECT * FROM alunos WHERE ra = ?", conn, params=[ra_ativo])
        
    st.header(f"Bem-vindo, {aluno['nome'].values[0]}! 👋")
    # No arquivo do Portal do Aluno, mude a linha das abas para:
    t_acad, t_dojo, t_perfil, t_provas = st.tabs(["📊 Boletim", "🏆 Ranking", "👤 Perfil", "📝 Minhas Provas"])

    # --- ABA 1: ACADÊMICO (NOTAS E FALTAS) ---
    with t_acad:
        with sqlite3.connect('banco_provas.db') as conn:
            # Busca as disciplinas em que o aluno está matriculado
            df_discs = pd.read_sql(f"SELECT m.turma_id, m.disciplina, t.nome as turma_nome FROM matriculas_disciplina m JOIN turmas t ON m.turma_id = t.id WHERE m.aluno_id = {aluno['id'].values[0]}", conn)
        
        if df_discs.empty:
            st.info("Você ainda não possui matrículas registradas.")
        else:
            # Seleção de Disciplina
            opcoes_disc = [f"{r['disciplina']} ({r['turma_nome']})" for _, r in df_discs.iterrows()]
            disc_sel_str = st.selectbox("Selecione a Disciplina:", opcoes_disc)
            idx_sel = opcoes_disc.index(disc_sel_str)
            d_sel = df_discs.iloc[idx_sel]['disciplina']
            t_id_sel = df_discs.iloc[idx_sel]['turma_id']

            # --- 1. PAINEL DE FREQUÊNCIA (FALTAS E PRESENÇAS) ---
            with st.container(border=True):
                st.markdown(f"#### 📊 Frequência em {d_sel}")
                with sqlite3.connect('banco_provas.db') as conn:
                    faltas = pd.read_sql(f"SELECT COUNT(*) as f FROM diario WHERE aluno_ra='{ra_ativo}' AND turma_id={t_id_sel} AND status='Ausente'", conn).iloc[0]['f']
                    pres = pd.read_sql(f"SELECT COUNT(*) as p FROM diario WHERE aluno_ra='{ra_ativo}' AND turma_id={t_id_sel} AND status='Presente'", conn).iloc[0]['p']
                
                total_aulas = faltas + pres
                perc_presenca = (pres / total_aulas * 100) if total_aulas > 0 else 100

                c1, c2, c3 = st.columns([1, 1, 2])
                c1.metric("🔴 Faltas", f"{faltas}")
                c2.metric("🟢 Presenças", f"{pres}")
                
                # Barra de Assiduidade colorida (Verde >= 75%, caso contrário Vermelha)
                cor_frequencia = "green" if perc_presenca >= 75 else "red"
                c3.markdown(f"""
                    <p style='margin-bottom:5px; font-size:14px; color:gray;'>Assiduidade: {perc_presenca:.0f}%</p>
                    <div style="width: 100%; background-color: #f0f2f6; border-radius: 10px; height: 15px;">
                        <div style="width: {perc_presenca}%; background-color: {cor_frequencia}; height: 15px; border-radius: 10px;"></div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # --- 2. BOLETIM E GRÁFICO DE EVOLUÇÃO ---
            try:
                with sqlite3.connect('banco_provas.db') as conn:
                    df_n = pd.read_sql(f"SELECT avaliacao as Avaliação, nota as Nota FROM notas_flexiveis WHERE matricula='{ra_ativo}' AND disciplina='{d_sel}' AND turma_id={t_id_sel} ORDER BY avaliacao", conn)
                
                if not df_n.empty:
                    # Garantir que as notas sejam tratadas como números para o gráfico
                    df_n['Nota'] = pd.to_numeric(df_n['Nota'], errors='coerce')
                    
                    col_tabela, col_grafico = st.columns([0.4, 0.6])
                    
                    with col_tabela:
                        st.markdown("**📝 Boletim de Notas**")
                        st.dataframe(df_n, hide_index=True, use_container_width=True)
                        media = df_n['Nota'].mean()
                        st.markdown(f"Média Atual: **{media:.1f}**")
                    
                    with col_grafico:
                        st.markdown("**📈 Evolução**")
                        if len(df_n) >= 2:
                            # Só gera o gráfico se houver 2 ou mais avaliações
                            chart_data = df_n.set_index('Avaliação')[['Nota']]
                            st.line_chart(chart_data, height=230)
                        else:
                            # Mensagem amigável para apenas 1 nota
                            st.info("Aguardando mais notas para traçar o gráfico de evolução.")
                else:
                    st.info("Nenhuma nota lançada para esta disciplina até o momento.")
            except Exception as e: 
                st.info("O sistema de notas está sendo carregado...")

    # --- ABA 2: RANKING E DOJO (O MURAL DE HONRA) ---
    with t_dojo:
        c_logs, c_rank = st.columns([0.6, 0.4])

        with c_logs:
            st.markdown("#### 📜 Meu Histórico de Pontos")
            with sqlite3.connect('banco_provas.db') as conn:
                logs = pd.read_sql(f"SELECT data as Data, pontos as Pontos, comentario as Motivo FROM logs_comportamento WHERE aluno_ra = '{ra_ativo}' ORDER BY id DESC", conn)
            
            if not logs.empty:
                st.dataframe(logs, use_container_width=True, hide_index=True)
            else:
                st.info("Você ainda não possui registros no Dojo. Participe das aulas para ganhar pontos!")

        with c_rank:
            st.markdown("#### 👑 Top 5 - Mural de Honra")
            with sqlite3.connect('banco_provas.db') as conn:
                df_rank = pd.read_sql("""
                    SELECT a.nome, a.avatar_style, a.ra, a.avatar_opts, SUM(l.pontos) as total 
                    FROM logs_comportamento l 
                    JOIN alunos a ON l.aluno_ra = a.ra 
                    WHERE l.aluno_ra != 'TURMA_INTEIRA' 
                    GROUP BY l.aluno_ra 
                    ORDER BY total DESC 
                    LIMIT 5
                """, conn)

            if not df_rank.empty:
                for i, r in df_rank.iterrows():
                    # --- Lógica de Destaque para o Aluno Logado ---
                    sou_eu = r['ra'] == ra_ativo
                    cor_borda = "#3498db" if sou_eu else "#f0f2f6"
                    cor_fundo = "#e8f4f8" if sou_eu else "#ffffff"
                    peso_fonte = "bold" if sou_eu else "normal"
                    
                    opts_rank = r['avatar_opts'] if pd.notna(r['avatar_opts']) else ""
                    url_rank = f"https://api.dicebear.com/9.x/{r['avatar_style']}/svg?seed={r['ra']}{opts_rank}"
                    
                    st.markdown(f"""
                        <div style='display: flex; align-items: center; background-color: {cor_fundo}; 
                                    border: 2px solid {cor_borda}; padding: 10px; border-radius: 12px; 
                                    margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);'>
                            <div style='font-size: 18px; font-weight: bold; color: #7f8c8d; width: 30px;'>#{i+1}</div>
                            <img src='{url_rank}' width='45' style='margin-right: 15px; border-radius: 50%; background: #eee;'>
                            <div style='flex-grow: 1;'>
                                <div style='font-weight: {peso_fonte}; font-size: 14px; color: #2c3e50;'>{r['nome'].split()[0]}</div>
                                <div style='font-size: 12px; color: #27ae60; font-weight: bold;'>⭐ {int(r['total'])} pontos</div>
                            </div>
                            { " <span style='font-size: 10px; background: #3498db; color: white; padding: 2px 6px; border-radius: 10px;'>VOCÊ</span>" if sou_eu else "" }
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("O ranking ainda está sendo processado.")

    with t_perfil:
        c_av, c_pw = st.columns([0.65, 0.35])
        estilo_atual = aluno['avatar_style'].values[0]
        
        with c_av:
            with st.container(border=True):
                st.markdown("### 🎨 Estúdio de Avatares")
                
                # 1. AVATAR EM DESTAQUE NO TOPO
                img_prev = st.empty()
                btn_salvar = st.empty()
                
                st.markdown("---")
                
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

        # --- COLUNA DA SENHA ---
        with c_pw:
            with st.container(border=True):
                st.subheader("🔒 Segurança")
                n_s = st.text_input("Nova Senha:", type="password")
                c_s = st.text_input("Confirmar Senha:", type="password")
                if st.button("Gravar Nova Senha", use_container_width=True):
                    if n_s == c_s and len(n_s) >= 4:
                        with sqlite3.connect('banco_provas.db') as c:
                            c.execute("UPDATE alunos SET senha=? WHERE ra=?", (n_s, ra_ativo))
                        st.success("Senha atualizada!")
                    else: st.error("Senhas não conferem.")
    with t_provas:
        st.markdown("### 🔍 Detalhes das Minhas Provas")
        with sqlite3.connect('banco_provas.db') as conn:
            provas_disponiveis = pd.read_sql(f"SELECT DISTINCT prova_nome FROM correcoes_detalhadas WHERE aluno_ra = '{ra_ativo}'", conn)
        
        if not provas_disponiveis.empty:
            p_sel = st.selectbox("Selecione a prova:", provas_disponiveis['prova_nome'])
            with sqlite3.connect('banco_provas.db') as conn:
                detalhes = pd.read_sql(f"SELECT * FROM correcoes_detalhadas WHERE aluno_ra = '{ra_ativo}' AND prova_nome = ?", conn, params=[p_sel])
            
            for _, q in detalhes.iterrows():
                icone = "✅" if q['status'] == "Correta" else "❌"
                with st.expander(f"{icone} Questão {q['questao_num']} - {q['status']}"):
                    st.write(q['feedback_ia'])
        else:
            st.info("Ainda não há feedbacks detalhados disponíveis.")