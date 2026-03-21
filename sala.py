# sala.py
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as plex 
import random
import json
import time
from datetime import datetime, timedelta
from latex_utils import gerar_preview_web

def renderizar_aba_sala():
    with sqlite3.connect('banco_provas.db') as conn:
        # 1. SETUP DE TABELAS
        conn.execute('''CREATE TABLE IF NOT EXISTS diario_conteudo (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, conteudo_real TEXT, observacao TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS atividades_sala (id INTEGER PRIMARY KEY, turma_id INTEGER, disciplina TEXT, data TEXT, aluno_ra TEXT, entregou INTEGER)''')
        
        semestres_db = pd.read_sql("SELECT DISTINCT semestre FROM turmas ORDER BY semestre DESC", conn)
        sem_hj = semestres_db['semestre'].iloc[0] if not semestres_db.empty else "2026.1"
        turmas_df = pd.read_sql(f"SELECT id, nome FROM turmas WHERE semestre='{sem_hj}'", conn)
        
        if turmas_df.empty:
            st.info("Cadastre uma turma primeiro.")
        else:
            c_s1, c_s2, c_s3, c_toggle = st.columns([0.3, 0.3, 0.2, 0.2], vertical_alignment="bottom")
            t_aula_nome = c_s1.selectbox("👥 Turma:", ["-- Escolha --"] + turmas_df['nome'].tolist(), key="final_t_sel")
            with c_toggle:
                modo_projetor = st.toggle("📽️ Modo Projetor", value=True)
            
            if t_aula_nome != "-- Escolha --":
                id_t_sel = int(turmas_df[turmas_df['nome'] == t_aula_nome]['id'].values[0])
                discs_turma = pd.read_sql(f"SELECT DISTINCT disciplina FROM matriculas_disciplina WHERE turma_id={id_t_sel}", conn)
                lista_discs = discs_turma['disciplina'].tolist() if not discs_turma.empty else ["Nenhuma"]
                disc_sel = c_s2.selectbox("🏷️ Disciplina:", ["-- Escolha --"] + lista_discs, key="final_d_sel")

                if disc_sel != "-- Escolha --":
                    data_aula_global = c_s3.date_input("📅 Data:", datetime.today(), key="data_global_sala")
                    data_str_global = data_aula_global.strftime("%d/%m/%Y")

                    st.write("---")
                    col_t1, col_t2 = st.columns([0.4, 0.6])
                    with col_t1:
                        st.markdown("### ⏱️ Cronômetro")
                        t_min = st.number_input("Minutos para atividade:", 1, 120, 15)
                        c_t_btn1, c_t_btn2 = st.columns(2)
                        if c_t_btn1.button("🚀 Iniciar", use_container_width=True):
                            st.session_state['timer_end'] = datetime.now().timestamp() + (t_min * 60); st.rerun()
                        if c_t_btn2.button("⏹️ Parar", use_container_width=True):
                            if 'timer_end' in st.session_state: del st.session_state['timer_end']; st.rerun()
                        
                        if 'timer_end' in st.session_state:
                            st.components.v1.html(f"""
                            <div style="text-align: center; background: #f0f2f6; padding: 10px; border-radius: 10px;">
                                <div id="timer_display" style="font-size: 45px; font-weight: bold; color: #2c3e50; font-family: monospace;">--:--</div>
                                <button id="btn_som" onclick="initAudio()" style="background: #3498db; color: white; border: none; border-radius: 5px; padding: 5px 10px; cursor: pointer;">🔊 Permitir Som</button>
                            </div>
                            <script>
                            let ac = null; function initAudio() {{ window.AudioContext = window.AudioContext || window.webkitAudioContext; ac = new AudioContext(); document.getElementById("btn_som").innerText="✅ OK"; }}
                            function alarme() {{ if(!ac) return; let o=ac.createOscillator(); let g=ac.createGain(); o.type='sine'; o.frequency.setValueAtTime(523.25, ac.currentTime); g.gain.setValueAtTime(0.4, ac.currentTime); g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime+1.5); o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime+1.5); }}
                            const i = setInterval(() => {{
                                let s = Math.floor({st.session_state['timer_end']} - (Date.now()/1000));
                                if(s > 0) {{ document.getElementById("timer_display").innerText = Math.floor(s/60).toString().padStart(2,'0') + ":" + (s%60).toString().padStart(2,'0'); }}
                                else {{ document.getElementById("timer_display").innerText = "00:00"; alarme(); clearInterval(i); }}
                            }}, 1000);
                            </script>""", height=110)

                    with col_t2:
                        st.markdown("### 🔊 Medidor de Ruído")
                        st.components.v1.html("""
                            <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; background: #f0f2f6; height: 110px; border-radius: 10px; padding: 10px; box-sizing: border-box;">
                                <canvas id="meter" width="300" height="35" style="background: #ffffff; border-radius: 5px; box-shadow: inset 0px 2px 5px rgba(0,0,0,0.05);"></canvas>
                                <div id="st" style="font-size:14px; font-weight:bold; margin-top:10px; color: #2c3e50;">🎤 Aguardando Microfone...</div>
                            </div>
                            <script>
                            navigator.mediaDevices.getUserMedia({audio:true}).then(s=>{
                                const ac=new AudioContext();
                                const an=ac.createAnalyser();
                                const mic=ac.createMediaStreamSource(s);
                                mic.connect(an);
                                const d=new Uint8Array(an.frequencyBinCount);
                                const can=document.getElementById('meter');
                                const ctx=can.getContext('2d');
                                function draw(){
                                    an.getByteFrequencyData(d);
                                    let av=d.reduce((a,b)=>a+b)/d.length;
                                    ctx.clearRect(0,0,300,35);
                                    ctx.fillStyle=(av>50?"#e74c3c":"#2ecc71");
                                    ctx.fillRect(0,0,(av/100)*300,35);
                                    document.getElementById('st').innerHTML=(av>50?"🛑 <b>Silêncio! Muito Barulho</b>":"✅ <b>Nível de Ruído OK</b>");
                                    requestAnimationFrame(draw);
                                }
                                draw();
                            }).catch(err => {
                                document.getElementById('st').innerHTML="⚠️ Microfone Bloqueado";
                            });
                            </script>
                        """, height=130)

                    st.write("---")
                    
                    try:
                        conn.execute('''CREATE TABLE IF NOT EXISTS duvidas_alunos (id INTEGER PRIMARY KEY AUTOINCREMENT, turma_id INTEGER, disciplina TEXT, aluno_ra TEXT, data TEXT, mensagem TEXT, respondida BOOLEAN DEFAULT 0)''')
                        df_duvidas = pd.read_sql(f"SELECT id FROM duvidas_alunos WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND respondida=0", conn)
                        if not df_duvidas.empty:
                            st.error(f"🚨 **VOCÊ TEM {len(df_duvidas)} NOVA(S) DÚVIDA(S)!** Verifique a aba de Dúvidas.")
                    except: pass
                    
                    modo_aula = st.radio("Ação:", ["⭐ Comportamento", "🙋 Fazer Chamada", "✍️ Atividade de Sala", "🎲 Sortear Aluno", "👥 Grupos", "📖 Registrar Diário", "📩 Responder Dúvidas"], horizontal=True)
                    
                    alunos_sala = pd.read_sql(f"SELECT a.ra, a.nome, a.avatar_style, a.avatar_opts, a.observacoes FROM alunos a JOIN matriculas_disciplina m ON a.id = m.aluno_id WHERE m.turma_id={id_t_sel} AND m.disciplina='{disc_sel}' ORDER BY a.nome", conn)

                    if modo_aula == "⭐ Comportamento":
                        df_p = pd.read_sql(f"SELECT aluno_ra, SUM(CASE WHEN data='{data_str_global}' AND pontos>0 THEN pontos ELSE 0 END) as dia_pos, SUM(CASE WHEN data='{data_str_global}' AND pontos<0 THEN pontos ELSE 0 END) as dia_neg, SUM(pontos) as total_geral FROM logs_comportamento WHERE turma_id={id_t_sel} GROUP BY aluno_ra", conn)
                        df_t_pts = pd.read_sql(f"SELECT SUM(CASE WHEN data='{data_str_global}' AND pontos>0 THEN pontos ELSE 0 END) as d_pos, SUM(CASE WHEN data='{data_str_global}' AND pontos<0 THEN pontos ELSE 0 END) as d_neg, SUM(pontos) as t_geral FROM logs_comportamento WHERE turma_id={id_t_sel} AND aluno_ra='TURMA_INTEIRA'", conn).iloc[0].fillna(0)
                        alunos_dojo = pd.merge(alunos_sala, df_p, left_on='ra', right_on='aluno_ra', how='left').fillna(0)

                        @st.dialog("Lançar FeedBack")
                        def modal_feedback(ra, nome):
                            st.write(f"Dar ponto para: **{nome}**")
                            def b_salvar(m, p):
                                with sqlite3.connect('banco_provas.db') as c:
                                    c.execute("INSERT INTO logs_comportamento (aluno_ra, turma_id, data, pontos, comentario, tipo) VALUES (?,?,?,?,?,?)", (ra, id_t_sel, data_str_global, p, m, "Feedback"))
                                st.rerun()
                            c1, c2 = st.columns(2)
                            if c1.button("❤️ Ajuda"): b_salvar("Ajudando os colegas", 1.0)
                            if c2.button("🧐 Foco"): b_salvar("Focado", 1.0)
                            if c1.button("💡 Participação"): b_salvar("Participação", 1.0)
                            if c2.button("🏔️ Persistência"): b_salvar("Persistência", 1.0)
                            if c1.button("📱 Celular"): b_salvar("Usando celular", -1.0)
                            if c2.button("🗣️ Conversa"): b_salvar("Conversa paralela", -1.0)
                            st.write("---")
                            p_i = st.number_input("Pts:", value=1.0, step=0.5); m_i = st.text_input("Motivo:")
                            if st.button("💾 Gravar"): b_salvar(m_i if m_i else "Avaliação", p_i)

                        cols = st.columns(6)
                        with cols[0]:
                            with st.container(border=True):
                                st.markdown(f"<div style='text-align:center; height:140px;'><span style='font-size: 38px;'>🌍</span><br><b>Turma</b><br><small style='color:green;'>●</small>{int(df_t_pts['d_pos'])}|<small style='color:red;'>●</small>{int(abs(df_t_pts['d_neg']))}<br><small>⭐{int(df_t_pts['t_geral'])}</small></div>", unsafe_allow_html=True)
                                if st.button("Feedback", key="bt_t", use_container_width=True): modal_feedback('TURMA_INTEIRA', 'Toda a Turma')
                        
                        for idx, row in alunos_dojo.iterrows():
                            with cols[(idx+1)%6]:
                                with st.container(border=True):
                                    opts = row['avatar_opts'] if pd.notna(row['avatar_opts']) else ""
                                    url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={row['ra']}{opts}"
                                    st.markdown(f"<div style='text-align:center; height:140px;'><img src='{url}' width='45'><br><b>{row['nome'].split()[0]}</b><br><small style='color:green;'>●</small>{int(row['dia_pos'])}|<small style='color:red;'>●</small>{int(abs(row['dia_neg']))}<br><small>⭐{int(row['total_geral'])}</small></div>", unsafe_allow_html=True)
                                    if st.button("Feedback", key=f"f_{row['ra']}", use_container_width=True): modal_feedback(row['ra'], row['nome'])

                    elif modo_aula == "🙋 Fazer Chamada":
                        df_f = pd.read_sql(f"SELECT aluno_ra, COUNT(*) as total FROM diario WHERE turma_id={id_t_sel} AND status='Ausente' GROUP BY aluno_ra", conn)
                        dict_f = dict(zip(df_f['aluno_ra'], df_f['total']))
                        if "m_ch" not in st.session_state:
                            df_dia = pd.read_sql(f"SELECT aluno_ra, status FROM diario WHERE turma_id={id_t_sel} AND data='{data_str_global}'", conn)
                            freq = dict(zip(df_dia['aluno_ra'], df_dia['status']))
                            st.session_state.m_ch = {r['ra']: freq.get(r['ra'], "Presente") for _, r in alunos_sala.iterrows()}
                        
                        c1, c2, c3, _ = st.columns([0.4, 0.4, 0.4, 2])
                        if c1.button("🟢 Presentes"): 
                            for r in st.session_state.m_ch: st.session_state.m_ch[r] = "Presente"
                            st.rerun()
                        if c2.button("🔴 Ausentes"): 
                            for r in st.session_state.m_ch: st.session_state.m_ch[r] = "Ausente"
                            st.rerun()
                        if c3.button("💾 SALVAR"):
                            for ra, stt in st.session_state.m_ch.items():
                                conn.execute("DELETE FROM diario WHERE turma_id=? AND data=? AND aluno_ra=?", (id_t_sel, data_str_global, ra))
                                conn.execute("INSERT INTO diario (turma_id, data, aluno_ra, presente, status) VALUES (?,?,?,?,?)", (id_t_sel, data_str_global, ra, stt!="Ausente", stt))
                            conn.commit(); st.success("Salvo!"); st.rerun()
                        
                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']; s = st.session_state.m_ch.get(ra, "Presente")
                            opts = row['avatar_opts'] if pd.notna(row['avatar_opts']) else ""
                            url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={ra}{opts}"
                            with cols_f[idx%6]:
                                with st.container(border=True):
                                    st.markdown(f"<div style='text-align:center;'><img src='{url}' width='45'><br><b>{row['nome'].split()[0]}</b><br><small style='color:red;'>Faltas: {dict_f.get(ra,0)}</small></div>", unsafe_allow_html=True)
                                    lbl = {"Presente":"🟢", "Ausente":"🔴", "Atrasado":"🟡"}[s]
                                    if st.button(lbl, key=f"ch_{ra}", use_container_width=True):
                                        st.session_state.m_ch[ra] = {"Presente":"Ausente", "Ausente":"Atrasado", "Atrasado":"Presente"}[s]; st.rerun()

                    elif modo_aula == "✍️ Atividade de Sala":
                        df_h = pd.read_sql(f"SELECT data, aluno_ra, entregou FROM atividades_sala WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}'", conn)
                        tot_aulas = df_h['data'].nunique()
                        meta = tot_aulas - int(tot_aulas * 0.25) if tot_aulas > 0 else 0
                        st.info(f"📊 Meta: {meta} entregas (Fator descarte 25% aplicado)")
                        if "m_ativ" not in st.session_state:
                            df_hj = df_h[df_h['data'] == data_str_global]
                            d_hj = dict(zip(df_hj['aluno_ra'], df_hj['entregou']))
                            st.session_state.m_ativ = {r['ra']: d_hj.get(r['ra'], 0) for _, r in alunos_sala.iterrows()}
                        if st.button("💾 Salvar Atividades", type="primary"):
                            for ra, ent in st.session_state.m_ativ.items():
                                conn.execute("DELETE FROM atividades_sala WHERE turma_id=? AND disciplina=? AND data=? AND aluno_ra=?", (id_t_sel, disc_sel, data_str_global, ra))
                                conn.execute("INSERT INTO atividades_sala (turma_id, disciplina, data, aluno_ra, entregou) VALUES (?,?,?,?,?)", (id_t_sel, disc_sel, data_str_global, ra, ent))
                            conn.commit(); st.success("Salvo!"); st.rerun()
                        cols_f = st.columns(6)
                        for idx, row in alunos_sala.iterrows():
                            ra = row['ra']; ent_hj = st.session_state.m_ativ.get(ra, 0)
                            tot_al = df_h[(df_h['aluno_ra']==ra) & (df_h['entregou']==1)].shape[0]
                            url = f"https://api.dicebear.com/9.x/{row['avatar_style']}/svg?seed={ra}{(row['avatar_opts'] if pd.notna(row['avatar_opts']) else '')}"
                            with cols_f[idx%6]:
                                with st.container(border=True):
                                    cor = "green" if tot_al >= meta and meta > 0 else "red"
                                    st.markdown(f"<div style='text-align:center;'><img src='{url}' width='45'><br><b>{row['nome'].split()[0]}</b><br><small style='color:{cor};'>Fez: {tot_al}/{meta}</small></div>", unsafe_allow_html=True)
                                    if st.button("✅" if ent_hj else "❌", key=f"at_{ra}", use_container_width=True):
                                        st.session_state.m_ativ[ra] = 1 if ent_hj==0 else 0; st.rerun()

                    elif modo_aula == "🎲 Sortear Aluno":
                        if not alunos_sala.empty:
                            if st.button("🎲 Novo Sorteio", use_container_width=True): st.session_state.sort_al = alunos_sala.sample(1).iloc[0]
                            if "sort_al" in st.session_state:
                                s = st.session_state.sort_al
                                url = f"https://api.dicebear.com/9.x/{s['avatar_style']}/svg?seed={s['ra']}{(s['avatar_opts'] if pd.notna(s['avatar_opts']) else '')}"
                                st.markdown(f"<div style='background:#1c9e5e; padding:30px; border-radius:15px; text-align:center;'><div style='background:white; padding:20px; border-radius:15px; display:inline-block;'><img src='{url}' width='130'><h2>{s['nome']}</h2></div></div>", unsafe_allow_html=True)

                    elif modo_aula == "👥 Grupos":
                        # Busca o planejamento para saber onde lançar a nota
                        df_plan = pd.read_sql(f"SELECT nome_avaliacao FROM planejamento_notas WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}'", conn)
                        atividades_validas = df_plan['nome_avaliacao'].tolist()
                        
                        if not atividades_validas: 
                            st.error("⚠️ Nenhuma atividade configurada em 'Pesos e Quantidades'."); st.stop()
                        
                        if "gs_m" not in st.session_state: st.session_state.gs_m = []
                        
                        col_sel, col_undo = st.columns([0.75, 0.25], vertical_alignment="bottom")
                        atividade_escolhida = col_sel.selectbox("📌 Selecione a atividade para o grupo:", atividades_validas, key=f"g_act_{id_t_sel}")
                        
                        if st.session_state.gs_m:
                            if col_undo.button("🗑️ Desfazer Grupos", use_container_width=True): 
                                st.session_state.gs_m = []; st.rerun()

                        st.markdown("---")

                        if not st.session_state.gs_m:
                            # A OPÇÃO MANUAL VOLTOU! 
                            t_formacao = st.radio("Como deseja formar os grupos?", ["Aleatório", "Manual"], horizontal=True)

                            if t_formacao == "Aleatório":
                                n_g = st.number_input("Alunos por grupo:", 1, 10, 4)
                                if st.button("🎲 Gerar Grupos Aleatórios", use_container_width=True):
                                    sh = alunos_sala.sample(frac=1).to_dict('records')
                                    st.session_state.gs_m = [sh[i:i + n_g] for i in range(0, len(sh), n_g)]
                                    st.rerun()
                            else:
                                # --- LÓGICA MANUAL RESTAURADA ---
                                qtd_grupos = st.number_input("Quantos grupos deseja criar?", 1, 20, 4)
                                st.caption("Selecione os membros de cada equipe:")
                                
                                dict_alunos = {f"{row['ra']} - {row['nome']}": row.to_dict() for _, row in alunos_sala.iterrows()}
                                grupos_temporarios = []
                                
                                for i in range(qtd_grupos):
                                    membros = st.multiselect(f"Membros do Grupo {i+1}:", options=list(dict_alunos.keys()), key=f"sel_gm_{i}")
                                    grupos_temporarios.append([dict_alunos[m] for m in membros])
                                
                                if st.button("✅ Confirmar Grupos Manuais", type="primary", use_container_width=True):
                                    filtrados = [g for g in grupos_temporarios if len(g) > 0]
                                    if filtrados:
                                        st.session_state.gs_m = filtrados
                                        st.rerun()
                                    else:
                                        st.warning("Selecione pelo menos um aluno.")

                        else:
                            # EXIBIÇÃO DOS CARDS (COM AVATARES V9)
                            st.markdown(f"**🏷️ Lançando nota em:** `{atividade_escolhida}`")
                            cg = st.columns(3)
                            for i, g in enumerate(st.session_state.gs_m):
                                with cg[i % 3]:
                                    with st.container(border=True):
                                        st.write(f"**Grupo {i+1}**")
                                        # Renderiza os avatares pequenos lado a lado
                                        avs_h = "".join([f"<img src='https://api.dicebear.com/9.x/{a['avatar_style']}/svg?seed={a['ra']}{(a['avatar_opts'] if pd.notna(a['avatar_opts']) else '')}' width='35' style='margin-right:2px;'>" for a in g])
                                        st.markdown(avs_h, unsafe_allow_html=True)
                                        
                                        st.write("")
                                        c_pts, c_btn = st.columns([0.5, 0.5], vertical_alignment="bottom")
                                        pts_v = c_pts.number_input("Nota:", 0.0, 10.0, 1.0, 0.5, key=f"pg_{i}")
                                        
                                        if c_btn.button("💾 Lançar", key=f"bg_{i}", use_container_width=True):
                                            with sqlite3.connect('banco_provas.db') as c_n:
                                                for al in g:
                                                    c_n.execute("DELETE FROM notas_flexiveis WHERE turma_id=? AND disciplina=? AND matricula=? AND avaliacao=?", (id_t_sel, disc_sel, al['ra'], atividade_escolhida))
                                                    c_n.execute("INSERT INTO notas_flexiveis (turma_id, disciplina, matricula, avaliacao, nota) VALUES (?,?,?,?,?)", (id_t_sel, disc_sel, al['ra'], atividade_escolhida, pts_v))
                                            st.toast(f"Nota {pts_v} salva para o Grupo {i+1}!")

                    elif modo_aula == "📖 Registrar Diário":
                        exp = pd.read_sql(f"SELECT tema FROM cronograma_detalhado WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND data='{data_str_global}'", conn)
                        st.info(f"🎯 Planejado: {exp['tema'].iloc[0] if not exp.empty else 'Não agendado'}")
                        real_db = pd.read_sql(f"SELECT conteudo_real FROM diario_conteudo WHERE turma_id={id_t_sel} AND disciplina='{disc_sel}' AND data='{data_str_global}'", conn)
                        c_real = st.text_area("O que foi dado hoje?", value=real_db['conteudo_real'].iloc[0] if not real_db.empty else "")
                        if st.button("💾 Salvar Diário", type="primary", use_container_width=True):
                            conn.execute("DELETE FROM diario_conteudo WHERE turma_id=? AND disciplina=? AND data=?", (id_t_sel, disc_sel, data_str_global))
                            conn.execute("INSERT INTO diario_conteudo (turma_id, disciplina, data, conteudo_real) VALUES (?,?,?,?)", (id_t_sel, disc_sel, data_str_global, c_real))
                            conn.commit(); st.success("Diário atualizado!")

                    elif modo_aula == "📩 Responder Dúvidas":
                        df_duv = pd.read_sql(f"SELECT d.*, a.nome FROM duvidas_alunos d JOIN alunos a ON d.aluno_ra = a.ra WHERE d.turma_id={id_t_sel} AND d.disciplina='{disc_sel}' ORDER BY d.respondida ASC, d.id DESC", conn)
                        if df_duv.empty: st.info("Sem dúvidas!")
                        else:
                            for _, d_row in df_duv.iterrows():
                                bg = "#fdf1f0" if d_row['respondida'] == 0 else "#f0fdf4"
                                st.markdown(f"<div style='border-radius:10px; padding:15px; margin-bottom:10px; background:{bg};'><b>{d_row['nome']}</b>: {d_row['mensagem']}</div>", unsafe_allow_html=True)
                                if d_row['respondida'] == 0:
                                    if st.button("✅ Resolvido", key=f"ld_{d_row['id']}"):
                                        conn.execute(f"UPDATE duvidas_alunos SET respondida=1 WHERE id={d_row['id']}"); conn.commit(); st.rerun()