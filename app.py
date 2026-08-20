# ================= VIEW 1: COMMAND CENTER =================
    if selected_nav == "📊 Command Center":
        st.markdown(f"### ☀️ Autonomous AI Performance Coach • Command Center")
        
        st.markdown(f"""
        <div style="background-color: #fef9e7; border: 1px solid #f9e79f; padding: 16px; border-radius: 14px; margin-bottom: 16px;">
            <span style="font-size: 0.75rem; font-weight: bold; color: #d68910; background: #fcf3cf; padding: 2px 6px; border-radius: 4px;">📊 INTERVALS.ICU & GARMIN SYNC ACTIVE</span>
            <div style="font-weight: bold; font-size: 1.1rem; margin-top: 4px;">Target Race: {st.session_state.goals['event_name']} ({days_left} days left — {race_date_obj.strftime('%B %d, %Y')})</div>
            <div style="color: #666; font-size: 0.85rem; margin-top: 4px;">Objective: {st.session_state.goals['target_metric']}</div>
            <hr style="margin: %10px 0; border-top: 1px solid #fce881;">
            <div style="font-size: 0.9rem; font-weight: 500; color: #333;">
                {'🟢 <strong>Readiness High:</strong> Telemetry verified via Garmin/Intervals.icu. Form (TSB) is optimal for hard efforts.' if tsb >= -15 else '🟡 <strong>Fatigue Warning:</strong> Telemetry shows elevated stress. Prioritize sleep and recovery pacing.'}
            </div>
        </div>
        """, unsafe_allow_html=True)

        c_met1, c_met2, c_met3, c_met4 = st.columns(4)
        with c_met1: st.metric("Fitness (CTL)", round(ctl, 1))
        with c_met2: st.metric("Fatigue (ATL)", round(atl, 1))
        with c_met3: st.metric("Form (TSB)", round(tsb, 1))
        with c_met4: st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

        st.markdown("---")
        st.markdown("#### 📈 Deep 90-Day Training Load & Progression Trend Analysis")

        # Initialize session state for trends if not present
        if "cached_trend_analysis" not in st.session_state:
            st.session_state.cached_trend_analysis = None
        if "trend_analysis_timestamp" not in st.session_state:
            st.session_state.trend_analysis_timestamp = None

        if st.button("🚀 Run 90-Day Trend Synthesis", type="primary"):
            trend_payload = "\n".join([
                "Perform a rigorous, detailed 90-day sports science trend analysis based on my wellness and training data:",
                f"CTL (Fitness): {ctl}, ATL (Fatigue): {atl}, TSB (Form): {tsb}",
                f"Recent Activities Summary: {activities_data[:25] if activities_data else 'None'}",
                f"Target Event: {st.session_state.goals['event_name']} in {days_left} days.",
                f"Objective: {st.session_state.goals['target_metric']}",
                "",
                "Provide a structured analysis covering fitness trajectory, consistency, climbing readiness, and next steps. Only mention equipment or physical limitations if there is a specific issue or impact."
            ])

            with st.spinner("Synthesizing 90-day performance trends..."):
                try:
                    trend_res, _ = execute_multiprovider_generation(trend_payload, preferred_provider=selected_provider)
                    st.session_state.cached_trend_analysis = trend_res
                    st.session_state.trend_analysis_timestamp = datetime.datetime.now().strftime("%B %d, %Y at %H:%M")
                except Exception as e:
                    st.error(f"Trend synthesis failed: {e}")

        # Persistent display: Stays right here on the Command Center until manually cleared or refreshed
        if st.session_state.cached_trend_analysis:
            st.caption(f"🕒 Analysis generated on: **{st.session_state.trend_analysis_timestamp}**")
            st.markdown(st.session_state.cached_trend_analysis)
            
            c_tr1, c_tr2 = st.columns(2)
            with c_tr1:
                if st.button("💬 Discuss These Trends With Coach", key="discuss_trends_btn", use_container_width=True):
                    # Also push it into chat memory so the coach can reference it when you arrive at the tab
                    st.session_state.messages.append({
                        "role": "user", 
                        "content": f"Here is my recent 90-day training trend analysis that I ran on the Command Center:\n\n{st.session_state.cached_trend_analysis}\n\nBased on my goal of '{st.session_state.goals['target_metric']}', am I progressing correctly?"
                    })
                    st.session_state.messages.append({
                        "role": "model", 
                        "content": "I have reviewed your 90-day trend report. What specific part of your fitness trajectory or training load would you like to tweak?"
                    })
                    st.session_state.active_nav = "🤖 AI Coach & Sparring"
                    st.rerun()
            with c_tr2:
                if st.button("🗑️ Clear Trend Analysis", key="clear_trend_btn", use_container_width=True):
                    st.session_state.cached_trend_analysis = None
                    st.session_state.trend_analysis_timestamp = None
                    st.rerun()
