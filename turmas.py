# turmas.py
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as plex 
import holidays
import calendar
from datetime import datetime, timedelta

def renderizar_aba_turmas():
    with sqlite3.connect('banco_provas.db') as conn:
        # --- 0. PREPARAÇÃO DE DATAS ---
        semestres_existentes = pd.read_sql("SELECT DISTINCT semestre FROM turmas", conn)['semestre'].dropna().tolist()
        if "2026.1" not in semestres_existentes: semestres_existentes.append("2026.1")
        sem_recente = sorted(semestres_existentes, reverse=True)[0]

        # --- 1. SISTEMA DE 3 ABAS (Substitui o Expander e os filtros soltos) ---
        t_operar, t_criar, t_importar = st.tabs(["🔍 Operar Turma", "➕ Criar Nova Turma", "📥 Importar Alunos"])

        # Inicializamos variáveis de controle
        id_t_ativa, d_ativa, t_ativa = None, None, None

        # --- ABA 1: OPERAR (AQUI FICAM OS SEUS FILTROS ORIGINAIS) ---
        with t_operar:
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                st.markdown("🌓 **Por Semestre**")
                semestre_ativo = st.selectbox("Selecione o Semestre Letivo:", sorted(semestres_existentes, reverse=True), label_visibility="collapsed", key="filt_sem_vFinal")
            
            t_db_ativa = pd.read_sql(f"SELECT * FROM turmas WHERE semestre='{semestre_ativo}'", conn)
            
            if not t_db_ativa.empty:
                with c_f2:
                    st.markdown("👥 **Turma:**")
                    t_ativa = st.selectbox("Escolha a Turma:", t_db_ativa['nome'].tolist(), label_visibility="collapsed", key="filt_t_vFinal")
                    id_t_ativa = int(t_db_ativa[t_db_ativa['nome'] == t_ativa]['id'].values[0])
                
                modelos_disponiveis = pd.read_sql("SELECT DISTINCT titulo_modelo FROM modelos_ensino", conn)['titulo_modelo'].dropna().tolist()
                with c_f3:
                    st.markdown("🏷️ **Disciplina:**")
                    if modelos_disponiveis:
                        d_ativa = st.selectbox("Disciplina cursada:", modelos_disponiveis, label_visibility="collapsed", key="filt_d_vFinal")
                    else:
                        st.warning("Crie um Molde na Fábrica.")
            else:
                st.info(f"Nenhuma turma em {semestre_ativo}")

        # --- ABA 2: CRIAR NOVA TURMA ---
        with t_criar:
            st.write("**Criar Turma**")
            col_c1, col_c2 = st.columns(2)
            n_t = col_c1.text_input("Nome da Turma:", placeholder="Ex: Engenharia Civil A", key="cad_n_t_vF")
            n_sem = col_c2.text_input("Semestre:", value=sem_recente, key="cad_s_t_vF")
            if st.button("🚀 Criar Turma", use_container_width=True):
                if n_t:
                    conn.execute('INSERT INTO turmas (nome, semestre) VALUES (?, ?)', (n_t, n_sem))
                    conn.commit(); st.success("Turma criada!"); st.rerun()

        # --- ABA 3: IMPORTAR ALUNOS ---
        with t_importar:
            st.markdown("**📥 Importar Lista (Excel/CSV)**")
            t_db_todas = pd.read_sql("SELECT * FROM turmas ORDER BY semestre DESC, nome ASC", conn)
            if not t_db_todas.empty:
                opcoes_turmas = [f"[{r['semestre']}] {r['nome']}" for _, r in t_db_todas.iterrows()]
                t_up_sel = st.selectbox("Turma de Destino:", opcoes_turmas, key="imp_t_dest_vF")
                arq = st.file_uploader("Arquivo (NOME e RA):", type=['xlsx', 'csv'], key="imp_t_arq_vF")
                if st.button("Iniciar Importação", use_container_width=True) and arq:
                    df = pd.read_excel(arq) if arq.name.endswith('.xlsx') else pd.read_csv(arq, sep=None, engine='python')
                    df.columns = df.columns.str.strip().str.upper()
                    c_n = next((c for c in df.columns if c in ['NOME', 'ALUNO']), None)
                    c_r = next((c for c in df.columns if c in ['RA', 'MATRICULA']), None)
                    if c_n and c_r:
                        nome_turma_pura = t_up_sel.split("] ", 1)[1]
                        id_up = t_db_todas[t_db_todas['nome'] == nome_turma_pura]['id'].values[0]
                        for _, row in df.dropna(subset=[c_n, c_r]).iterrows():
                            ra_limpo = str(row[c_r]).replace('.0', '').strip()
                            conn.execute('INSERT OR IGNORE INTO alunos (turma_id, nome, ra) VALUES (?, ?, ?)', (int(id_up), str(row[c_n]).strip(), ra_limpo))
                        conn.commit(); st.success("Importação concluída!"); st.rerun()

        # --- 2. ÁREA DE TRABALHO (Sub-Abas Pedagógicas) ---
        if id_t_ativa and d_ativa:
                st.write("---")
                sub_mat, sub_cron, sub_pesos, sub_boletim = st.tabs([
                    "🎓 1. Matrículas", "🗓️ 2. Plano de aulas", "⚖️ 3. Pesos de Notas", "🏆 4. Boletim Mestre"
                ])
                
                with sub_mat:
                    st.markdown(f"**Quais alunos de {t_ativa} farão {d_ativa}?**")
                    alunos_turma_base = pd.read_sql(f"SELECT id, nome, ra, email, observacoes FROM alunos WHERE turma_id={id_t_ativa} ORDER BY nome", conn)
                    
                    if alunos_turma_base.empty:
                        st.info("Importe a lista de alunos da turma no menu superior de 'Importação'.")
                    else:
                        # 1. GERENCIAMENTO DE MATRÍCULA
                        matriculados = pd.read_sql(f"SELECT aluno_id FROM matriculas_disciplina WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)['aluno_id'].tolist()
                        alunos_dict = dict(zip(alunos_turma_base['nome'], alunos_turma_base['id']))
                        nomes_pre_selecionados = [nome for nome, id_al in alunos_dict.items() if id_al in matriculados]
                        selecionados = st.multiselect("Selecione os matriculados nesta disciplina:", options=alunos_turma_base['nome'].tolist(), default=nomes_pre_selecionados if matriculados else alunos_turma_base['nome'].tolist())
                        
                        if st.button("💾 Salvar Matrículas da Disciplina"):
                            conn.execute("DELETE FROM matriculas_disciplina WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                            for nome in selecionados:
                                conn.execute("INSERT INTO matriculas_disciplina (turma_id, disciplina, aluno_id) VALUES (?,?,?)", (int(id_t_ativa), d_ativa, int(alunos_dict[nome])))
                            conn.commit()
                            st.success(f"Matrículas de {d_ativa} atualizadas!")
                            st.rerun()

                        st.write("---")
                        st.markdown("**🆔 Lista de Alunos e Anotações Pedagógicas**")
                        df_edit_lista = pd.read_sql(f"SELECT a.id, a.ra as RA, a.nome as Nome, a.email as E_mail, a.observacoes as [Anotações Pedagógicas] FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' ORDER BY a.nome", conn)
                        if not df_edit_lista.empty:
                            df_resultado_edicao = st.data_editor(df_edit_lista, column_config={"id": None, "RA": st.column_config.TextColumn("RA", disabled=True), "Nome": st.column_config.TextColumn("Nome do Aluno", width="medium"), "E_mail": st.column_config.TextColumn("E-mail"), "Anotações Pedagógicas": st.column_config.TextColumn("Notas (TDAH, Liderança, etc.)", width="large")}, hide_index=True, use_container_width=True, key=f"editor_alunos_{id_t_ativa}_{d_ativa}")
                            if st.button("💾 Salvar Alterações na Lista", type="primary", use_container_width=True):
                                with sqlite3.connect('banco_provas.db') as c:
                                    for _, row in df_resultado_edicao.iterrows():
                                        c.execute("UPDATE alunos SET nome=?, email=?, observacoes=? WHERE id=?", (row['Nome'], row['E_mail'], row['Anotações Pedagógicas'], int(row['id'])))
                                st.success("Informações atualizadas!"); st.rerun()

                with sub_cron:
                    aba_planejador, aba_plano_real = st.tabs(["🔀 Planejador de Aulas", "🧭 Plano de aula real"])
                    with aba_planejador:
                        with st.container(border=True):
                            st.markdown("**📅 Passo 1: Calendário e Provas**")
                            c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
                            d_ini = c1.date_input("Início do Semestre:", datetime.today(), key="cr_ini_vFinal")
                            d_fim = c2.date_input("Fim do Semestre:", datetime.today() + timedelta(days=130), key="cr_fim_vFinal")
                            c_fer = c3.selectbox("📍 Cidade:", ["Nenhum", "Americana", "Campinas"], key="cr_city_vFinal")
                            mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5}
                            dias_w = st.multiselect("Dias com aula:", list(mapa_dias.keys()), default=["Segunda"], key="cr_dias_vFinal")
                            st.write("**📍 Agendar Eventos Fixos (N1, N2, N3, AR):**")
                            if "df_fixas_vFinal" not in st.session_state:
                                st.session_state.df_fixas_vFinal = pd.DataFrame([{"Data": d_ini + timedelta(days=60), "Evento": "Prova N1"}, {"Data": d_ini + timedelta(days=110), "Evento": "Prova N2"}])
                            ed_fixas = st.data_editor(st.session_state.df_fixas_vFinal, num_rows="dynamic", use_container_width=True, key="ed_fixas_vFinal", column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
                            num_aulas_meta = st.number_input("Meta total de aulas:", min_value=1, value=20, key="meta_vFinal")
                            anos = list(set([d_ini.year, d_fim.year]))
                            f_base = holidays.Brazil(subdiv='SP', years=anos)
                            f_per = {d: n for d, n in f_base.items() if d_ini <= d <= d_fim}
                            sel_f = st.multiselect("Pular feriados:", options=list(f_per.keys()), format_func=lambda x: f"{x.strftime('%d/%m/%Y')} - {f_per[x]}", default=list(f_per.keys()), key="sel_f_vFinal")
                            d_ext = st.text_input("Exceções (Bloqueios):", placeholder="Ex: 22/04/2026", key="ext_vFinal")

                            if st.button("📅 Gerar Grade de Datas Disponíveis", use_container_width=True):
                                dict_fixas = {row['Data']: row['Evento'] for _, row in ed_fixas.iterrows() if row['Data'] is not None}
                                idx_aulas = [mapa_dias[d] for d in dias_w]
                                datas_v = []
                                curr = d_ini
                                bloqueio_manual = [d.strip() for d in d_ext.split(",") if d.strip()]
                                while curr <= d_fim and len(datas_v) < num_aulas_meta:
                                    ds_str = curr.strftime("%d/%m/%Y")
                                    if curr in sel_f or ds_str in bloqueio_manual:
                                        curr += timedelta(days=1); continue
                                    if curr.weekday() in idx_aulas:
                                        evento_fixo = dict_fixas.get(curr, "")
                                        datas_v.append({"data": ds_str, "num_aula": len(datas_v)+1, "tema_origem": evento_fixo if evento_fixo else "-- Selecionar Conteúdo --", "tipo_aula": "Avaliação" if evento_fixo else "Teórica"})
                                    curr += timedelta(days=1)
                                st.session_state[f"temp_cron_{id_t_ativa}"] = datas_v; st.rerun()

                            key_temp = f"temp_cron_{id_t_ativa}"
                            if key_temp in st.session_state:
                                st.write("") 
                                df_fab = pd.read_sql(f"SELECT num_aula, tema FROM roteiro_mestre WHERE titulo_modelo='{d_ativa}' ORDER BY num_aula", conn)
                                dict_fab = {f"Aula {row['num_aula']}: {row['tema']}": row['num_aula'] for _, row in df_fab.iterrows()}
                                opcoes_fab = ["-- Selecionar --", "Aula Extra / Revisão", "Prova N1", "Prova N2", "Prova N3", "Exame AR"] + list(dict_fab.keys())
                                c_p2_1, c_p2_2, c_p2_3 = st.columns([0.4, 0.35, 0.25], vertical_alignment="bottom")
                                c_p2_1.markdown("**📏 Passo 2: Distribuir Conteúdo**")
                                if c_p2_2.button("⚡ Preenchimento Sequencial", use_container_width=True):
                                    ponteiro = 0
                                    for i, _ in enumerate(st.session_state[key_temp]):
                                        if any(x in st.session_state[key_temp][i]['tema_origem'] for x in ["Prova", "Exame", "AR"]): continue
                                        if ponteiro < len(df_fab):
                                            st.session_state[key_temp][i]['tema_origem'] = f"Aula {df_fab.iloc[ponteiro]['num_aula']}: {df_fab.iloc[ponteiro]['tema']}"; ponteiro += 1
                                    st.rerun()
                                if c_p2_3.button("🗑️ Reiniciar Grade", use_container_width=True): del st.session_state[key_temp]; st.rerun()

                                for idx, aula in enumerate(st.session_state[key_temp]):
                                    with st.container(border=True):
                                        c_d, c_s = st.columns([0.3, 0.7])
                                        cor = "red" if any(x in aula['tema_origem'] for x in ["Prova", "Exame", "AR"]) else "blue"
                                        c_d.markdown(f"<b style='color:{cor};'>Aula {aula['num_aula']} ({aula['data']})</b>", unsafe_allow_html=True)
                                        st.session_state[key_temp][idx]['tema_origem'] = c_s.selectbox(f"Conteúdo para {aula['data']}:", options=opcoes_fab, index=opcoes_fab.index(aula['tema_origem']) if aula['tema_origem'] in opcoes_fab else 0, key=f"mapeador_vFinal_{idx}")
                                if st.button("💾 CONSOLIDAR E SALVAR CRONOGRAMA", type="primary", use_container_width=True):
                                    conn.execute("DELETE FROM cronograma_detalhado WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                    for r in st.session_state[key_temp]:
                                        if r['tema_origem'] in dict_fab:
                                            d_f = pd.read_sql(f"SELECT * FROM roteiro_mestre WHERE titulo_modelo='{d_ativa}' AND num_aula={dict_fab[r['tema_origem']]}", conn).iloc[0].to_dict()
                                            dfinal = {k: (v if v is not None else "") for k, v in d_f.items()}
                                        else:
                                            dfinal = {k: "" for k in ["tema", "tipo_aula", "objetivos_aula", "conteudo_detalhado", "metodologia", "aps_aula", "referencias_aula", "link_slides", "link_overleaf", "link_extras", "atividades", "atividades_link", "forum", "forum_link"]}
                                            dfinal['tema'] = r['tema_origem']; dfinal['tipo_aula'] = "Avaliação" if "Prova" in r['tema_origem'] else "Teórica"
                                        conn.execute("""INSERT INTO cronograma_detalhado (turma_id, disciplina, num_aula, data, tema, tipo_aula, objetivos_aula, conteudo_detalhado, metodologia, aps_aula, referencias_aula, link_slides, link_overleaf, link_extras, atividades, atividades_link, forum, forum_link) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (int(id_t_ativa), d_ativa, r['num_aula'], r['data'], dfinal['tema'], dfinal['tipo_aula'], dfinal['objetivos_aula'], dfinal['conteudo_detalhado'], dfinal['metodologia'], dfinal['aps_aula'], dfinal['referencias_aula'], dfinal['link_slides'], dfinal['link_overleaf'], dfinal['link_extras'], dfinal['atividades'], dfinal['atividades_link'], dfinal['forum'], dfinal['forum_link']))
                                    conn.commit(); st.success("Cronograma salvo!"); del st.session_state[key_temp]; st.rerun()

                    with aba_plano_real:
                        df_master = pd.read_sql(f"SELECT c.*, d.conteudo_real FROM cronograma_detalhado c LEFT JOIN diario_conteudo d ON c.turma_id = d.turma_id AND c.disciplina = d.disciplina AND c.data = d.data WHERE c.turma_id={id_t_ativa} AND c.disciplina='{d_ativa}' ORDER BY c.num_aula", conn)
                        if not df_master.empty:
                            for idx, row in df_master.iterrows():
                                st_icon = "✅" if pd.notna(row['conteudo_real']) else "📅"
                                with st.expander(f"{st_icon} Aula {row['num_aula']} ({row['data']}) - {row['tema']}"):
                                    col_p, col_f = st.columns([0.65, 0.35])
                                    with col_p:
                                        st.markdown("**📝 Edição do Planejamento:**")
                                        c_p1, c_p2 = st.columns([0.7, 0.3])
                                        n_t = c_p1.text_input("Tema:", value=row['tema'], key=f"v_t_{idx}_vF")
                                        lista_tp = ["Teórica", "Prática", "Laboratório", "Avaliação"]
                                        n_tp = c_p2.selectbox("Tipo:", lista_tp, index=lista_tp.index(row['tipo_aula']) if row['tipo_aula'] in lista_tp else 0, key=f"v_tp_{idx}_vF")
                                        n_obj = st.text_area("Objetivos:", value=row['objetivos_aula'] or "", key=f"v_o_{idx}_vF", height=70)
                                        n_cont = st.text_area("Conteúdo:", value=row['conteudo_detalhado'] or "", key=f"v_c_{idx}_vF", height=100)
                                        cp1, cp2 = st.columns(2)
                                        n_m = cp1.text_area("Metodologia:", value=row['metodologia'] or "", key=f"v_m_{idx}_vF")
                                        n_a = cp2.text_area("APS:", value=row['aps_aula'] or "", key=f"v_aps_{idx}_vF")
                                        b1, b2, b3 = st.columns(3)
                                        n_ls = b1.text_input("Link Slides:", value=row['link_slides'] or "", key=f"v_ls_{idx}_vF")
                                        n_lo = b2.text_input("Link Overleaf:", value=row['link_overleaf'] or "", key=f"v_lo_{idx}_vF")
                                        n_le = b3.text_input("Extras:", value=row['link_extras'] or "", key=f"v_le_{idx}_vF")
                                        ca1, ca2 = st.columns([0.6, 0.4])
                                        n_at_t = ca1.text_area("Texto Atividade:", value=row['atividades'] or "", key=f"v_at_{idx}_vF")
                                        n_at_l = ca2.text_input("Link Material Ativ.:", value=row['atividades_link'] or "", key=f"v_al_{idx}_vF")
                                        cf1, cf2 = st.columns([0.6, 0.4])
                                        n_ft_t = cf1.text_area("Texto Fórum:", value=row['forum'] or "", key=f"v_ft_{idx}_vF")
                                        n_ft_l = cf2.text_input("Link Material Fórum:", value=row['forum_link'] or "", key=f"v_fl_{idx}_vF")
                                        n_ref = st.text_input("Referências:", value=row['referencias_aula'] or "", key=f"v_r_{idx}_vF")
                                    with col_f:
                                        st.markdown("**📖 Diário Real:**")
                                        if pd.notna(row['conteudo_real']): st.success(row['conteudo_real'])
                                        else: st.info("Aguardando registro.")
                                    c_btn1, c_btn2, c_btn3 = st.columns([0.4, 0.4, 0.2])
                                    sync = c_btn1.checkbox("🔄 Sincronizar na FÁBRICA", key=f"sy_{idx}_vF")
                                    if c_btn2.button(f"💾 Salvar Aula {row['num_aula']}", key=f"bs_{idx}_vF", type="primary"):
                                        conn.execute("UPDATE cronograma_detalhado SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE id=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, row['id']))
                                        if sync: conn.execute("UPDATE roteiro_mestre SET tema=?, tipo_aula=?, objetivos_aula=?, conteudo_detalhado=?, metodologia=?, aps_aula=?, link_slides=?, link_overleaf=?, link_extras=?, atividades=?, atividades_link=?, forum=?, forum_link=?, referencias_aula=? WHERE titulo_modelo=? AND num_aula=?", (n_t, n_tp, n_obj, n_cont, n_m, n_a, n_ls, n_lo, n_le, n_at_t, n_at_l, n_ft_t, n_ft_l, n_ref, d_ativa, row['num_aula']))
                                        conn.commit(); st.toast("Salvo!"); st.rerun()
                                    if c_btn3.button("🗑️ Deletar", key=f"bd_{idx}_vF"):
                                        conn.execute("DELETE FROM cronograma_detalhado WHERE id=?", (row['id'],)); conn.commit(); st.rerun()
                                st.write("---")

                with sub_pesos:
                    df_ativ_sala = pd.read_sql(f"SELECT data, aluno_ra as Matrícula, entregou FROM atividades_sala WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}' ORDER BY data", conn)
                    datas_unicas = df_ativ_sala['data'].unique() if not df_ativ_sala.empty else []
                    qtd_aulas_registradas = len(datas_unicas)
                    st.markdown("**📊 Central Dinâmica de Notas e Médias**")
                    t_manual, t_excel, t_auto, t_config = st.tabs(["✍️ Planilha de Notas", "📊 Importar Notas", "🦾 Corretor Automático", "⚙️ Ajustar Pesos e Quantidades"])
                    with t_config:
                        st.info(f"⚡ Atualmente existem {qtd_aulas_registradas} aulas no Dojo.")
                        col_cfg1, col_cfg2 = st.columns(2)
                        with col_cfg1:
                            with st.container(border=True):
                                st.markdown("**📝 Provas Oficiais**")
                                n_p = st.text_input("Nome:", "Prova N", key="n_p"); q_p = st.number_input("Quantidade:", 0, 10, 2, key="q_p"); w_p = st.number_input("Peso Final (%):", 0, 100, 60, key="w_p"); c_p = st.number_input("Descartar Piores %:", 0, 99, 0, step=5, key="corte_p")
                        with col_cfg2:
                            with st.container(border=True):
                                st.markdown("**📋 Listas / Exercícios**")
                                n_l = st.text_input("Nome:", "Lista", key="n_l"); q_l = st.number_input("Quantidade:", 0, 20, 3, key="q_l"); w_l = st.number_input("Peso Final (%):", 0, 100, 10, key="w_l"); c_l = st.number_input("Descartar Piores %:", 0, 99, 0, step=5, key="corte_l")
                        col_cfg3, col_cfg4 = st.columns(2)
                        with col_cfg3:
                            with st.container(border=True):
                                st.markdown("**🔬 Laboratório / Prática**")
                                n_lb = st.text_input("Nome:", "Lab", key="n_lb"); q_lb = st.number_input("Quantidade:", 0, 20, 2, key="q_lb"); w_lb = st.number_input("Peso Final (%):", 0, 100, 20, key="w_lb"); c_lb = st.number_input("Descartar Piores %:", 0, 99, 0, step=5, key="corte_lb")
                        with col_cfg4:
                            with st.container(border=True):
                                st.markdown("**🥋 Ativ. em Sala (Dojo)**")
                                n_a = st.text_input("Prefixo:", "Ativ", key="n_a"); w_a = st.number_input("Peso Final (%):", 0, 100, 10, key="w_a"); c_a = st.number_input("Descartar Piores %:", 0, 99, 25, step=5, key="corte_a")
                        st.write("---")
                        st.markdown("### ➕ Categorias Extras")
                        if "num_extras" not in st.session_state: st.session_state.num_extras = 0
                        c_add, c_rm = st.columns(2)
                        if c_add.button("➕ Adicionar Categoria Extra"): st.session_state.num_extras += 1; st.rerun()
                        if c_rm.button("➖ Remover Categoria Extra") and st.session_state.num_extras > 0: st.session_state.num_extras -= 1; st.rerun()
                        extras_list = []
                        if st.session_state.num_extras > 0:
                            cols_ex = st.columns(2)
                            for i in range(st.session_state.num_extras):
                                with cols_ex[i % 2]:
                                    with st.container(border=True):
                                        st.markdown(f"**📌 Extra {i+1}**")
                                        ex_n = st.text_input("Nome:", f"Atividade Extra {i+1}", key=f"ex_n_{i}"); ex_q = st.number_input("Quantidade:", 0, 20, 1, key=f"ex_q_{i}"); ex_w = st.number_input("Peso Final (%):", 0, 100, 10, key=f"ex_w_{i}"); ex_c = st.number_input("Descartar Piores (%):", 0, 99, 0, step=5, key=f"ex_c_{i}")
                                        if ex_n.strip(): extras_list.append((ex_n.strip(), ex_q, ex_w, ex_c))
                        soma_total = w_p + w_l + w_lb + w_a + sum([e[2] for e in extras_list])
                        cor_soma = "green" if abs(soma_total - 100.0) < 0.1 else "red"
                        st.markdown(f"**Soma Total:** <span style='color:{cor_soma}; font-size:18px;'>{soma_total:.1f}%</span>", unsafe_allow_html=True)
                        if st.button("🔄 Aplicar e Recalcular Médias", type="primary", use_container_width=True):
                            if abs(soma_total - 100.0) < 0.1:
                                conn.execute("DELETE FROM planejamento_notas WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                cp = [f"{n_p} {i+1}" for i in range(int(q_p))]; cl = [f"{n_l} {i+1}" for i in range(int(q_l))]; clb = [f"{n_lb} {i+1}" for i in range(int(q_lb))]
                                for nome in cp: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (int(id_t_ativa), d_ativa, nome, float(w_p) / max(1, int(q_p))))
                                for nome in cl: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (int(id_t_ativa), d_ativa, nome, float(w_l) / max(1, int(q_l))))
                                for nome in clb: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (int(id_t_ativa), d_ativa, nome, float(w_lb) / max(1, int(q_lb))))
                                if w_a > 0: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (int(id_t_ativa), d_ativa, f"{n_a} (Dojo)", float(w_a)))
                                for ex_n, ex_q, ex_w, ex_c in extras_list:
                                    ctx = [f"{ex_n} {j+1}" for j in range(int(ex_q))]
                                    for nome in ctx: conn.execute("INSERT INTO planejamento_notas (turma_id, disciplina, nome_avaliacao, peso) VALUES (?,?,?,?)", (int(id_t_ativa), d_ativa, nome, float(ex_w) / max(1, int(ex_q))))
                                conn.commit(); st.success("Planejamento salvo!"); st.rerun()

                    # --- LÓGICA DE DEFINIÇÃO DE COLUNAS ---
                    cp = [f"{n_p} {i+1}" for i in range(int(q_p))]; cl = [f"{n_l} {i+1}" for i in range(int(q_l))]; clb = [f"{n_lb} {i+1}" for i in range(int(q_lb))]; cativs = [f"{n_a} {i+1} ({dt[:5]})" for i, dt in enumerate(datas_unicas)] if w_a > 0 else []
                    cextras = []
                    for ex_n, ex_q, ex_w, ex_c in extras_list: cextras.extend([f"{ex_n} {j+1}" for j in range(int(ex_q))])
                    tent = cp + cl + clb + cativs + cextras
                    df_al = pd.read_sql(f"SELECT a.ra as Matrícula, a.nome as Nome FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}' ORDER BY a.nome", conn)
                    if not df_al.empty:
                        df_nb = pd.read_sql(f"SELECT matricula as Matrícula, avaliacao, nota FROM notas_flexiveis WHERE turma_id={id_t_ativa} AND disciplina='{d_ativa}'", conn)
                        df_piv = df_nb.pivot_table(index='Matrícula', columns='avaliacao', values='nota', aggfunc='max').reset_index() if not df_nb.empty else pd.DataFrame(columns=['Matrícula'])
                        df_at = pd.merge(df_al, df_piv, on="Matrícula", how="left")
                        if len(datas_unicas) > 0 and w_a > 0:
                            for i, dt in enumerate(datas_unicas):
                                ncol = cativs[i]; df_f = df_ativ_sala[df_ativ_sala['data'] == dt]
                                mapa = dict(zip(df_f['Matrícula'], df_f['entregou'].apply(lambda x: 10.0 if x == 1 else 0.0)))
                                df_at[ncol] = df_at['Matrícula'].map(mapa).fillna(0.0)
                        for col in tent:
                            if col not in df_at.columns: df_at[col] = 0.0
                            df_at[col] = pd.to_numeric(df_at[col], errors='coerce').fillna(0.0)
                        df_calc = df_at.copy()
                        def calc_m(row, cols, corte):
                            if not cols: return 0.0
                            notas = sorted(row[cols].tolist(), reverse=True)
                            if corte > 0: manter = max(1, int(len(notas) * (1 - (corte/100.0)))); notas = notas[:manter]
                            return sum(notas) / len(notas) if notas else 0.0
                        mp, ml, mlb, ma = df_calc.apply(lambda r: calc_m(r, cp, c_p), axis=1) if cp else 0.0, df_calc.apply(lambda r: calc_m(r, cl, c_l), axis=1) if cl else 0.0, df_calc.apply(lambda r: calc_m(r, clb, c_lb), axis=1) if clb else 0.0, df_calc.apply(lambda r: calc_m(r, cativs, c_a), axis=1) if cativs else 0.0
                        se = 0.0
                        for ex_n, ex_q, ex_w, ex_c in extras_list:
                            ct = [f"{ex_n} {j+1}" for j in range(int(ex_q))]; me = df_calc.apply(lambda r: calc_m(r, ct, ex_c), axis=1)
                            df_calc[f"Média {ex_n}"] = me; se += me * (ex_w / 100.0)
                        df_calc["MÉDIA FINAL"] = ((mp*(w_p/100)) + (ml*(w_l/100)) + (mlb*(w_lb/100)) + (ma*(w_a/100)) + se).round(2)

                        with t_manual:
                            st.caption("As colunas 'Ativ' são automáticas do Dojo. Outras edite aqui.")
                            cdisp = ["Matrícula", "Nome"] + tent + ["MÉDIA FINAL"]
                            ccfg = {"Matrícula": st.column_config.TextColumn(disabled=True), "Nome": st.column_config.TextColumn(disabled=True), "MÉDIA FINAL": st.column_config.NumberColumn(disabled=True)}
                            for col in cativs: ccfg[col] = st.column_config.NumberColumn(disabled=True)
                            df_ed = st.data_editor(df_calc[cdisp], use_container_width=True, hide_index=True, column_config=ccfg, key="ed_notas_vFinal")
                            if st.button("💾 Salvar Planilha Inteira", type="primary", use_container_width=True):
                                conn.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=?", (int(id_t_ativa), d_ativa))
                                for _, row in df_ed.iterrows():
                                    for col in tent:
                                        if col in cativs: continue
                                        conn.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", (int(id_t_ativa), d_ativa, row['Matrícula'], col, float(row[col])))
                                conn.commit(); st.success("Notas salvas!"); st.rerun()

                        with t_excel:
                            st.markdown("#### 📊 Importar Notas via Planilha")
                            a_imp = cp + cl + clb + cextras
                            if a_imp:
                                alvo = st.selectbox("Lançar em:", a_imp); arq_n = st.file_uploader("Subir arquivo:", type=["xlsx", "csv"])
                                if st.button("📥 Processar Planilha"): st.info("Processando...")
                            else: st.warning("Crie o planejamento primeiro.")

                        with t_auto:
                            st.markdown("#### 🦾 Corretor Automático")
                            a_corr = cp + cl + clb + cextras
                            if a_corr:
                                sel_p = st.selectbox("Lote para corrigir:", ["Todas"] + a_corr)
                                if st.button("🔄 Sincronizar Robô"): st.warning("Conectando...")

                with sub_boletim:
                    st.markdown(f"**🏆 Boletim Mestre: {t_ativa} - {d_ativa}**")
                    df_bol_b = pd.read_sql(f"SELECT a.ra as RA, a.nome as Aluno FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_ativa} AND m.disciplina='{d_ativa}'", conn)
                    if not df_bol_b.empty:
                        hoje = datetime.today().date(); meses = {1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril', 5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'}
                        cft, cfa = st.columns(2); ftempo = cft.selectbox("Período:", ["Semestre Inteiro", f"Este mês ({meses[hoje.month]})", "Hoje", "Esta semana"]); asel = cfa.selectbox("Aluno:", ["Visão Geral"] + df_bol_b['Aluno'].tolist())
                        df_dia_b = pd.read_sql(f"SELECT aluno_ra as RA, data, status FROM diario WHERE turma_id = {id_t_ativa}", conn)
                        df_dojo_b = pd.read_sql(f"SELECT aluno_ra as RA, data, pontos FROM logs_comportamento WHERE turma_id = {id_t_ativa} AND aluno_ra != 'TURMA_INTEIRA'", conn)
                        df_res = df_bol_b.copy()
                        mapa_m = dict(zip(df_calc['Matrícula'], df_calc['MÉDIA FINAL']))
                        df_res['Média'] = df_res['RA'].map(mapa_m).fillna(0.0)
                        st.write("---")
                        c_chart, c_metrics = st.columns([0.4, 0.6])
                        with c_chart:
                            pos = df_dojo_b[df_dojo_b['pontos']>0]['pontos'].sum(); neg = abs(df_dojo_b[df_dojo_b['pontos']<0]['pontos'].sum())
                            if pos+neg > 0:
                                fig = plex.pie(values=[pos, neg], names=['Positivos', 'A Melhorar'], color=['Positivos', 'A Melhorar'], color_discrete_map={'Positivos':'#2ecc71', 'A Melhorar':'#e74c3c'}, hole=0.65)
                                st.plotly_chart(fig, use_container_width=True)
                        with c_metrics:
                            st.metric("MÉDIA GERAL DA TURMA", f"{df_res['Média'].mean():.2f}")
                            st.dataframe(df_res, use_container_width=True, hide_index=True)
                        csv = df_res.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📤 Exportar Boletim", csv, f"Boletim_{t_ativa}.csv", "text/csv")