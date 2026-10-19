"""Global stylesheet for the dashboard. Injected once from app.main() via st.html."""

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* custom (non-Streamlit) elements use Inter; Streamlit's own widgets keep their font so icons stay intact */
.kpi,.ct,.card-title,.card-sub,.dash-title,.dash-sub,table.act,.legend,.fld,.box,pre.ocr,.storage,.brand,.promo,.status-pill,.pill,.live
    {font-family:'Inter','Source Sans Pro',system-ui,sans-serif;}

/* ---------- page canvas ---------- */
.stApp {background:#F4F6FC;}
[data-testid="stMain"] .block-container {padding-top:4.5rem;max-width:1500px;}
[data-testid="stHeader"] {background:transparent;}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {background:linear-gradient(185deg,#1B2160 0%,#243088 55%,#2B3A9A 100%);}
[data-testid="stSidebar"] :is(p,span,label,.stCaption) {color:#DDE3FF;}
.brand-row {display:flex;align-items:center;gap:14px;margin:4px 0 26px}
.logo {width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#6366F1,#8B5CF6);
    display:flex;align-items:center;justify-content:center;flex:none;box-shadow:0 8px 20px rgba(99,102,241,.45)}
.brand {font-size:18px;font-weight:750;line-height:1.2;color:#fff;margin:0}

/* nav: every page is a button; the container key tells us which one is active */
[data-testid="stSidebar"] [class*="st-key-nav"] button {
    justify-content:flex-start;gap:12px;border:0;border-radius:14px;min-height:50px;padding:0 16px;box-shadow:none;transition:background .15s}
[data-testid="stSidebar"] [class*="st-key-nav"] button > div {justify-content:flex-start;}
[data-testid="stSidebar"] [class*="st-key-nav"] button p {font-size:15px;font-weight:600;}
[data-testid="stSidebar"] [class*="st-key-nav"] button [data-testid="stIconMaterial"] {font-size:24px;}
[data-testid="stSidebar"] [class*="st-key-navoff_"] button {background:transparent;color:#C9D1FF;}
[data-testid="stSidebar"] [class*="st-key-navoff_"] button:hover {background:rgba(255,255,255,.09);color:#fff;}
[data-testid="stSidebar"] [class*="st-key-navon_"] button {background:rgba(255,255,255,.20);color:#fff;}
[data-testid="stSidebar"] [class*="st-key-nav"] button :is(p,span) {color:inherit;}

/* storage meter + privacy card */
.storage {background:rgba(255,255,255,.08);border-radius:14px;padding:14px 16px;margin:6px 0 14px}
.storage .t {font-size:13px;font-weight:650;color:#fff}
.storage .bar {height:7px;border-radius:99px;background:rgba(255,255,255,.18);margin:10px 0 8px;overflow:hidden}
.storage .bar span {display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#6366F1,#A78BFA)}
.storage .m {font-size:12px;color:#C7CEFF;display:flex;justify-content:space-between}
.promo {display:flex;gap:12px;align-items:center;padding:16px;border-radius:16px;margin-top:14px;
    background:linear-gradient(135deg,#4338CA 0%,#2A2F9E 60%,#1B2160 100%);color:#E0E7FF;font-size:13px;line-height:1.45;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}

/* ---------- cards (every bordered container) ---------- */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
    background:#fff;border:1px solid #E8ECF5;border-radius:18px;box-shadow:0 6px 24px rgba(30,41,120,.06);}
.ct {display:flex;align-items:center;gap:12px;margin-bottom:10px}
.ct-ico {width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex:none}
.ct-right {margin-left:auto}
.card-title {font-size:17px;font-weight:700;color:#17153B;line-height:1.25}
.card-sub {font-size:13px;color:#64748B;margin:1px 0 0}

/* ---------- page header ---------- */
.page-heading {margin:0 0 26px;}
.eyebrow {color:#5145CD;font-size:11px;font-weight:750;letter-spacing:2px;margin-bottom:10px}
.page-heading h1 {color:#17153B;font-size:30px;letter-spacing:-1px;margin:0 0 8px;font-weight:750}
.page-heading p {color:#64748B;font-size:15px;margin:0}
.dash-title {display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.dash-title h1 {color:#17153B;font-size:34px;letter-spacing:-1.2px;margin:0;font-weight:800}
.dash-sub {color:#64748B;font-size:14px;margin:4px 0 0}
.status-pill {display:inline-flex;align-items:center;gap:7px;background:#E7F8EE;color:#15803D;
    font-size:12px;font-weight:650;border-radius:99px;padding:5px 12px}
.status-pill.off {background:#FEF3C7;color:#B45309}
.status-pill i {width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block}
[data-testid="stMain"] [data-testid="stTextInput"] input {border-radius:14px;}

/* ---------- KPI cards ---------- */
.kpi {background:#fff;border:1px solid #E8ECF5;border-radius:18px;padding:18px 20px;
    box-shadow:0 6px 24px rgba(30,41,120,.06);min-height:132px;display:grid;
    grid-template-columns:auto 1fr auto;column-gap:14px;align-items:center}
.kpi-icon {width:54px;height:54px;border-radius:15px;display:flex;align-items:center;justify-content:center}
.kpi-label {font-size:13px;color:#64748B;font-weight:600}
.kpi-value {font-size:32px;font-weight:800;color:#17153B;line-height:1.15;letter-spacing:-1px}
.kpi-spark {align-self:end;line-height:0}
.kpi-sub {grid-column:1 / -1;font-size:12px;margin-top:10px;font-weight:600}
.kpi-sub.up {color:#16A34A}.kpi-sub.down {color:#DC2626}.kpi-sub.flat {color:#64748B}

/* ---------- activity table ---------- */
.act-wrap {overflow-x:auto;border-radius:12px}
table.act {width:100%;border-collapse:collapse;font-size:13px;min-width:680px}
table.act th {text-align:left;color:#64748B;font-weight:600;font-size:12px;background:#F8FAFD;padding:10px 12px}
table.act td {padding:10px 12px;border-top:1px solid #EEF1F8;color:#334155;vertical-align:middle}
table.act tr:hover td {background:#FAFBFF}
table.act td.new {color:#17153B;font-weight:600;word-break:break-word;min-width:170px}
table.act td.orig {color:#64748B;font-size:12.5px;min-width:150px}
table.act td.nw {white-space:nowrap}
table.act td.kebab {color:#94A3B8;font-weight:800;text-align:right;width:24px}
table.act img {width:64px;height:44px;object-fit:cover;border-radius:8px;display:block;border:1px solid #E8ECF5}
.thumb-missing {width:64px;height:44px;border-radius:8px;background:#EEF1F8}
.pill {display:inline-block;padding:3px 12px;border-radius:99px;font-size:12px;font-weight:650}
.dot {display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px}

/* "View all" outlined button */
.st-key-view_all_wrap button {background:#fff;border:1px solid #DDE3F5;color:#4338CA;border-radius:10px;min-height:38px}
.st-key-view_all_wrap button:hover {background:#EEF2FF;border-color:#C7D2FE;color:#4338CA}

/* ---------- legend (donut) ---------- */
.legend {font-size:13px;color:#334155}
.legend div {display:flex;align-items:center;gap:8px;padding:4px 0}
.legend .n {flex:1}.legend .p {color:#64748B;width:42px;text-align:right}.legend .c {color:#17153B;font-weight:650;width:48px;text-align:right}

/* 7 / 30 day toggle */
[data-testid="stSegmentedControl"] button[data-testid="stBaseButton-segmented_controlActive"] {background:#4338CA;color:#fff;border-color:#4338CA;}
[data-testid="stSegmentedControl"] button[data-testid="stBaseButton-segmented_controlActive"] :is(p,span) {color:#fff;}

/* ---------- live preview ---------- */
.live {font-size:12px;font-weight:650;color:#15803D;background:#E7F8EE;border-radius:99px;padding:4px 11px;white-space:nowrap}
.live.off {color:#B45309;background:#FEF3C7}
.fld {font-size:12px;color:#64748B;font-weight:600;margin:12px 0 5px}
.box {background:#F6F7FC;border:1px solid #E8ECF5;border-radius:10px;padding:9px 12px;font-size:13px;color:#17153B;word-break:break-word}
pre.ocr {background:#F6F7FC;border:1px solid #E8ECF5;border-radius:10px;padding:10px 12px;font-size:12px;
    color:#17153B;white-space:pre-wrap;margin:0;max-height:130px;overflow:auto}

/* ---------- quick actions: coloured, with a two-line label (title + helper text) ---------- */
[class*="st-key-qa_"] button {border:0;min-height:76px;border-radius:14px;justify-content:flex-start;text-align:left;padding:10px 16px;gap:12px;
    transition:transform .12s, box-shadow .12s}
[class*="st-key-qa_"] button > div {justify-content:flex-start;}
[class*="st-key-qa_"] button [data-testid="stIconMaterial"] {font-size:26px;}
[class*="st-key-qa_"] button p {font-weight:700;font-size:14px;line-height:1.3;text-align:left;white-space:normal;color:inherit}
[class*="st-key-qa_"] button p::after {display:block;font-size:11.5px;font-weight:450;opacity:.8;margin-top:2px}
[class*="st-key-qa_"] button:not(:disabled):hover {transform:translateY(-1px);box-shadow:0 8px 18px rgba(49,46,129,.18)}
.st-key-qa_scan button {background:#312E81;color:#fff;}
.st-key-qa_scan button p::after {content:"Find and organize existing files";}
.st-key-qa_folder button {background:#E4E9FF;color:#312E81;}
.st-key-qa_folder button p::after {content:"View organized screenshots";}
.st-key-qa_start button {background:#DDF6E6;color:#15803D;}
.st-key-qa_start button p::after {content:"Watch for new screenshots";}
.st-key-qa_stop button {background:#FEE2E2;color:#B91C1C;}
.st-key-qa_stop button p::after {content:"Pause automatic processing";}
[class*="st-key-qa_"] button:disabled {opacity:.5;}
.st-key-qa_scan button :is(p,span), .st-key-qa_folder button :is(p,span), .st-key-qa_start button :is(p,span), .st-key-qa_stop button :is(p,span) {color:inherit;}

/* ---------- misc ---------- */
.missing {height:200px;display:flex;flex-direction:column;justify-content:center;text-align:center;color:#64748B;background:#F6F7FC;border-radius:12px}
@media(max-width:700px){.page-heading h1,.dash-title h1{font-size:25px}.kpi-value{font-size:26px}}
</style>
"""