"""Compact brokerage-style layout. No external font/network dependency."""
from __future__ import annotations
import html


def css(dark=False):
    colors=('#0c1421','#121e30','#22324a','#e6edf7','#95a5bd','#1ab6a0') if dark else ('#f2f5f9','#ffffff','#dce3ec','#14253d','#64758b','#087e76')
    bg,panel,line,text,muted,accent=colors
    return f'''<style>
    :root{{--desk-bg:{bg};--desk-panel:{panel};--desk-line:{line};--desk-text:{text};--desk-muted:{muted};--desk-accent:{accent}}}
    .stApp,[data-testid="stAppViewContainer"]{{background:var(--desk-bg);color:var(--desk-text)}}
    .block-container{{max-width:1240px;padding-top:2.2rem;padding-bottom:3rem}}
    html,body,button,input,select,.stMarkdown{{font-family:Inter,"PingFang TC","Noto Sans TC","Microsoft JhengHei","Heiti TC",sans-serif}}
    [data-testid="stHeader"]{{height:2rem;background:var(--desk-bg)}}
    [data-testid="stToolbar"]{{display:none}}
    button[data-testid="stBaseButton-segmentedControlActive"]{{color:var(--desk-accent)!important;background:var(--desk-panel)!important;border-color:var(--desk-accent)!important}}
    h1,h2,h3{{color:var(--desk-text);letter-spacing:-.025em}} h3{{font-size:1.12rem!important;margin-top:.35rem}}
    .desk-top{{display:flex;justify-content:space-between;align-items:center;padding:14px 2px 18px;border-bottom:2px solid #182f4d;gap:18px}}
    .desk-wordmark{{font-size:20px;font-weight:800;letter-spacing:1.3px;color:var(--desk-text)}}
    .desk-wordmark span{{color:var(--desk-accent)}} .desk-product{{font-size:12px;color:var(--desk-muted);margin-top:3px;letter-spacing:.08em}}
    .desk-meta{{font-size:12px;text-align:right;line-height:1.8;color:var(--desk-muted)}}
    .desk-strip{{display:flex;gap:14px;flex-wrap:wrap;background:var(--desk-panel);border:1px solid var(--desk-line);padding:11px 15px;margin:12px 0;border-radius:8px;font-size:12px;color:var(--desk-muted);box-shadow:0 5px 18px rgba(15,35,58,.035)}}
    .desk-strip b{{color:var(--desk-text);font-variant-numeric:tabular-nums}}
    .desk-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:10px 0 18px}}
    .desk-stat{{background:var(--desk-panel);border:1px solid var(--desk-line);border-top:3px solid var(--desk-accent);padding:15px 18px;border-radius:8px;box-shadow:0 7px 22px rgba(15,35,58,.045)}}
    .desk-stat .label{{font-size:12px;color:var(--desk-muted)}}.desk-stat .value{{font-size:26px;font-weight:750;color:var(--desk-text);margin:4px 0;font-variant-numeric:tabular-nums}}
    .desk-stat .hint{{font-size:11px;color:var(--desk-muted)}}
    .desk-note{{font-size:12px;line-height:1.75;color:var(--desk-muted);margin:6px 0 12px}}
    .desk-title{{font-size:23px;font-weight:750;letter-spacing:-.04em;color:var(--desk-text);margin:15px 0 4px}}
    .desk-sub{{font-size:13px;color:var(--desk-muted);margin-bottom:15px;line-height:1.6}}
    .desk-stock{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-top:1px solid var(--desk-line);padding:20px 0 12px;margin-top:10px}}
    .desk-stock .code{{font-size:25px;font-weight:800;color:var(--desk-accent);font-variant-numeric:tabular-nums}}
    .desk-stock .name{{font-size:24px;font-weight:700;color:var(--desk-text)}}
    .desk-tag{{font-size:11px;padding:4px 8px;border:1px solid var(--desk-line);color:var(--desk-muted);border-radius:4px;background:var(--desk-panel)}}
    .desk-verdict{{border-left:4px solid var(--desk-accent);padding:12px 16px;background:var(--desk-panel);margin-bottom:12px;font-size:14px;color:var(--desk-text);line-height:1.7}}
    .desk-global{{display:flex;justify-content:space-between;gap:14px;align-items:center;margin:10px 0 16px;padding:12px 15px;border:1px solid var(--desk-line);border-left:4px solid #718399;border-radius:7px;background:var(--desk-panel);font-size:12px;box-shadow:0 6px 20px rgba(15,35,58,.035)}}
    .desk-global b{{font-size:13px;color:var(--desk-text);white-space:nowrap}}.desk-global span{{color:var(--desk-muted);text-align:right}}
    .desk-global.positive{{border-left-color:#c83a40}}.desk-global.negative{{border-left-color:#148759}}.desk-global.neutral{{border-left-color:var(--desk-accent)}}
    [data-testid="stDataFrame"]{{border:1px solid var(--desk-line);border-radius:5px;overflow:hidden}}
    [data-testid="stExpander"]{{background:var(--desk-panel);border:1px solid var(--desk-line);border-radius:5px}}
    [data-testid="stMetric"]{{background:var(--desk-panel);border:1px solid var(--desk-line);border-radius:5px;padding:12px}}
    [data-testid="stMetricValue"]{{font-size:24px;font-variant-numeric:tabular-nums}}
    .stButton button{{border-radius:5px;font-weight:600}} [data-testid="stSidebar"]{{background:var(--desk-panel)}}
    div[role="radiogroup"]{{gap:0!important;border-bottom:1px solid var(--desk-line);padding:7px 0 10px;background:var(--desk-bg)}}
    div[role="radiogroup"] label{{padding:4px 12px!important;font-size:13px!important}}
    .desk-demo{{background:#fff7df;color:#78531b;border:1px solid #edcf80;padding:8px 13px;font-size:12px;margin:8px 0;border-radius:4px}}
    .desk-footer{{border-top:1px solid var(--desk-line);margin-top:22px;padding-top:12px;color:var(--desk-muted);font-size:11px;line-height:1.8}}
    .st-key-desk_section{{width:100%!important}}
    .st-key-desk_section div[role="radiogroup"]{{display:flex;width:100%!important;flex-wrap:nowrap!important;gap:10px!important;border:0;padding:18px 0 12px}}
    .st-key-desk_section div[role="radiogroup"] label{{flex:1 1 50%!important;min-width:0;padding:15px 20px!important;border:1px solid var(--desk-line);border-radius:12px;background:var(--desk-panel)}}
    .st-key-desk_section div[role="radiogroup"] label:has(input:checked){{border-color:var(--desk-accent);background:color-mix(in srgb,var(--desk-accent) 8%,var(--desk-panel))}}
    .st-key-desk_section div[role="radiogroup"] label p{{font-size:16px;font-weight:700}}
    .focus-eyebrow{{font-size:10px;letter-spacing:2px;color:var(--desk-accent);margin-top:26px}}
    .lab-hero{{background:linear-gradient(115deg,#142e48,#1a4a58);padding:18px 24px;border-radius:16px;color:#fff;margin:16px 0}}
    .lab-hero span{{font-size:10px;letter-spacing:2px;color:#83d1c4}}.lab-hero h1{{font-size:26px;color:white;margin:6px 0}}
    .lab-hero p{{color:#c6d8e2;font-size:13px;margin:0;line-height:1.75}}
    .focus-eyebrow+.desk-title{{font-size:32px;line-height:1.3;margin-top:8px;margin-bottom:10px}}
    .focus-pick{{min-width:0;padding:5px 1px 12px;line-height:1.6}}
    .focus-pick-top{{display:flex;align-items:center;justify-content:space-between;gap:4px}}
    .focus-rank{{font-size:10px;letter-spacing:.5px;color:var(--desk-muted)}}
    .focus-status{{font-size:10px;padding:3px 7px;border-radius:30px;background:var(--desk-bg);color:var(--desk-muted)}}
    .focus-status.ready{{color:var(--desk-accent);background:#e5f5ef}}
    .focus-name{{display:flex;gap:10px;align-items:baseline;margin:18px 0 2px;flex-wrap:wrap}}
    .focus-name b{{font-size:25px;letter-spacing:-.6px}}.focus-name span{{font-size:13px;color:var(--desk-muted)}}
    .focus-sector{{font-size:11px;color:var(--desk-muted);min-height:18px}}
    .focus-reason-label{{font-size:11px;color:var(--desk-accent);font-weight:700;margin-top:20px}}
    .focus-reasons{{padding-left:17px;font-size:13px;line-height:1.8;margin:8px 0 17px;min-height:46px}}
    .focus-levels{{display:grid;grid-template-columns:1fr 1.5fr 1fr;gap:6px;border-top:1px solid var(--desk-line);border-bottom:1px solid var(--desk-line);padding:14px 0}}
    .focus-levels span,.focus-levels b{{display:block}}.focus-levels span{{font-size:10px;color:var(--desk-muted);margin-bottom:4px}}
    .focus-levels b{{font-size:16px;font-variant-numeric:tabular-nums;letter-spacing:-.35px}}
    .focus-risk{{font-size:11px;color:var(--desk-muted);line-height:1.7;margin-top:13px;min-height:38px}}
    .focus-risk b{{color:#a87530;font-weight:600}}.focus-score{{font-size:10px;color:var(--desk-muted);margin-top:10px}}
    [data-testid="stVerticalBlockBorderWrapper"],[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .focus-pick){{border-radius:14px!important;background:var(--desk-panel);box-shadow:0 8px 26px rgba(15,35,58,.025)}}
    .focus-guide{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;border:1px solid var(--desk-line);padding:22px 24px;border-radius:14px;margin:24px 0 10px;background:var(--desk-panel)}}
    .focus-guide span{{display:block;color:var(--desk-accent);font-size:11px;letter-spacing:1px;margin-bottom:6px}}
    .focus-guide b{{font-size:14px}}.focus-guide p{{font-size:12px;color:var(--desk-muted);line-height:1.75;margin:7px 0 0}}
    .focus-conclusion{{background:var(--desk-panel);border:1px solid var(--desk-line);border-left:4px solid var(--desk-accent);border-radius:14px;padding:24px 28px;margin:24px 0}}
    .focus-conclusion span{{font-size:11px;color:var(--desk-accent)}}.focus-conclusion h2{{font-size:25px;margin:9px 0}}
    .focus-conclusion p{{font-size:13px;color:var(--desk-muted);margin:0;line-height:1.75}}
    .focus-empty{{border:1px dashed var(--desk-line);border-radius:12px;padding:24px;margin:10px 0;background:var(--desk-panel)}}
    .focus-empty p{{font-size:13px;line-height:1.8;color:var(--desk-muted);margin:8px 0 0}}
    @media(max-width:720px){{
      .block-container{{padding:1.2rem .65rem 5rem}}
      .desk-top{{align-items:flex-start;padding-top:7px}}.desk-product{{font-size:10px}}.desk-meta{{max-width:132px;font-size:9px;line-height:1.6}}.desk-wordmark{{font-size:16px}}
      .desk-strip{{gap:7px;padding:9px 10px;overflow-x:auto;flex-wrap:nowrap}}.desk-strip span{{white-space:nowrap}}
      .desk-grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}.desk-stat{{padding:10px 11px}}.desk-stat .value{{font-size:20px}}.desk-title{{font-size:21px}}
      .desk-global{{display:block;padding:10px 12px}}.desk-global span{{display:block;text-align:left;margin-top:4px;line-height:1.55}}
      .st-key-desk_section div[role="radiogroup"]{{position:relative;top:0;gap:7px!important;padding:13px 0}}
      .st-key-desk_section div[role="radiogroup"] label{{padding:10px 8px!important;justify-content:center;min-width:0}}
      .st-key-desk_section div[role="radiogroup"] label p{{font-size:13px}}
      div[role="radiogroup"] label{{padding:7px 9px!important;white-space:nowrap;font-size:12px!important}}
      [data-testid="stDataFrame"]{{font-size:11px}}
      .focus-eyebrow{{margin-top:18px}}.focus-eyebrow+.desk-title{{font-size:27px}}
      .focus-name b{{font-size:25px}}.focus-levels b{{font-size:18px}}
      .focus-guide{{grid-template-columns:1fr;gap:17px;padding:20px}}
      .focus-guide span{{float:left;margin:1px 14px 30px 0}}.focus-guide p{{margin-top:4px}}
      .focus-conclusion{{padding:20px}}.focus-conclusion h2{{font-size:22px}}
      .st-key-focus_controls [data-testid="stHorizontalBlock"]{{flex-direction:row!important;gap:12px!important}}
      .st-key-focus_controls [data-testid="stColumn"]{{min-width:0!important;flex:1 1 calc(50% - 6px)!important;width:calc(50% - 6px)!important}}
      .st-key-focus_controls button{{padding-left:8px!important;padding-right:8px!important;font-size:12px!important;min-width:0!important}}
      .st-key-focus_controls [data-testid="stVerticalBlock"]{{gap:5px!important}}
    }}
    </style>'''


def esc(x):return html.escape(str(x) if x is not None else '')


def readable_reason(value):
    out=str(value or '')
    for old,new in {'相對0050強度(120日)':'近半年相對走勢較強','中期動能(120日扣近20日)':'中期上漲動能較穩',
        '外資5日買超(占量)偏低':'外資近期買盤偏弱','外資/投信連續買超天數偏低':'法人連續買盤較弱',
        '均線多頭排列':'均線結構偏多','接近一年新高':'股價接近一年高點'}.items():out=out.replace(old,new)
    return out


def stats(items):
    return '<div class="desk-grid">'+''.join('<div class="desk-stat"><div class="label">'+esc(a)+'</div><div class="value">'+esc(b)+'</div><div class="hint">'+esc(c)+'</div></div>' for a,b,c in items)+'</div>'


def title(main,sub=''):
    return '<div class="desk-title">'+esc(main)+'</div><div class="desk-sub">'+esc(sub)+'</div>'
