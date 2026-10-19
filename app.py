"""Monitoring dashboard for the independent, copy-only screenshot service."""
import base64
import colorsys
from html import escape
from datetime import datetime
import os
import sqlite3
import subprocess

import plotly.graph_objects as go
import streamlit as st

from config import PROJECT_ROOT, Settings
from src.background_service import status
from src.metadata_store import MetadataStore, make_snippet
from src.ocr_engine import check_tesseract
from src import dashboard_data as data
from styles import STYLE

PAGES = ['Dashboard', 'Screenshot Gallery', 'Live Monitor', 'History & Search', 'Settings']
PAGE_ICONS = {'Dashboard': 'home', 'Screenshot Gallery': 'photo_library', 'Live Monitor': 'monitor_heart',
              'History & Search': 'history', 'Settings': 'settings'}
STORAGE_BUDGET_GB = 1  # the sidebar meter shows your organized-screenshots folder against this budget; change freely

# One distinct accent colour per category (checked so no two are perceptually close).
# Donut slices and legend dots use the accent; pills use a light tint of it with a darker text shade.
CATEGORY_ACCENTS = {
    'Programming': '#4F46E5', 'Education': '#F59E0B', 'Health': '#14B8A6', 'Work': '#475569',
    'Communication': '#22C55E', 'Web Search': '#0EA5E9', 'Shopping': '#F97316', 'Finance': '#84CC16',
    'Travel': '#EF4444', 'Entertainment': '#EC4899', 'Design': '#D946EF', 'Personal': '#92400E',
    'AI Chat': '#0F766E', 'System & Files': '#1E3A8A', 'Uncategorized': '#CBD5E1',
}


def _mix(hex_color, other, amount):
    """Blend hex_color toward `other` by `amount` (0..1)."""
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02X%02X%02X' % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def accent_for(category):
    name = category or 'Uncategorized'
    if name in CATEGORY_ACCENTS:
        return CATEGORY_ACCENTS[name]
    # Unknown (user-added) category: a stable colour derived from its name.
    r, g, b = colorsys.hls_to_rgb((sum(map(ord, name)) * 47 % 360) / 360, 0.45, 0.65)
    return '#%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))


def colors_for(category):
    """(background, text) for a category pill."""
    if (category or 'Uncategorized') == 'Uncategorized':
        return '#F1F5F9', '#64748B'
    accent = accent_for(category)
    return _mix(accent, '#FFFFFF', 0.86), _mix(accent, '#000000', 0.38)


@st.cache_data(ttl=60)
def ocr_status():
    return check_tesseract(Settings())


@st.cache_data(ttl=300, show_spinner=False)
def cached_thumb(path):
    return data.thumb_b64(path)


@st.cache_data(ttl=60, show_spinner=False)
def cached_folder_size(path):
    return data.folder_size(path)


# ---------------------------------------------------------------- small UI helpers
def header(title, subtitle):
    st.html(f'<div class="page-heading"><div class="eyebrow">SMART SCREENSHOT ORGANIZER</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>')


def table(items):
    st.dataframe([{'ID': r.id, 'Filename': r.new_name or r.original_name,
                   'Category': r.category or 'Uncategorized', 'Status': r.status.title(),
                   'Processed': data.relative_time(r.processed_at)} for r in items], hide_index=True, width='stretch')


ICON_PATHS = {
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
    'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2"/>',
    'activity': '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    'folder': '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    'zap': '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    'eye': '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    'pie': '<path d="M21.2 15.9A10 10 0 1 1 8 2.8"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
    'chart': '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    'shield': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
}


def data_uri(svg):
    """Inline SVGs get stripped by Streamlit's sanitizer; <img> data URIs survive."""
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def icon(name, color='#4F46E5', size=22):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICON_PATHS[name]}</svg>')
    return f'<img src="{data_uri(svg)}" width="{size}" height="{size}" alt="">'


def card_title(name, color, tint, title, sub='', right=''):
    sub_html = f'<div class="card-sub">{escape(sub)}</div>' if sub else ''
    return (f'<div class="ct"><span class="ct-ico" style="background:{tint}">{icon(name, color, 20)}</span>'
            f'<div><div class="card-title">{escape(title)}</div>{sub_html}</div>'
            f'<div class="ct-right">{right}</div></div>')


def sparkline(values, color, w=110, h=44):
    values = list(values) or [0, 0]
    if len(values) < 2:
        values = values * 2
    top = max(max(values), 1)
    step = w / (len(values) - 1)
    points = ' '.join(f'{i * step:.1f},{h - 4 - (v / top) * (h - 8):.1f}' for i, v in enumerate(values))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
           f'<polygon points="0,{h} {points} {w},{h}" fill="{color}" fill-opacity=".14"/>'
           f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.2" '
           f'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return f'<img src="{data_uri(svg)}" width="{w}" height="{h}" alt="">'


def change(current, previous, label):
    if previous == 0:
        return (f'▲ {current} {label}', 'up') if current else ('No change', 'flat')
    pct = round((current - previous) / previous * 100)
    return (f'{"▲" if pct >= 0 else "▼"} {abs(pct)}% from {label}', 'up' if pct >= 0 else 'down')


def kpi(icon, tint, label, value, sub, sub_class='flat', spark=''):
    return (f'<div class="kpi"><div class="kpi-icon" style="background:{tint}">{icon}</div>'
            f'<div><div class="kpi-label">{escape(label)}</div><div class="kpi-value">{value}</div></div>'
            f'<div class="kpi-spark">{spark}</div><div class="kpi-sub {sub_class}">{sub}</div></div>')


def pill(category):
    bg, fg = colors_for(category)
    return f'<span class="pill" style="background:{bg};color:{fg}">{escape(category or "Uncategorized")}</span>'


def activity_table(rows):
    body = ''
    for r in rows:
        thumb = cached_thumb(r.destination_path)
        image = f'<img src="{thumb}" alt="">' if thumb else '<div class="thumb-missing"></div>'
        ok = r.status in ('copied', 'moved')
        dot = '#22C55E' if ok else '#EF4444'
        label = 'Completed' if ok else r.status.title()
        body += (f'<tr><td>{image}</td><td class="orig">{escape(r.original_name or "")}</td>'
                 f'<td class="new">{escape(r.new_name or "—")}</td><td>{pill(r.category)}</td>'
                 f'<td class="nw"><span class="dot" style="background:{dot}"></span>{escape(label)}</td>'
                 f'<td class="nw">{escape(data.relative_time(r.processed_at))}</td><td class="kebab">⋮</td></tr>')
    return ('<div class="act-wrap"><table class="act"><thead><tr><th>Preview</th><th>Original filename</th>'
            f'<th>New filename</th><th>Category</th><th>Status</th><th>Processed</th><th></th></tr></thead><tbody>{body}</tbody></table></div>')


def flash_toast():
    if 'flash' in st.session_state:
        ok, message = st.session_state.pop('flash')
        st.toast(message or ('Done.' if ok else 'The action failed.'), icon=':material/check_circle:' if ok else ':material/error:')


def run_action(action, config):
    if action == 'folder':
        if config and hasattr(os, 'startfile'):
            os.startfile(config.destination)
        else:
            st.toast('Opening the folder is only supported on Windows.', icon=':material/info:')
        return
    try:
        with st.spinner('Working…'):
            ok, message = data.control(PROJECT_ROOT, action)
        st.session_state.flash = (ok, message)
        st.rerun()
    except (OSError, subprocess.TimeoutExpired) as exc:
        st.warning(f'Could not confirm completion: {exc}')


def go_search():
    query = st.session_state.get('global_search', '').strip()
    if query:
        st.session_state.history_query = query
        st.session_state.page = 'History & Search'
        st.session_state.global_search = ''


# ---------------------------------------------------------------- dashboard sections
def dashboard_header(ready, active):
    left, right = st.columns([3, 2], vertical_alignment='center')
    with left:
        ok = ready and active
        text = 'OCR active' if ok else ('Automation inactive' if ready else 'OCR unavailable')
        st.html(f'<div class="dash-title"><h1>Dashboard</h1><span class="status-pill{"" if ok else " off"}"><i></i>{text}</span></div>'
                '<p class="dash-sub">Automatically organize, rename and find your screenshots using OCR.</p>')
    with right:
        st.text_input('Search', placeholder='Search screenshots, text or filenames…', icon=':material/search:',
                      key='global_search', label_visibility='collapsed', on_change=go_search)


def kpi_row(store, automation, ready):
    values = data.metrics(store.db_path)
    days = data.daily_counts(store.db_path, 30)
    unc_days = data.daily_counts(store.db_path, 30, uncategorized=True)
    series = list(days.values())
    this_week, last_week = sum(series[-7:]), sum(series[-14:-7])
    week_text, week_cls = change(this_week, last_week, 'last week')
    day_text, day_cls = change(series[-1], series[-2], 'yesterday')
    unc_today = list(unc_days.values())[-1]
    active = automation.get('active', False)
    cards = [
        kpi(icon('image', '#4F46E5', 26), '#E0E7FF', 'Total screenshots', f'{values["total"]:,}', week_text, week_cls, sparkline(series[-14:], '#4F46E5')),
        kpi(icon('file', '#16A34A', 26), '#DCFCE7', 'Processed today', f'{values["today"]:,}', day_text, day_cls, sparkline(series[-14:], '#16A34A')),
        kpi(icon('activity', '#7C3AED', 26), '#EDE9FE', 'Automation status', 'Active' if active else 'Inactive',
            '● OCR &amp; auto-copy running' if active and ready else '● Service not running',
            'up' if active else 'flat'),
        kpi(icon('folder', '#F97316', 26), '#FFEDD5', 'Uncategorized', f'{values["uncategorized"]:,}', f'{unc_today} new today',
            'down' if unc_today else 'flat', sparkline(list(unc_days.values())[-14:], '#F97316')),
    ]
    for column, card in zip(st.columns(4), cards):
        column.html(card)
    return values


def recent_activity(store):
    with st.container(border=True):
        top, link = st.columns([4, 1], vertical_alignment='center')
        top.html(card_title('clock', '#4F46E5', '#EEF2FF', 'Recent activity', 'Latest processed screenshots and their results.'))
        with link.container(key='view_all_wrap'):
            st.button('View all  →', key='view_all', width='stretch',
                      on_click=lambda: st.session_state.update(page='History & Search'))
        rows = data.records(store, limit=6)
        if rows:
            st.html(activity_table(rows))
        else:
            st.info('Your library starts with your next screenshot. When automation is active, it will appear here automatically.')


def categories_card(values):
    with st.container(border=True):
        st.html(card_title('pie', '#7C3AED', '#F3E8FF', 'Screenshot categories'))
        cats = values['categories']
        if not cats:
            st.caption('Category totals will appear after the first successful copy.')
            return
        # Largest first, Uncategorized last, so neighbouring slices differ and the order is stable.
        ordered = sorted(cats.items(), key=lambda kv: (kv[0] == 'Uncategorized', -kv[1], kv[0]))
        names, counts = [k for k, _ in ordered], [v for _, v in ordered]
        total = sum(counts)
        palette = [accent_for(n) for n in names]
        fig = go.Figure(go.Pie(labels=names, values=counts, hole=0.64, sort=False, textinfo='none',
                               marker=dict(colors=palette, line=dict(color='#fff', width=2))))
        fig.update_layout(height=210, margin=dict(l=0, r=0, t=6, b=6), showlegend=False,
                          paper_bgcolor='rgba(0,0,0,0)',
                          annotations=[dict(text=f'<b>{total:,}</b><br>total', showarrow=False, font=dict(size=15, color='#17153B'))])
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        rows = ''.join(f'<div><span class="dot" style="background:{c}"></span><span class="n">{escape(n)}</span>'
                       f'<span class="p">{round(v / total * 100)}%</span><span class="c">{v:,}</span></div>'
                       for n, v, c in zip(names, counts, palette))
        st.html(f'<div class="legend">{rows}</div>')


def trend_card(store):
    with st.container(border=True):
        head, toggle = st.columns([1, 1], vertical_alignment='center')
        head.html(card_title('chart', '#4F46E5', '#EEF2FF', 'Activity trend'))
        choice = toggle.segmented_control('Range', ['7 days', '30 days'], default='7 days',
                                          key='trend_range', label_visibility='collapsed') or '7 days'
        span = 7 if choice == '7 days' else 30
        counts = list(data.daily_counts(store.db_path, span).items())
        labels = [d.strftime('%b %d') for d, _ in counts]
        values = [c for _, c in counts]
        shades = ['#C7D2FE'] * (len(values) - 1) + ['#4F46E5']
        fig = go.Figure(go.Bar(x=labels, y=values, marker=dict(color=shades, cornerradius=6),
                               hovertemplate='%{x}: %{y} screenshots<extra></extra>'))
        fig.update_layout(height=270, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(0,0,0,0)', bargap=0.35,
                          xaxis=dict(showgrid=False, tickfont=dict(size=11, color='#64748B')),
                          yaxis=dict(gridcolor='#EEF1F8', tickfont=dict(size=11, color='#64748B'), rangemode='tozero'))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


def quick_actions(config, active):
    with st.container(border=True):
        st.html(card_title('zap', '#4F46E5', '#EEF2FF', 'Quick actions', 'Common tasks to organize your screenshots.'))
        a, b = st.columns(2)
        with a.container(key='qa_scan'):
            if st.button('Scan old screenshots', key='btn_scan', icon=':material/search:', width='stretch', disabled=config is None):
                run_action('scan', config)
        with b.container(key='qa_folder'):
            if st.button('Open destination folder', key='btn_folder', icon=':material/folder_open:', width='stretch', disabled=config is None):
                run_action('folder', config)
        c, d = st.columns(2)
        with c.container(key='qa_start'):
            if st.button('Start monitor', key='btn_start', icon=':material/play_circle:', width='stretch', disabled=active or config is None):
                run_action('start', config)
        with d.container(key='qa_stop'):
            if st.button('Stop monitor', key='btn_stop', icon=':material/stop_circle:', width='stretch', disabled=not active):
                run_action('stop', config)


def live_preview(store, active):
    with st.container(border=True):
        badge = '<span class="live">● Live</span>' if active else '<span class="live off">○ Idle</span>'
        st.html(card_title('eye', '#4F46E5', '#EEF2FF', 'Live preview', 'The latest screenshot and what OCR read from it.', badge))
        rows = data.records(store, limit=1)
        if not rows:
            st.caption('Nothing processed yet.')
            return
        record = rows[0]
        image = data.preview(record.destination_path, (900, 600))
        if image is not None:
            st.image(image, width='stretch')
        else:
            st.html('<div class="missing">Preview unavailable</div>')
        text = escape((record.ocr_text or 'No readable text recorded.').strip()[:260])
        bg, fg = colors_for(record.category)
        st.html(f'<div class="fld">Extracted text (OCR)</div><pre class="ocr">{text}</pre>'
                f'<div class="fld">Proposed title</div><div class="box">{escape(record.title or "Neutral fallback")}</div>'
                f'<div class="fld">Category</div><div>{pill(record.category)}</div>'
                f'<div class="fld">Final filename</div><div class="box">{escape(record.new_name or record.original_name)}</div>')


def overview(store, config, automation, ready):
    flash_toast()
    active = automation.get('active', False)
    dashboard_header(ready, active)
    st.space('small')
    values = kpi_row(store, automation, ready)
    st.space('small')
    main, side = st.columns([1.9, 1], gap='medium')
    with main:
        recent_activity(store)
        left, right = st.columns([1, 1.25], gap='medium')
        with left:
            categories_card(values)
        with right:
            trend_card(store)
    with side:
        quick_actions(config, active)
        live_preview(store, active)
    if values['errors']:
        st.caption(f'{values["errors"]} processing error(s) recorded. Open Live Monitor for diagnostics.')


# ---------------------------------------------------------------- other pages (unchanged behaviour)
def inspect_record(record, show_image=True):
    if show_image:
        image = data.preview(record.destination_path, (1800, 1400))
        if image is None:
            st.info('Preview unavailable. The file may have moved or is no longer readable; its history is preserved.')
        else:
            st.image(image, width='stretch')
    st.text(f'Original filename: {record.original_name}\nGenerated filename: {record.new_name or "—"}\nTitle: {record.title or "Neutral fallback"}\nCategory: {record.category or "Uncategorized"}\nProcessed: {record.processed_at}\nStatus: {record.status}\nDestination: {record.destination_path or "Not recorded"}')
    if st.checkbox('Reveal extracted text', key=f'ocr_{record.id}'):
        st.text_area('Full OCR text', record.ocr_text or 'No readable text recorded.', height=240, disabled=True, key=f'text_{record.id}')


def category_filter(settings, key):
    choice = st.selectbox('Category', ['All categories', *settings.categories, settings.uncategorized_name], key=key)
    return None if choice == 'All categories' else choice


def gallery(store, settings):
    header('Screenshot Gallery', 'A visual library of the moments you saved.')
    a, b = st.columns([3, 1])
    with a:
        query = st.text_input('Find a screenshot', placeholder='Search titles, filenames or extracted text…')
    with b:
        category = category_filter(settings, 'gallery_category')
    limit = st.select_slider('Recent result limit', [12, 24, 60, 120], value=24)
    items = data.records(store, query, category, limit)
    st.caption(f'{len(items)} result(s) · newest first · up to {limit} matches')
    if not items:
        st.info('No screenshots match yet. Try another search or take a new screenshot with automation active.')
        return
    columns = st.columns(3)
    for i, record in enumerate(items):
        with columns[i % 3], st.container(border=True):
            image = data.preview(record.destination_path, (600, 360))
            if image is None:
                st.html('<div class="missing">Preview unavailable<br><small>History is still available below</small></div>')
            else:
                # A consistent canvas keeps the cards aligned without cropping content.
                from PIL import ImageOps
                canvas = ImageOps.pad(image, (600, 360), color='#F6F7FC')
                st.image(canvas, width='stretch')
            st.text(record.new_name or record.original_name)
            st.html(pill(record.category) + f'<span style="margin-left:8px;color:#64748B;font-size:12px">{record.status.title()}</span>')
            st.caption(data.relative_time(record.processed_at))
            if st.button('View screenshot', key=f'view_{record.id}', width='stretch'):
                show_record(record)


@st.dialog('Screenshot details', width='large')
def show_record(record):
    inspect_record(record)


@st.fragment(run_every=5)
def live_panel(store, config):
    if 'control_feedback' in st.session_state:
        ok, message = st.session_state.pop('control_feedback')
        (st.success if ok else st.error)(message)
    automation = status(PROJECT_ROOT / 'runtime')
    active = automation.get('active', False)
    cols = st.columns(3)
    cols[0].metric('Service', automation.get('state', 'stopped').title())
    cols[1].metric('Process ID', str(automation.get('pid')) if active and automation.get('pid') else '—')
    cols[2].metric('Operating mode', automation.get('mode', 'Unknown').title() if active else 'Copy on next start')
    st.caption(f'Lock verified: {"active" if active else "inactive"} · refreshed {datetime.now():%H:%M:%S} · updates every 5 seconds')
    if active:
        st.success('Automation is independent of this dashboard. Closing the browser or stopping Streamlit leaves it running.')
    else:
        st.info('Automation is inactive. Start the service to organize new screenshots automatically.')
    if automation.get('error'):
        st.error(str(automation['error']))
    with st.container(border=True):
        st.text(f'Source: {automation.get("source") if active else (config.source if config else "Not configured")}\nDestination: {automation.get("destination") if active else (config.destination if config else "Not configured")}')
        start, stop = st.columns(2)
        action = None
        if start.button('Start automation', disabled=active or config is None, type='primary'):
            action = 'start'
        if stop.button('Stop automation', disabled=not active, help='Finish the current item and stop gracefully. Originals are retained.'):
            action = 'stop'
        if action:
            try:
                with st.spinner(f'{action.title()}ing background automation…'):
                    ok, message = data.control(PROJECT_ROOT, action)
                st.session_state.control_feedback = (ok, message)
                st.rerun()
            except (OSError, subprocess.TimeoutExpired) as exc:
                st.warning(f'Could not confirm completion: {exc}. Refresh status before retrying.')
    st.subheader('Latest processing activity')
    recent = data.records(store, limit=8)
    if recent:
        table(recent)
    else:
        st.caption('No processing activity recorded yet.')
    with st.expander('Recent warnings and errors · may contain private paths'):
        if st.checkbox('Reveal local diagnostic messages'):
            messages = data.warnings(PROJECT_ROOT)
            st.text('\n'.join(messages) if messages else 'No warnings or errors in the recent log tail.')


def history(store, settings):
    header('History & Search', 'Find the right screenshot by what it says, not just what it is called.')
    a, b = st.columns([3, 1])
    with a:
        query = st.text_input('Search OCR text, titles and filenames', placeholder='All search words must match…', key='history_query')
    with b:
        category = category_filter(settings, 'history_category')
    items = data.records(store, query, category, 200)
    st.caption(f'{len(items)} result(s) · newest 200 matches · recorded values are never reclassified here')
    if not items:
        st.info('No history matches. Try fewer words or a different category.')
        return
    table(items)
    choice = st.selectbox('Inspect history record', range(len(items)), format_func=lambda i: f'#{items[i].id} · {items[i].new_name or items[i].original_name}')
    record = items[choice]
    with st.expander('Preview and saved details', expanded=True):
        if st.checkbox('Show screenshot preview', key='history_preview'):
            image = data.preview(record.destination_path)
            if image is not None:
                st.image(image, width='stretch')
            else:
                st.info('Image preview unavailable. The saved record remains accessible.')
        if st.checkbox('Show OCR excerpt'):
            st.text(make_snippet(record.ocr_text, query.split(), width=220))
        inspect_record(record, show_image=False)


def settings_page(settings, config, ready, message):
    header('Settings', 'Your local workspace, with automation kept safely in sync.')
    with st.container(border=True):
        st.subheader('Workspace configuration')
        st.text(f'Source folder: {config.source if config else "Not configured"}\nDestination folder: {config.destination if config else "Not configured"}\nHistory database: {config.database if config else settings.database_path}')
        st.caption('Read-only here. Folder changes require stopping the service and using background.py configure, then starting it again.')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader('OCR & automation')
        (st.success if ready else st.warning)(message)
        st.write('Independent background service · copy mode')
        st.caption('No external AI services. Original screenshots are retained.')
        if st.button('Check Windows startup status'):
            try:
                st.text(data.startup_status(PROJECT_ROOT))
            except (OSError, subprocess.TimeoutExpired):
                st.warning('Startup status is unavailable. Verify it locally with the PowerShell script.')
    with right, st.container(border=True):
        st.subheader('Content categories')
        st.write(' · '.join([*settings.categories, settings.uncategorized_name]))
        st.caption(f'Minimum evidence score: {settings.category_min_score} · Minimum lead: {settings.category_min_margin}')
        with st.expander('Review configured keyword weights'):
            st.json(settings.categories)
    st.info('Keep the dashboard on localhost. Screenshot previews and revealed OCR can contain personal information.')


def sidebar(config, automation, ready):
    with st.sidebar:
        st.html(f'<div class="brand-row"><div class="logo">{icon("image", "#fff", 26)}</div>'
                '<div class="brand">Smart<br>Screenshot<br>Organizer</div></div>')
        page = st.session_state.get('page', 'Dashboard')
        for name in PAGES:
            # The container key becomes a CSS class, so the active item can be styled as a pill.
            with st.container(key=f'{"navon" if name == page else "navoff"}_{PAGE_ICONS[name]}'):
                st.button(name, key=f'nav_{name}', icon=f':material/{PAGE_ICONS[name]}:', width='stretch',
                          on_click=lambda n=name: st.session_state.update(page=n))
        st.divider()
        used = cached_folder_size(str(config.destination)) if config else 0
        budget = STORAGE_BUDGET_GB * 1024 ** 3
        pct = min(used / budget * 100, 100)
        shown = f'{pct:.1f}%' if pct < 10 else f'{pct:.0f}%'      # "0.1%" instead of a misleading "0%"
        width = max(pct, 3) if used else 0                         # keep a small amount visible
        st.html(f'<div class="storage"><div class="t">Storage used by screenshots</div>'
                f'<div class="bar"><span style="width:{width:.1f}%"></span></div>'
                f'<div class="m"><span>{data.format_bytes(used)} of {STORAGE_BUDGET_GB} GB</span><span>{shown}</span></div></div>')
        st.caption('● Automation active' if automation.get('active') else '○ Automation inactive')
        st.caption('OCR ready' if ready else 'OCR unavailable')
        st.caption('Copy mode · originals retained')
        st.button('Refresh dashboard', width='stretch')
        st.html(f'<div class="promo">{icon("shield", "#C7D2FE", 24)}<div>Private by design.<br>Everything is processed on this computer.</div></div>')
    return page


def main():
    st.set_page_config(page_title='Smart Screenshot Organizer', page_icon=':material/photo_library:', layout='wide')
    st.html(STYLE)
    settings = Settings()
    config, error = data.configuration(PROJECT_ROOT)
    store = MetadataStore(config.database if config else settings.database_path)
    automation = status(PROJECT_ROOT / 'runtime')
    ready, message = ocr_status()
    page = sidebar(config, automation, ready)
    if error:
        st.warning(error)
    try:
        if page == 'Dashboard':
            overview(store, config, automation, ready)
        elif page == 'Screenshot Gallery':
            gallery(store, settings)
        elif page == 'Live Monitor':
            header('Live Monitor', 'A real-time view of the service working quietly in the background.')
            live_panel(store, config)
        elif page == 'History & Search':
            history(store, settings)
        else:
            settings_page(settings, config, ready, message)
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.warning(f'Data is temporarily unavailable: {exc}. Refresh to try again.')


if __name__ == '__main__':
    main()