#!/usr/bin/env python3
"""report_generator_v3.py

Version v3 — corrections demandées par l'utilisateur :
1) Détail des camemberts : quand un même "spent_subtype" existe en both 'asso' et 'perso',
   on propose 4 modes: combined (fusion asso+perso), only_asso, only_perso, two (deux camemberts).
   Le clic sur une ligne affiche toutes les options, même si l'utilisateur a cliqué sur la ligne
   qui appartient à une des deux catégories.

2) Remboursements : repositionnement du panneau de filtres juste au-dessus des résultats,
   algorithmie exactement comme demandée :
     - On sélectionne des éléments en ANTE (par type/subtype/name) ; leur somme totale = TOTAL_ANTE
     - On prélève sur SUM_GAIN la partie couverte des ANTE : COVERED_ANTE = min(SUM_GAIN, TOTAL_ANTE)
       (si insuffisant, on répartit COVERED_ANTE *proportionnellement* aux contributions ANTE par membre)
     - On calcule REMAINING = SUM_GAIN - COVERED_ANTE
     - REMAINING est réparti entre membres selon les poids (poids normalisés)
     - Pour chaque membre, on définit PART_AFTER_ANTE = REMAINING * weight(member)
     - Chaque membre a un total POST (les éléments non sélectionnés en ANTE) : POST_MEMBER
     - On déduit POST_MEMBER de PART_AFTER_ANTE -> FINAL = PART_AFTER_ANTE - POST_MEMBER

   Les colonnes affichées par membre (exactement comme demandé) :
    - total_ante_member
    - total_post_member
    - total_ante_plus_post_member
    - part_after_ante_split (ce qui lui est dévolu après avoir retranché ANTE du SUM_GAIN et splitté)
    - final_after_post (après avoir retranché ses POST de sa part)

3) Esthétique : couleurs pastel appliquées par colonne (très légères) et couleurs correspondantes
   plus saturées pour les camemberts (on dérive les versions claires en JS pour les fonds de colonne).

4) SUM_GAIN est importé via "from infos import SUM_GAIN" comme demandé — la page n'offre pas de
   contrôle pour changer SUM_GAIN.

Usage:
  - place expenses.csv next to the script or pass --in
  - create infos.py with SUM_GAIN = 1000.0 (par ex.)
  - run: python report_generator_v3.py --in expenses.csv --out report_v3.html

"""

# SUM_GAIN must come from infos as requested
try:
    from infos import SUM_GAIN
except Exception:
    SUM_GAIN = 0.0
    print("[Warning] infos.SUM_GAIN introuvable — SUM_GAIN = 0.0 utilisé (mettre infos.py avec SUM_GAIN value).")

import argparse
import json
import os
import re
import pandas as pd

# -------------------- helpers --------------------

def parse_amount(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip()
    if s == "":
        return 0.0
    s = s.replace('\u00A0', '').replace(' ', '')
    if s.count(',') == 1 and s.count('.') == 0:
        s = s.replace(',', '.')
    s2 = re.sub(r'[^0-9\.-]', '', s)
    try:
        return float(s2) if s2 not in ('', '-', '.') else 0.0
    except:
        return 0.0


def clean_member_name(name):
    if pd.isna(name):
        return ''
    s = str(name).strip()
    s = ' '.join(s.split())
    return s

# -------------------- load & clean --------------------

def load_and_clean(csv_path):
    df = pd.read_csv(csv_path, dtype=str)
    expected = ['spent_type', 'spent_subtype', 'spent_name', 'amount', 'member', 'is_bill', 'spent_id']
    for c in expected:
        if c not in df.columns:
            df[c] = None
    df['spent_type_clean'] = df['spent_type'].fillna('').astype(str).str.strip()
    df['spent_subtype_clean'] = df['spent_subtype'].fillna('').astype(str).str.strip()
    df['spent_name_clean'] = df['spent_name'].fillna('').astype(str).str.strip()
    df['member_clean'] = df['member'].apply(clean_member_name).fillna('').astype(str)
    df['amount_f'] = df['amount'].apply(parse_amount).astype(float)
    df['is_bill_clean'] = df['is_bill'].fillna('').astype(str).str.strip()
    df['spent_id'] = df['spent_id'].fillna('').astype(str)
    return df

# -------------------- aggregates --------------------

def compute_aggregates(df):
    members = sorted([m for m in df['member_clean'].unique() if str(m).strip() != ''])
    base_colors = [
        '#7fb3ff', '#ffd7a6', '#b6e3b6', '#ffb3b3', '#d6b3ff', '#d8b9ab', '#ffc7e6', '#e6e6e6'
    ]
    member_colors = {m: base_colors[i % len(base_colors)] for i, m in enumerate(members)}

    total_overall = float(df['amount_f'].sum())
    totals_by_type = df.groupby('spent_type_clean')['amount_f'].sum().to_dict()

    records = []
    for _, row in df.iterrows():
        records.append({
            'spent_type': row['spent_type_clean'],
            'spent_subtype': row['spent_subtype_clean'],
            'spent_name': row['spent_name_clean'],
            'amount': float(row['amount_f']),
            'member': row['member_clean'],
            'is_bill': row['is_bill_clean'],
            'spent_id': str(row.get('spent_id', ''))
        })

    subtypes_by_type = {}
    for t in df['spent_type_clean'].unique():
        subtypes_by_type[t] = sorted(df[df['spent_type_clean'] == t]['spent_subtype_clean'].unique().tolist())

    member_totals_overall = df.groupby('member_clean')['amount_f'].sum().to_dict()

    agg = {
        'members': members,
        'member_colors': member_colors,
        'total_overall': total_overall,
        'totals_by_type': {k: float(v) for k, v in totals_by_type.items()},
        'records': records,
        'subtypes_by_type': subtypes_by_type,
        'member_totals_overall': {k: float(v) for k, v in member_totals_overall.items()}
    }
    return agg

# -------------------- template HTML --------------------

HTML_TEMPLATE = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Rapport dépenses — v3</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
<style>
  body { font-family: Inter, Arial, sans-serif; margin:18px; background:#fbfcfe; color:#1b1b1b; }
  h1 { font-size:1.5rem; margin-bottom:6px; }
  .panel { background:white; padding:12px; border-radius:10px; box-shadow: 0 6px 18px rgba(20,20,40,0.04); margin-bottom:12px; }
  table { border-collapse:collapse; width:100%; }
  th, td { padding:8px 10px; border-bottom:1px solid #f0f2f6; text-align:right; }
  th { text-align:left; background:#f4f7ff; font-weight:700; }
  td.namecell { text-align:left; font-weight:600; }
  tr.subtotal { background:#fff8e6; font-weight:700; }
  tr.total { background:#e9f7ff; font-weight:800; }
  .member-swatch { display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:8px; vertical-align:middle; }
  .grid { display:grid; grid-template-columns: 1fr 420px; gap:12px; }
  .fullwidth { grid-column:1/-1; }
  .btn { padding:6px 10px; border-radius:8px; border:1px solid #d9e2ff; background:linear-gradient(#fff,#f7fbff); cursor:pointer; }
  .muted { color:#6b7280; font-size:0.9rem; }
  .tiny { font-size:0.85rem; color:#6b7280; }
  .clickable { cursor:pointer; }
</style>
</head>
<body>
  <h1>Visualisation & Remboursements — v3</h1>
  <div class="panel">
    <div style="display:flex; gap:12px; align-items:center;">
      <div>
        <strong>Granularité ANTE</strong>
        <label style="margin-left:8px"><input type="radio" name="ante_gran" value="type" checked> type</label>
        <label style="margin-left:6px"><input type="radio" name="ante_gran" value="subtype"> subtype</label>
        <label style="margin-left:6px"><input type="radio" name="ante_gran" value="name"> name</label>
      </div>
      <div style="margin-left:auto" class="tiny"> Somme des gains : <strong id="sum_gain_label">{{SUM_GAIN_LABEL}}</strong></div>
    </div>
    <div class="muted" style="margin-top:8px">Sélectionner ce qui est <strong>ANTE</strong> — ces montants sont déduits directement de la somme des gains (indépendamment du membre).</div>
  </div>

  <div class="panel">
    <div style="display:flex; gap:18px; align-items:flex-start;">
      <div style="min-width:320px">
        <div style="font-weight:700;margin-bottom:6px">Sélection ANTE</div>
        <div id="ante_choice_container" style="max-height:260px; overflow:auto; border:1px solid #eef2ff; padding:8px; border-radius:8px"></div>
      </div>

      <div style="flex:1">
        <div style="font-weight:700; margin-bottom:6px">Poids membres (somme = 1)</div>
        <div id="member_weights"></div>
        <div style="margin-top:8px" class="tiny">Par défaut : Hélène 0.5, Lucie 0.5, autres 0.</div>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="panel" id="main_table_panel">
      <h2 style="margin-top:0">Tableau principal</h2>
      <div id="main_table_container"></div>
    </div>

    <div class="panel" id="member_legend_panel">
      <h3 style="margin-top:0">Légende & totaux</h3>
      <div id="member_legend"></div>
      <div style="margin-top:8px">Totaux par membre</div>
      <table>
        <thead><tr><th>Membre</th><th>Total payé</th></tr></thead>
        <tbody id="member_totals_tbody"></tbody>
      </table>
    </div>

    <div class="panel fullwidth" id="subtype_detail_panel" style="display:none">
      <h3>Détail: <span id="detail_title"></span></h3>
      <div style="display:flex; gap:10px; margin-bottom:8px;">
        <label><input type="radio" name="detail_pie_mode" value="combined" checked> Combiner (asso+perso)</label>
        <label><input type="radio" name="detail_pie_mode" value="only_asso"> Seulement asso</label>
        <label><input type="radio" name="detail_pie_mode" value="only_perso"> Seulement perso</label>
        <label><input type="radio" name="detail_pie_mode" value="two"> Deux camemberts</label>
      </div>
      <div id="detail_table_container"></div>
      <div id="detail_plot" style="display:flex; gap:12px; flex-wrap:wrap; margin-top:10px"></div>
    </div>

    <div class="panel fullwidth" id="reimburse_panel">
      <h2 style="margin-top:0">Remboursements — résultats</h2>
      <div class="tiny" style="margin-bottom:8px">Algorithme: retirer ANTE à la somme des gains -- séparer selon les poids -- déduire les POST</div>
      <div style="margin-bottom:8px"><button class="btn" id="apply_filters">Appliquer filtres et recalculer</button></div>

      <table>
        <thead><tr>
          <th>Membre</th>
          <th>Total ANTE</th>
          <th>Total POST</th>
          <th>Total ANTE + POST</th>
          <th>Part après ANTE & split</th>
          <th>Montant POST déduit</th>
          <th>Final après POST</th>
        </tr></thead>
        <tbody id="reimb_results_body"></tbody>
      </table>
    </div>

  </div>

<script>
const DATA = __DATA__;
const MEMBERS = __MEMBERS__ || [];
const MEMBER_COLORS = __MEMBER_COLORS__ || {};
const SUBTYPES_BY_TYPE = __SUBTYPES_BY_TYPE__ || {};
const SUM_GAIN = __SUM_GAIN__ || 0.0;

// small helpers for color manipulation
function hexToRgb(hex) {
  if (!hex) return [128,128,128];
  hex = hex.replace('#','');
  if (hex.length===3) hex = hex.split('').map(c=>c+c).join('');
  const bigint = parseInt(hex, 16);
  return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255];
}
function rgbaFromHex(hex, alpha) { const [r,g,b] = hexToRgb(hex); return `rgba(${r},${g},${b},${alpha})`; }
function lightenHex(hex, factor) { // blend with white
  const [r,g,b] = hexToRgb(hex);
  const nr = Math.round(r + (255-r)*factor); const ng = Math.round(g + (255-g)*factor); const nb = Math.round(b + (255-b)*factor);
  return `rgb(${nr},${ng},${nb})`;
}

// formatage monétaire : retourne '' si valeur ~ 0 (pour masquer les 0,00 €)
// usage : fmtMoney(value) -> '' pour ~0 ; fmtMoney(value, true) -> '0,00 €' si ~0
function fmtMoney(x, showZero=false) {
  if (x === undefined || x === null) return showZero ? '0,00 €' : '';
  const EPS = 0.005; // seuil pour considérer comme zéro (arrondi au centime)
  const n = Number(x) || 0;
  if (Math.abs(n) < EPS) return showZero ? '0,00 €' : '';
  const sign = n < 0 ? '-' : '';
  const v = Math.abs(Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
  return sign + v.replace('.', ',') + ' €';
}

// Render legend & totals
// remplacement robuste de render_member_legend_and_totals
function render_member_legend_and_totals() {
  try {
    console.debug('[render_member_legend_and_totals] start', { MEMBERS, MEMBER_COLORS, records_count: (DATA.records||[]).length });

    const legend = document.getElementById('member_legend');
    if (!legend) {
      console.warn('member_legend element introuvable');
      return;
    }
    legend.innerHTML = '';

    // sécurité : MEMBERS doit être un tableau
    const membersList = Array.isArray(MEMBERS) ? MEMBERS : [];
    membersList.forEach(m => {
      const color = MEMBER_COLORS && MEMBER_COLORS[m] ? MEMBER_COLORS[m] : '#cccccc';
      const div = document.createElement('div');
      // on encode le nom sommairement pour éviter injection
      const safeName = String(m).replace(/</g,'&lt;').replace(/>/g,'&gt;');
      div.innerHTML = `<span class="member-swatch" style="background:${color}"></span> <strong>${safeName}</strong>`;
      legend.appendChild(div);
    });

    const tbody = document.getElementById('member_totals_tbody');
    if (!tbody) {
      console.warn('member_totals_tbody introuvable');
      return;
    }
    tbody.innerHTML = '';

    // calcul des totaux en étant tolerant avec les données
    const totals = {};
    const recs = Array.isArray(DATA.records) ? DATA.records : [];
    recs.forEach(r => {
      const memberKey = (r && r.member) ? r.member : '';
      const amt = Number(r && r.amount ? r.amount : 0) || 0;
      totals[memberKey] = (totals[memberKey] || 0) + amt;
    });

    membersList.forEach(m => {
      const tr = document.createElement('tr');
      const totalValue = totals[m] || 0;
      // fmtMoney retourne '' pour les valeurs ~0 selon ton changement
      const display = (typeof fmtMoney === 'function') ? fmtMoney(totalValue) : '';
      tr.innerHTML = `<td style="text-align:left">${m}</td><td style="text-align:right">${display}</td>`;
      tbody.appendChild(tr);
    });

    console.debug('[render_member_legend_and_totals] done', { totals });
  } catch (err) {
    // On log l'erreur mais on ne lève pas afin de ne pas casser tout l'app
    console.error('Erreur dans render_member_legend_and_totals:', err);
    // afficher un message visible dans la page (utile si console non consultée)
    const container = document.getElementById('member_legend') || document.body;
    const msg = document.createElement('div');
    msg.style.color = 'crimson';
    msg.style.marginTop = '8px';
    msg.textContent = 'Erreur d\'affichage (voir console).';
    container.appendChild(msg);
  }
}


// Build main table with pastel column background per member
function build_main_table() {
  if (!Array.isArray(DATA.records)) { document.getElementById('main_table_container').innerText = 'Données manquantes ou mal formatées'; return; }
  const byType = {};
  DATA.records.forEach(r=>{
    const t = r.spent_type || '';
    const rowKey = r.spent_subtype || '(no subtype)';
    if (!byType[t]) byType[t] = {};
    if (!byType[t][rowKey]) byType[t][rowKey] = {totals:{}, total:0, rowKey:rowKey, spent_type:t};
    const cur = byType[t][rowKey]; const m = r.member||''; cur.totals[m] = (cur.totals[m]||0) + (r.amount||0); cur.total = (cur.total||0) + (r.amount||0);
  });

  const container = document.getElementById('main_table_container'); container.innerHTML='';
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  let head = '<tr><th>ligne</th>';
  MEMBERS.forEach((m, idx)=> head += `<th style="text-align:right; background:${lightenHex(MEMBER_COLORS[m]||'#ddd',0.85)}">${m}</th>`);
  head += '<th style="text-align:right">Total</th></tr>';
  thead.innerHTML = head; table.appendChild(thead);
  const tbody = document.createElement('tbody');

  const order = Object.keys(byType).sort((a,b)=>{ if (a.toLowerCase()==='asso') return -1; if (b.toLowerCase()==='asso') return 1; if (a.toLowerCase()==='perso') return -1; if (b.toLowerCase()==='perso') return 1; return a.localeCompare(b); });
  let grandTotal = 0;
  order.forEach(t=>{
    const hdr = document.createElement('tr'); hdr.innerHTML = `<td class="namecell" colspan="${2+MEMBERS.length}"><strong>${t.toUpperCase()}</strong></td>`; tbody.appendChild(hdr);
    const rows = Object.values(byType[t]).sort((a,b)=>b.total - a.total);
    let subtotal = 0;
    rows.forEach(r=>{
      const tr = document.createElement('tr');
      const tdName = document.createElement('td'); tdName.className='namecell'; tdName.innerText = r.rowKey; tr.appendChild(tdName);
      MEMBERS.forEach(m=>{ const td=document.createElement('td'); td.style.textAlign='right'; td.style.background = lightenHex(MEMBER_COLORS[m]||'#eee', 0.88); td.innerText = fmtMoney(r.totals[m]||0); tr.appendChild(td); });
      const tdTot = document.createElement('td'); tdTot.style.textAlign='right'; tdTot.innerHTML = `<strong>${fmtMoney(r.total||0)}</strong>`; tr.appendChild(tdTot);
      tr.classList.add('clickable'); tr.addEventListener('click', ()=> show_subtype_detail(r.spent_type || t, r.rowKey));
      tbody.appendChild(tr); subtotal += r.total||0;
    });
    const trsub = document.createElement('tr'); trsub.className='subtotal'; const tdlabel=document.createElement('td'); tdlabel.className='namecell'; tdlabel.innerText = `Sous-total ${t}`; trsub.appendChild(tdlabel);
    MEMBERS.forEach(m=>{ const s = rows.reduce((acc,row)=>acc + (row.totals[m]||0),0); const td=document.createElement('td'); td.style.textAlign='right'; td.style.background = lightenHex(MEMBER_COLORS[m]||'#eee',0.9); td.innerText = fmtMoney(s); trsub.appendChild(td); });
    const tdsub=document.createElement('td'); tdsub.style.textAlign='right'; tdsub.innerHTML = `<strong>${fmtMoney(subtotal)}</strong>`; trsub.appendChild(tdsub); tbody.appendChild(trsub);
    grandTotal += subtotal;
  });
  const trtot = document.createElement('tr'); trtot.className='total'; const tdlabel2 = document.createElement('td'); tdlabel2.className='namecell'; tdlabel2.innerText='TOTAL'; trtot.appendChild(tdlabel2);
  MEMBERS.forEach(m=>{ const s = DATA.records.reduce((acc,r)=>acc + ((r.member===m)?(r.amount||0):0),0); const td=document.createElement('td'); td.style.textAlign='right'; td.style.background = lightenHex(MEMBER_COLORS[m]||'#eee',0.89); td.innerText = fmtMoney(s); trtot.appendChild(td); });
  const tdgt = document.createElement('td'); tdgt.style.textAlign='right'; tdgt.innerHTML = `<strong>${fmtMoney(grandTotal)}</strong>`; trtot.appendChild(tdgt); tbody.appendChild(trtot);
  table.appendChild(tbody); container.appendChild(table);
}

// Detail subtype with combined/two/only modes
function show_subtype_detail(spent_type, subtype) {
  document.getElementById('subtype_detail_panel').style.display='block';
  document.getElementById('detail_title').innerText = subtype + ' (' + spent_type + ')';
  const allRecs = (DATA.records || []).filter(r => r.spent_subtype === subtype);
  const assoRecs = allRecs.filter(r => r.spent_type === 'asso');
  const persoRecs = allRecs.filter(r => r.spent_type === 'perso');

  // table by spent_name x member (join both types)
  const rowsMap = {};
  allRecs.forEach(r=>{
    const name = r.spent_name || '(no name)';
    if (!rowsMap[name]) rowsMap[name] = {name:name, totals:{}, total:0, parts:{asso:0, perso:0}};
    rowsMap[name].totals[r.member] = (rowsMap[name].totals[r.member]||0) + (r.amount||0);
    rowsMap[name].total += r.amount||0;
    if (r.spent_type === 'asso') rowsMap[name].parts.asso += r.amount||0; else rowsMap[name].parts.perso += r.amount||0;
  });
  const rows = Object.values(rowsMap);
  const container = document.getElementById('detail_table_container'); container.innerHTML='';
  const table = document.createElement('table');
  let head = '<thead><tr><th>spent_name</th>';
  MEMBERS.forEach(m=> head += `<th style="text-align:right">${m}</th>`);
  head += '<th style="text-align:right">Total</th></tr></thead>';
  table.innerHTML = head; const tb = document.createElement('tbody');
  rows.forEach(r=>{ const tr=document.createElement('tr'); let html = `<td class="namecell">${r.name}</td>`; MEMBERS.forEach(m=> html += `<td style="text-align:right">${fmtMoney(r.totals[m]||0)}</td>`); html += `<td style="text-align:right">${fmtMoney(r.total||0)}</td>`; tr.innerHTML = html; tb.appendChild(tr); });
  table.appendChild(tb); container.appendChild(table);

  function make_plots(mode) {
    const plotDiv = document.getElementById('detail_plot'); plotDiv.innerHTML='';
    if (mode === 'two') {
      // draw 2 pies side by side
      function buildPie(recs, title) {
        const sums = {}; recs.forEach(r=> sums[r.member] = (sums[r.member]||0) + r.amount);
        const labels = [], vals = [], colors = [];
        MEMBERS.forEach(m=>{ if ((sums[m]||0) > 0) { labels.push(m); vals.push(sums[m]); colors.push(rgbaFromHex(MEMBER_COLORS[m]||'#888',0.9)); } });
        const div = document.createElement('div'); div.style.width='45%'; div.style.minWidth='260px'; div.style.height='320px'; plotDiv.appendChild(div);
        if (labels.length) Plotly.newPlot(div, [{values:vals, labels:labels, type:'pie', marker:{colors:colors}, textinfo:'label+percent+value', name:title}], {margin:{t:20,b:10}});
        else div.innerHTML = `<div class="muted">Aucun ${title}</div>`;
      }
      buildPie(assoRecs, 'asso'); buildPie(persoRecs, 'perso');
    } else {
      let recs = [];
      if (mode === 'combined') recs = assoRecs.concat(persoRecs);
      else if (mode === 'only_asso') recs = assoRecs;
      else recs = persoRecs;
      const sums = {}; recs.forEach(r=> sums[r.member] = (sums[r.member]||0) + r.amount);
      const labels = [], vals = [], colors = [];
      MEMBERS.forEach(m=>{ if ((sums[m]||0) > 0) { labels.push(m); vals.push(sums[m]); // use slightly stronger color for slices
        colors.push(rgbaFromHex(MEMBER_COLORS[m]||'#888', 0.95)); } });
      const div = document.createElement('div'); div.style.width='60%'; div.style.minWidth='300px'; div.style.height='360px'; plotDiv.appendChild(div);
      if (labels.length) Plotly.newPlot(div, [{values:vals, labels:labels, type:'pie', marker:{colors:colors}, textinfo:'label+percent+value'}], {margin:{t:20,b:10}});
      else div.innerHTML = '<div class="muted">Aucune donnée</div>';
    }
  }
  document.querySelectorAll('input[name="detail_pie_mode"]').forEach(inp=> inp.onchange = ()=> make_plots(document.querySelector('input[name="detail_pie_mode"]:checked').value));
  make_plots('combined');
}

// Build ANTE choices UI
function build_ante_choice_ui() {
  const container = document.getElementById('ante_choice_container'); container.innerHTML='';
  function renderChoices(gran) {
    container.innerHTML = '';
    const items = new Set(); (DATA.records||[]).forEach(r=>{
      if (gran === 'type') items.add(r.spent_type || '(no type)');
      else if (gran === 'subtype') items.add(r.spent_subtype || '(no subtype)');
      else items.add(r.spent_name || '(no name)');
    });
    const sorted = Array.from(items).sort(); sorted.forEach(it=>{
      const id = 'ante_' + gran + '_' + it.replace(/[^a-zA-Z0-9_\-]/g,'_');
      const div = document.createElement('div'); div.innerHTML = `<label><input type="checkbox" id="${id}" value="${it}"> ${it}</label>`; container.appendChild(div);
    });
    if (gran === 'type') {
      const targets = Array.from(document.querySelectorAll('input[id^="ante_type_"]')); const t = targets.find(x=>x.value.toLowerCase()==='asso'); if (t) t.checked = true;
    }
  }
  renderChoices('type'); document.querySelectorAll('input[name="ante_gran"]').forEach(inp=> inp.onchange = ()=> renderChoices(document.querySelector('input[name="ante_gran"]:checked').value));
}

function build_member_weight_inputs(defaultWeights) {
  const container = document.getElementById('member_weights'); container.innerHTML='';
  MEMBERS.forEach(m=>{ const id = 'weight_' + m.replace(/[^a-zA-Z0-9]/g,'_'); const val = (defaultWeights && defaultWeights[m]!==undefined) ? defaultWeights[m] : (1.0 / MEMBERS.length); const div = document.createElement('div'); div.innerHTML = `<label style="display:flex; gap:8px; align-items:center"><span style="min-width:120px">${m}</span><input type="number" id="${id}" step="0.01" value="${val.toFixed(2)}" min="0" max="1"></label>`; container.appendChild(div); });
}

// Core reimbursement algorithm and render
function compute_reimbursements_and_render() {
  const granElem = document.querySelector('input[name="ante_gran"]:checked');
  const gran = granElem ? granElem.value : 'type';
  const selected = new Set(); Array.from(document.querySelectorAll('#ante_choice_container input[type="checkbox"]')).forEach(ch=>{ if (ch.checked) selected.add(ch.value); });

  const weights = {}; let wsum=0; MEMBERS.forEach(m=>{ const id='weight_'+m.replace(/[^a-zA-Z0-9]/g,'_'); const v=parseFloat(document.getElementById(id).value)||0; weights[m]=v; wsum+=v; });
  if (wsum<=0) MEMBERS.forEach(m=> weights[m]=1.0/MEMBERS.length); else for (let k in weights) weights[k]=weights[k]/wsum;

  const isAnte = {};
  (DATA.records||[]).forEach((r, idx)=>{ let key = (gran==='type') ? r.spent_type : (gran==='subtype' ? r.spent_subtype : r.spent_name); isAnte[idx] = selected.has(key); });

  let total_ante = 0, total_post = 0;
  const ante_totals_by_member = {}; const post_totals_by_member = {};
  const ante_asso_by_member = {}; const ante_perso_by_member = {};
  const post_asso_by_member = {}; const post_perso_by_member = {};
  MEMBERS.forEach(m=>{ ante_totals_by_member[m]=0; post_totals_by_member[m]=0; ante_asso_by_member[m]=0; ante_perso_by_member[m]=0; post_asso_by_member[m]=0; post_perso_by_member[m]=0; });

  (DATA.records||[]).forEach((r, idx)=>{
    const m = r.member;
    if (isAnte[idx]) { total_ante += r.amount||0; ante_totals_by_member[m] = (ante_totals_by_member[m]||0) + (r.amount||0); if (r.spent_type==='asso') ante_asso_by_member[m] = (ante_asso_by_member[m]||0) + (r.amount||0); else ante_perso_by_member[m] = (ante_perso_by_member[m]||0) + (r.amount||0); }
    else { total_post += r.amount||0; post_totals_by_member[m] = (post_totals_by_member[m]||0) + (r.amount||0); if (r.spent_type==='asso') post_asso_by_member[m] = (post_asso_by_member[m]||0) + (r.amount||0); else post_perso_by_member[m] = (post_perso_by_member[m]||0) + (r.amount||0); }
  });

  // COVER ANTE from SUM_GAIN
  const covered_ante = Math.min(SUM_GAIN, total_ante);
  const remaining_gain = Math.max(SUM_GAIN - covered_ante, 0);

  // allocate covered_ante proportionally to members' ante contributions
  const allocated_ante = {}; MEMBERS.forEach(m=> allocated_ante[m]=0);
  const total_ante_contrib = Object.values(ante_totals_by_member).reduce((a,b)=>a+b,0);
  if (total_ante_contrib > 0) {
    MEMBERS.forEach(m=> allocated_ante[m] = covered_ante * ((ante_totals_by_member[m]||0) / total_ante_contrib));
  }

  // remaining_gain split by weights -> each member gets part_after_ante
  const part_after_ante = {}; MEMBERS.forEach(m=> part_after_ante[m] = remaining_gain * (weights[m] || 0));

  // For each member, POST is simply post_totals_by_member[m]
  // Final after post = part_after_ante - post_member
  const results = {};
  MEMBERS.forEach(m=>{
    const totalAnte = ante_totals_by_member[m] || 0;
    const totalPost = post_totals_by_member[m] || 0;
    const totalAP = totalAnte + totalPost;
    const partAfter = part_after_ante[m] || 0;
    const finalAfterPost = partAfter - totalPost; // can be negative
    results[m] = {
      total_ante: totalAnte,
      total_post: totalPost,
      total_ante_post: totalAP,
      part_after_ante_split: partAfter,
      final_after_post: finalAfterPost
    };
  });

  // render
  const tbody = document.getElementById('reimb_results_body'); tbody.innerHTML = '';
  MEMBERS.forEach(m=>{
    const r = results[m];
    const tr = document.createElement('tr');
    tr.innerHTML = `<td style="text-align:left">${m}</td>
      <td style="text-align:right">${fmtMoney(r.total_ante||0)}</td>
      <td style="text-align:right">${fmtMoney(r.total_post||0)}</td>
      <td style="text-align:right">${fmtMoney(r.total_ante_post||0)}</td>
      <td style="text-align:right">${fmtMoney(r.part_after_ante_split||0)}</td>
      <td style="text-align:right">${fmtMoney(r.total_post||0)}</td>
      <td style="text-align:right"><strong>${fmtMoney(r.final_after_post||0)}</strong></td>`;
    tbody.appendChild(tr);
  });

  console.log('reimburse summary', {SUM_GAIN, total_ante, covered_ante, remaining_gain, results});
}

// default weights
function default_weights(members) {
  const w = {}; members.forEach(m=>{ const nm=m.toLowerCase(); if (nm.includes('helene')||nm.includes('hélène')) w[m]=0.5; else if (nm.includes('lucie')) w[m]=0.5; else w[m]=0.0; });
  const s = Object.values(w).reduce((a,b)=>a+b,0); if (s>0) for (let k in w) w[k]=w[k]/s; else members.forEach(m=> w[m]=1.0/members.length); return w;
}

function init() {
  document.getElementById('sum_gain_label').innerText = `${SUM_GAIN.toFixed(2)} €`;
  render_member_legend_and_totals(); build_main_table(); build_ante_choice_ui(); build_member_weight_inputs(default_weights(MEMBERS));
  document.getElementById('apply_filters').addEventListener('click', compute_reimbursements_and_render);
  compute_reimbursements_and_render();
}

init();
</script>
</body>
</html>'''

# -------------------- generate html --------------------

def safe_json_for_js(obj):
    s = json.dumps(obj, ensure_ascii=False, allow_nan=False)
    return s.replace('</', '<\\/')


def generate_html(out_path, agg):
    data_json = safe_json_for_js(agg)
    members_json = safe_json_for_js(agg['members'])
    member_colors_json = safe_json_for_js(agg['member_colors'])
    subtypes_by_type_json = safe_json_for_js(agg['subtypes_by_type'])
    sum_gain_json = json.dumps(float(SUM_GAIN))

    html = HTML_TEMPLATE.replace('__DATA__', data_json)
    html = html.replace('__MEMBERS__', members_json)
    html = html.replace('__MEMBER_COLORS__', member_colors_json)
    html = html.replace('__SUBTYPES_BY_TYPE__', subtypes_by_type_json)
    html = html.replace('__SUM_GAIN__', sum_gain_json)
    html = html.replace('{{SUM_GAIN_LABEL}}', f'{SUM_GAIN:.2f} €')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'HTML généré -> {out_path} (SUM_GAIN = {SUM_GAIN})')

# -------------------- main --------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='infile', default='data_summer_2025.csv')
    parser.add_argument('--out', dest='outfile', default='report_v3.html')
    args = parser.parse_args()

    csv_path = args.infile
    if not os.path.exists(csv_path):
        print(f"[Info] CSV '{csv_path}' introuvable. Utilisation d'un exemple embarqué pour démo.")
        sample = '''spent_type,spent_subtype,spent_name,amount,member,is_bill,spent_id
perso,instrument,archet,85,Lucie,1,0
perso,divers,rouge a levres,06.05,Lucie ,1,1
perso,instrument,cordes,"288,9",Lucie,1,2
perso,vetement,robe,"83,3",Lucie,1,3
perso,instrument,archet,80,Helene,1,4
perso,instrument,cordes,"99,9",Helene,1,5
perso,vetement,robes,"100,3",Helene,1,6
asso,divers,bombes,"7,7",Helene,1,7
asso,corep,affiche ; flyer,"20,71",Lucie,1,8
asso,corep,affiche ; flyer,"22,5",Helene,1,9
asso,corep,flyer,"9,99",David,1,10
asso,corep,abonnement,23,Nathalie,1,11
perso,alimentation,the,"7,2",Lucie,1,12
asso,alimentation,marqueur ; eau,"1,44",Lucie,1,13
asso,alimentation,snack,"6,37",Lucie,1,14
perso,poste,poste,"10,45",Helene,1,15
asso,paroisse,sainthermeland,50,asso,1,17
asso,paroisse,toutlemonde,50,asso,1,18
asso,paroisse,valençais,50,asso,1,19
asso,paroisse,chateaumeilland,50,asso,1,20
asso,poste,affiches,"4,72",Nathalie,1,21
asso,corep,flyer,"8,11",Helene,1,22
asso,corep,flyer ,"8,11",Helene,1,23
asso,corep,flyer,"16,22",Lucie,1,24
asso,corep,flyer,"14,11",Lucie,1,25
asso,corep,flyer,"8,11",Lucie,1,26
asso,corep,carte ; affiche,40,Lucie,1,27
perso,vetement,robes,-49,Hélène ,,6
perso,vetement,robes,-49,Lucie,,3
perso,frais_km,toulouse-chateauroux,"34,99",Lucie,,28
perso,frais_km,nantes-issoudun,"32,29",Lucie,,29
perso,frais_km,velles-verrieresenanjou,"21,99",Lucie,,30
perso,frais_km,angers-orvault,"5,99",Lucie,,31
'''
        with open('expenses_example_used.csv', 'w', encoding='utf-8') as f:
            f.write(sample)
        csv_path = 'expenses_example_used.csv'

    df = load_and_clean(csv_path)
    agg = compute_aggregates(df)
    generate_html(args.outfile, agg)

if __name__ == '__main__':
    main()
