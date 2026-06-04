/* ─── State ─────────────────────────────────────────────────────────────── */
let currentTab  = 'forex';
let selectedTZ  = Intl.DateTimeFormat().resolvedOptions().timeZone;
let _lastData   = null;

const ALL_TZ = (() => {
  try { return Intl.supportedValuesOf('timeZone'); }
  catch {
    return [
      'UTC','Africa/Cairo','America/Chicago','America/Los_Angeles',
      'America/New_York','America/Sao_Paulo','America/Toronto',
      'Asia/Bangkok','Asia/Dhaka','Asia/Dubai','Asia/Hong_Kong',
      'Asia/Jakarta','Asia/Karachi','Asia/Kolkata','Asia/Seoul',
      'Asia/Shanghai','Asia/Singapore','Asia/Tokyo','Australia/Sydney',
      'Europe/Amsterdam','Europe/Berlin','Europe/Istanbul','Europe/London',
      'Europe/Moscow','Europe/Paris','Europe/Zurich','Pacific/Auckland',
    ];
  }
})();

/* ═══════════════════════════════════════════════════════════════════════════
   TOOLTIP SYSTEM
   Every element with [data-tip="id"] shows a pop-up on hover.
   Tips are stored in TIPS{} and re-built on each render.
═══════════════════════════════════════════════════════════════════════════ */
const TIPS = {};
let _tipId = 0;

const tipBox = document.createElement('div');
tipBox.id = 'tooltip-box';
tipBox.innerHTML = '<div id="tip-title"></div><div id="tip-body"></div>';
document.body.appendChild(tipBox);

/* Follow cursor */
document.addEventListener('mousemove', e => {
  if (tipBox.style.display !== 'block') return;
  let x = e.clientX + 18, y = e.clientY + 14;
  if (x + 310 > window.innerWidth)  x = e.clientX - 316;
  if (y + 170 > window.innerHeight) y = e.clientY - 170;
  tipBox.style.left = x + 'px';
  tipBox.style.top  = y + 'px';
});

/* Show or hide based on hover target */
document.addEventListener('mouseover', e => {
  const target = e.target.closest('[data-tip]');
  if (target) {
    const tip = TIPS[target.dataset.tip];
    if (tip) {
      document.getElementById('tip-title').textContent = tip.title;
      document.getElementById('tip-body').innerHTML   = tip.body;
      tipBox.style.display = 'block';
    }
  } else if (!e.target.closest('#tooltip-box')) {
    tipBox.style.display = 'none';
  }
});

/* Mobile: tap on [data-tip] to show tooltip; tap outside to dismiss */
let _touchTipEl = null;
document.addEventListener('touchend', e => {
  if (e.target.closest('a')) return;               // let links work normally
  const target = e.target.closest('[data-tip]');
  if (target) {
    const tip = TIPS[target.dataset.tip];
    if (!tip) return;
    if (_touchTipEl === target && tipBox.style.display === 'block') {
      tipBox.style.display = 'none'; _touchTipEl = null; return;
    }
    _touchTipEl = target;
    document.getElementById('tip-title').textContent = tip.title;
    document.getElementById('tip-body').innerHTML   = tip.body;
    const r = target.getBoundingClientRect();
    const tw = Math.min(300, window.innerWidth - 20);
    let x = Math.max(10, Math.min(r.left, window.innerWidth - tw - 10));
    let y = r.bottom + 10;
    if (y + 200 > window.innerHeight) y = Math.max(10, r.top - 210);
    tipBox.style.left    = x + 'px';
    tipBox.style.top     = y + 'px';
    tipBox.style.maxWidth = tw + 'px';
    tipBox.style.display = 'block';
  } else if (!e.target.closest('#tooltip-box')) {
    tipBox.style.display = 'none'; _touchTipEl = null;
  }
}, { passive: true });

/* Register a tip and return its id */
function mkTip(title, body) {
  const id = 'T' + (_tipId++);
  TIPS[id] = { title, body };
  return id;
}

/* Attach a tip directly to an element */
function setTip(elem, title, body) {
  if (!elem) return;
  elem.setAttribute('data-tip', mkTip(title, body));
}

/* Attach a tip to the <tr> that contains a given cell id */
function rowTip(cellId, title, body) {
  const cell = document.getElementById(cellId);
  if (cell) setTip(cell.closest('tr'), title, body);
}

/* Reset tips on each new render */
function resetTips() {
  Object.keys(TIPS).forEach(k => delete TIPS[k]);
  _tipId = 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DESCRIPTION FUNCTIONS  (one per indicator / section)
   Each returns an HTML string used inside the tooltip body.
   No em-dashes used anywhere.
═══════════════════════════════════════════════════════════════════════════ */

function dRSI(val, label) {
  let state, note;
  if      (val > 70) { state = 'Overbought';              note = 'Price has risen too fast. A short pullback or pause is likely soon.'; }
  else if (val < 30) { state = 'Oversold';                note = 'Price has fallen too far. A bounce or recovery may be near.'; }
  else if (val > 50) { state = 'Neutral, bullish lean';  note = 'Momentum is balanced but buyers have a slight edge.'; }
  else               { state = 'Neutral, bearish lean';  note = 'Momentum is balanced but sellers have a slight edge.'; }
  return `${label} RSI is <strong>${val}</strong> which means <strong>${state}</strong>.<br>${note}<small>Scale: 0 to 30 = Oversold | 30 to 70 = Neutral | 70 to 100 = Overbought</small>`;
}

function dMACD(isAbove, label) {
  return isAbove
    ? `${label} MACD is <strong>Above</strong> its signal line.<br>Buying momentum is currently stronger than selling. Short-term buyers are in control.<small>MACD crossing above signal = bullish momentum signal</small>`
    : `${label} MACD is <strong>Below</strong> its signal line.<br>Selling momentum is currently stronger than buying. Short-term sellers are in control.<small>MACD crossing below signal = bearish momentum signal</small>`;
}

function dMA(isAbove, label) {
  return isAbove
    ? `${label} MA20 is <strong>Above</strong> MA50.<br>Short-term average price is higher than long-term average. Bullish alignment — recent price action is strong.<small>MA20 above MA50 = short-term strength confirmed</small>`
    : `${label} MA20 is <strong>Below</strong> MA50.<br>Short-term average price is lower than long-term average. Bearish alignment — recent price is weaker than history.<small>MA20 below MA50 = short-term weakness confirmed</small>`;
}

function dTrend(trend, label) {
  return trend === 'up'
    ? `${label} trend is <strong>Upward</strong>.<br>Current price is above the 50-period moving average. The market is in an upward momentum phase on this timeframe.<small>Price above MA50 = bullish trend</small>`
    : `${label} trend is <strong>Downward</strong>.<br>Current price is below the 50-period moving average. The market is in a downward momentum phase on this timeframe.<small>Price below MA50 = bearish trend</small>`;
}

function dATR(val, label) {
  const lvl  = val > 1 ? 'High' : val > 0.4 ? 'Medium' : 'Low';
  const note = val > 1
    ? 'Large price swings are occurring. Higher chance of sudden moves in either direction.'
    : val > 0.4
    ? 'Normal price movement. Standard market conditions with typical risk.'
    : 'Market is calm and quiet. Low chance of sudden unexpected price spikes.';
  return `${label} ATR Volatility is <strong>${val}%</strong> — <strong>${lvl} volatility</strong>.<br>${note}<small>ATR = how much price moves on average. Low = quiet. High = volatile.</small>`;
}

function dSupport(val) {
  return `Daily Support level: <strong>${val}</strong><br>This is the recent price floor based on the lowest lows of the last 30 candles. If price drops to this area, buyers have historically stepped in and pushed price back up.<br>Breaking below this level could signal further decline.`;
}

function dResistance(val) {
  return `Daily Resistance level: <strong>${val}</strong><br>This is the recent price ceiling based on the highest highs of the last 30 candles. If price rises to this area, sellers have historically pushed price back down.<br>Breaking above this level could signal further rise.`;
}

function dHSupport(val) {
  return `Hourly Support level: <strong>${val}</strong><br>Nearest price floor on the hourly chart. A short-term bounce zone. Closer to current price than daily support, so more immediately relevant for short-term trades.`;
}

function dHResistance(val) {
  return `Hourly Resistance level: <strong>${val}</strong><br>Nearest price ceiling on the hourly chart. A short-term rejection zone. Closer to current price than daily resistance, so more immediately relevant for short-term trades.`;
}

function dBias(bias, score) {
  const str = score >= 70 ? 'strong' : score >= 50 ? 'moderate' : 'weak';
  if (bias === 'up')
    return `Overall bias is <strong>BULLISH</strong> with ${str} alignment (score ${score}/100).<br>More signals are pointing upward than downward. The higher the score, the more signals agree. This is not a guarantee — it is a measure of signal alignment.`;
  if (bias === 'down')
    return `Overall bias is <strong>BEARISH</strong> with ${str} alignment (score ${score}/100).<br>More signals are pointing downward than upward. Score of ${score} indicates ${str} bearish conviction across all layers.`;
  return `Overall bias is <strong>UNCLEAR</strong> with score ${score}/100.<br>Signals are conflicting with roughly equal bullish and bearish forces. This is not a good time for a high-conviction directional trade.`;
}

function dGauge(score) {
  const str = score >= 70 ? 'Strong' : score >= 50 ? 'Moderate' : score >= 35 ? 'Weak' : 'Very Weak';
  return `Alignment Score: <strong>${score} out of 100</strong> — ${str}.<br>This number shows how much all the research layers (technical, intermarket, sentiment, events) agree with each other. Higher score means stronger agreement in one direction.<small>This is NOT a win probability. It is a signal agreement measure. Always use proper risk management.</small>`;
}

function dScoreCard(name, pts, max, dir, extra) {
  const pct = Math.round(pts / max * 100);
  return `<strong>${name}: ${pts} out of ${max} points (${pct}%)</strong><br>Direction contribution: <strong>${capFirst(dir) || 'Neutral'}</strong>.<br>${extra}`;
}

function dDollar(dollar) {
  const map = {
    strengthening: `US Dollar is <strong>Strengthening</strong>.<br>EUR/USD is falling and USD/JPY is rising — both confirm Dollar gaining power. For EUR/USD this creates downward (bearish) pressure on the Euro.`,
    weakening:     `US Dollar is <strong>Weakening</strong>.<br>EUR/USD is rising and USD/JPY is falling — both confirm Dollar losing power. For EUR/USD this creates upward (bullish) support for the Euro.`,
    mixed:         `US Dollar shows <strong>Mixed</strong> signals.<br>EUR/USD and USD/JPY are pointing in different directions. Dollar strength is not confirmed — this section adds fewer points to the score.`,
    unknown:       `Dollar strength is <strong>Unknown</strong>.<br>Could not retrieve the data needed to assess Dollar direction. This section contributes 0 points.`,
  };
  return (map[dollar] || map.unknown) + `<small>Proxy for the Dollar Index (DXY) using EUR/USD and USD/JPY trends</small>`;
}

function dEURUSD(trend) {
  if (trend === 'up')   return `EUR/USD daily trend is <strong>Up</strong>.<br>The Euro is stronger than the Dollar on the daily chart. This suggests Dollar is weakening — a bullish signal for EUR/USD.<small>EUR/USD rising = Dollar losing strength</small>`;
  if (trend === 'down') return `EUR/USD daily trend is <strong>Down</strong>.<br>The Euro is weaker than the Dollar on the daily chart. This confirms the Dollar is strengthening — a bearish signal for EUR/USD.<small>EUR/USD falling = Dollar gaining strength</small>`;
  return `EUR/USD trend is <strong>Neutral</strong>.<br>No clear directional confirmation from this pair. EUR/USD is trading near its 50-period moving average.`;
}

function dUSDJPY(trend) {
  if (trend === 'up')   return `USD/JPY daily trend is <strong>Up</strong>.<br>The Dollar is stronger than the Japanese Yen. This confirms global Dollar strength — a bearish signal for EUR/USD.<small>USD/JPY rising = Dollar gaining strength globally</small>`;
  if (trend === 'down') return `USD/JPY daily trend is <strong>Down</strong>.<br>The Dollar is weaker than the Japanese Yen. This confirms global Dollar weakness — a bullish signal for EUR/USD.<small>USD/JPY falling = Dollar losing strength globally</small>`;
  return `USD/JPY trend is <strong>Neutral</strong>.<br>No clear directional confirmation from this pair.`;
}

function dSentLabel(label, score) {
  if (label === 'bullish') return `News sentiment is <strong>Bullish</strong> (score: ${score}).<br>Recent news articles lean positive about this asset. This adds bullish weight to the overall alignment score.`;
  if (label === 'bearish') return `News sentiment is <strong>Bearish</strong> (score: ${score}).<br>Recent news articles lean negative about this asset. This adds bearish weight to the overall alignment score.`;
  return `News sentiment is <strong>Neutral</strong> (score: ${score}).<br>No strong positive or negative news bias detected. This section contributes 0 points to the alignment score.`;
}

function dSentScore(score) {
  const abs = Math.abs(Number(score));
  const str = abs > 0.3 ? 'Strong bias' : abs > 0.15 ? 'Moderate bias' : 'Weak or no bias';
  return `Sentiment score is <strong>${score}</strong>.<br>Range: -1.0 (very bearish) to +1.0 (very bullish). A score near 0 means no clear news direction.<br>Current strength: <strong>${str}</strong><small>Scores above +0.15 = Bullish | Below -0.15 = Bearish | In between = Neutral</small>`;
}

function dArticles(count) {
  if (count === 0) return `<strong>0 articles</strong> were scanned.<br>No news data was found for this ticker. Sentiment analysis is unavailable. This may be due to API limits or this symbol not being covered by the news source.`;
  return `<strong>${count} articles</strong> were scanned to calculate the sentiment score.<br>More articles generally mean a more reliable sentiment reading. All articles were analyzed for positive or negative language about this asset.`;
}

function dEvent(ev) {
  const isHigh   = ['high', '3'].includes(String(ev.impact).toLowerCase());
  const impLabel = isHigh ? 'HIGH IMPACT' : 'MEDIUM IMPACT';
  const impNote  = isHigh
    ? 'Major release. Expect large, fast price movement when published. Avoid open trades right before this event.'
    : 'Moderate impact expected. Price may move noticeably but less dramatically than high-impact events.';
  const est = ev.estimate ? `Market estimate: <strong>${ev.estimate}</strong>` : 'No market estimate yet.';
  return `<strong>${ev.event}</strong><br>Country: ${ev.country || 'N/A'} &nbsp; Impact: ${impLabel}<br>Time: ${ev.time || 'N/A'} UTC<br>${est}<small>${impNote}</small>`;
}

function dSentimentLabel(label) {
  const map = {
    bullish: 'Overall sentiment from news is positive. This supports the bullish case.',
    bearish: 'Overall sentiment from news is negative. This supports the bearish case.',
    neutral: 'No strong news direction found. Sentiment is not pushing the score either way.',
  };
  return map[label] || map.neutral;
}

/* ═══════════════════════════════════════════════════════════════════════════
   TRADE GUIDANCE — TOOLTIP DESCRIPTIONS
═══════════════════════════════════════════════════════════════════════════ */

function dTGSignal(signal, score) {
  const str = score >= 70 ? 'strong' : score >= 50 ? 'moderate' : 'weak';
  if (signal === 'up')
    return `BUY signal means more indicators are pointing <strong>upward</strong> than downward. Current alignment strength is <strong>${str}</strong> (score ${score}/100).<br>A BUY signal suggests looking for long trade setups — but always confirm with your own analysis before entering.<small>Higher score = more signals agree = higher conviction</small>`;
  if (signal === 'down')
    return `SELL signal means more indicators are pointing <strong>downward</strong> than upward. Current alignment strength is <strong>${str}</strong> (score ${score}/100).<br>A SELL signal suggests looking for short trade setups — but always confirm with your own analysis before entering.<small>Higher score = more signals agree = higher conviction</small>`;
  return `<strong>No clear signal.</strong> Indicators are conflicting with roughly equal bullish and bearish pressure. Best to wait for better alignment before risking any capital.<small>Score below 35 = avoid trading. Wait for score 50+</small>`;
}

function dTGProbability(upProb, downProb, score) {
  const majority = downProb >= upProb ? downProb : upProb;
  const dir      = downProb >= upProb ? 'bearish' : 'bullish';
  return `Signal probability shows <strong>${majority}% toward ${dir}</strong> direction, estimated from the alignment score (${score}/100).<br>Formula: bias direction = 50% base + score/2 — so score 0 = 50/50 (no edge), score 100 = fully aligned.<small>This is NOT a win guarantee. Markets can move against any signal. Always use a stop loss.</small>`;
}

function dTGStopLoss(priceStr, dist, isBuy) {
  return `<strong>Stop Loss at ${priceStr}</strong> — this is your maximum risk point. If price reaches this level, exit the trade to prevent larger losses.<br>Distance from entry: <strong>${dist}</strong>. Set ${isBuy ? 'below the nearest hourly support zone' : 'above the nearest hourly resistance zone'} with an ATR buffer.<small>Never trade without a stop loss. This level is a calculated reference — adjust based on your risk tolerance.</small>`;
}

function dTGEntry(priceStr) {
  return `<strong>Entry Zone at ${priceStr}</strong> — approximately the current market price at time of analysis.<br>Use this as the reference point for all distance and risk/reward calculations. Your actual entry price may differ slightly due to spread or slippage.<small>Always check live price before entering. Do not chase a price that has moved significantly from this level.</small>`;
}

function dTGTP(num, priceStr, dist, rrStr, isHourly) {
  const zone = isHourly ? 'nearest hourly resistance/support level' : 'daily resistance/support level — a wider target';
  return `<strong>Take Profit ${num} at ${priceStr}</strong> — your profit target based on the ${zone}.<br>Distance from entry: <strong>${dist}</strong>. Risk/Reward: <strong>${rrStr}</strong> meaning for every 1 pip risked, you could gain ${rrStr.split(':')[1]} pips if this target is reached.<small>Close part of the position at TP1 to secure profit, then let the rest run toward TP2.</small>`;
}

function dTGConfidence(conf, score) {
  const map = {
    'Strong':    'Strong alignment across all indicators. Most signals agree. This setup has higher conviction — standard position size is appropriate.',
    'Moderate':  'Moderate alignment. Signals partially agree. The bias is real but not dominant. Consider using a smaller position size than usual.',
    'Weak':      'Weak alignment. Indicators barely agree. High chance of a false signal. Paper trade this setup or skip it entirely.',
    'Very Weak': 'Very weak alignment. Signals are mostly conflicting. No trade is recommended. Wait for score to reach at least 50 before considering entry.',
  };
  return `Confidence: <strong>${conf}</strong> — Score <strong>${score}/100</strong>.<br>${map[conf] || map['Very Weak']}<small>Confidence ranges: 0-34 = Avoid | 35-49 = Weak | 50-69 = Moderate | 70-100 = Strong</small>`;
}

function dTGRR(rr, num) {
  const val = parseFloat(rr);
  const quality = val >= 2 ? 'Good' : val >= 1.5 ? 'Acceptable' : val >= 1 ? 'Break-even level' : 'Poor';
  return `Risk/Reward for TP${num}: <strong>1:${rr}</strong> — for every 1 pip you risk on the stop loss, you could earn <strong>${rr} pips</strong> at this target.<br>Quality: <strong>${quality}</strong>.<small>Professional traders generally look for R:R 1:2 or better. Below 1:1 is usually not worth taking.</small>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   TRADE GUIDANCE
═══════════════════════════════════════════════════════════════════════════ */

function _pipSize(asset) {
  if (!asset) return null;
  const a = asset.toUpperCase();
  if (!a.includes('/')) return null;       // stock
  return a.includes('JPY') ? 0.01 : 0.0001;
}

function _fmtPrice(val, asset) {
  if (!asset) return val.toFixed(2);
  const a = asset.toUpperCase();
  if (a.includes('JPY'))    return val.toFixed(3);
  if (val >= 1000)          return val.toFixed(2);
  if (val >= 100)           return val.toFixed(2);
  if (val >= 10)            return val.toFixed(3);
  if (val >= 1)             return val.toFixed(4);
  return val.toFixed(5);
}

function _distStr(from, to, asset) {
  const ps   = _pipSize(asset);
  const diff = to - from;
  const sign = diff >= 0 ? '+' : '';
  if (ps) {
    const pips = Math.round(diff / ps);
    return `${sign}${pips} pips`;
  }
  const pct = ((diff / Math.abs(from)) * 100).toFixed(1);
  const d   = diff.toFixed(2);
  return `${sign}$${d} (${sign}${pct}%)`;
}

function calcTradeGuide(d) {
  const price  = parseFloat(d.last_price);
  const daily  = d.timeframes.daily;
  const hourly = d.timeframes.hourly;
  const bias   = d.bias;
  const score  = d.score;
  const asset  = d.asset;
  const atr    = price * (daily.volatility_atr_pct / 100);
  const buf    = Math.max(atr * 0.28, price * 0.0003);

  /* Probability: bias direction always gets >= 50%, score strength pushes it toward 100%.
     Formula: biasDir% = 50 + score/2  (score=0 → 50/50, score=100 → 100/0) */
  const biasDirProb = 50 + Math.round(score / 2);
  const oppDirProb  = 100 - biasDirProb;
  let upProb, downProb;
  if      (bias === 'up')   { upProb = biasDirProb; downProb = oppDirProb; }
  else if (bias === 'down') { downProb = biasDirProb; upProb = oppDirProb; }
  else                      { upProb = 50; downProb = 50; }

  const conf = score >= 70 ? 'Strong' : score >= 50 ? 'Moderate' : score >= 35 ? 'Weak' : 'Very Weak';
  const confCls = conf.toLowerCase().replace(' ', '-');
  const advice = score >= 70 ? 'Strong alignment. Standard position size applies.'
               : score >= 50 ? 'Moderate alignment. Consider a smaller position.'
               : score >= 35 ? 'Weak signal. Paper trade or wait for better setup.'
               :               'Conflicting signals. No trade recommended now.';

  if (bias !== 'up' && bias !== 'down') {
    return { signal: 'neutral', price, upProb, downProb, conf, confCls, advice, score };
  }

  let sl, tp1, tp2;
  if (bias === 'up') {
    sl  = parseFloat(hourly.support)    - buf;
    tp1 = parseFloat(hourly.resistance);
    tp2 = parseFloat(daily.resistance);
    if (sl  >= price) sl  = price - atr * 1.5;
    if (tp1 <= price) tp1 = price + atr * 2.0;
    if (tp2 <= tp1)   tp2 = tp1   + atr * 2.0;
  } else {
    sl  = parseFloat(hourly.resistance) + buf;
    tp1 = parseFloat(hourly.support);
    tp2 = parseFloat(daily.support);
    if (sl  <= price) sl  = price + atr * 1.5;
    if (tp1 >= price) tp1 = price - atr * 2.0;
    if (tp2 >= tp1)   tp2 = tp1   - atr * 2.0;
  }

  const risk    = Math.abs(price - sl);
  const rr1     = risk > 0 ? Math.abs(tp1 - price) / risk : 0;
  const rr2     = risk > 0 ? Math.abs(tp2 - price) / risk : 0;

  return { signal: bias, price, sl, tp1, tp2, rr1, rr2, upProb, downProb, conf, confCls, advice, score, asset };
}

function renderTradeGuide(d) {
  const g = calcTradeGuide(d);

  /* Badge + tooltip */
  const badge = el('tg-signal-badge');
  if (g.signal === 'up')        { badge.textContent = '↑ BUY Signal';  badge.className = 'tg-signal-badge up'; }
  else if (g.signal === 'down') { badge.textContent = '↓ SELL Signal'; badge.className = 'tg-signal-badge down'; }
  else                          { badge.textContent = '→ Wait';        badge.className = 'tg-signal-badge neutral'; }
  setTip(badge, 'Trade Signal', dTGSignal(g.signal, g.score));

  /* Probability bar + tooltips */
  el('tg-fill-up').style.width    = `${g.upProb}%`;
  el('tg-fill-down').style.width  = `${g.downProb}%`;
  el('tg-lbl-up').textContent     = `${g.upProb}% Bullish`;
  el('tg-lbl-down').textContent   = `${g.downProb}% Bearish`;
  const probTipBody = dTGProbability(g.upProb, g.downProb, g.score);
  setTip(el('tg-fill-up').closest('.tg-prob-track'), 'Signal Probability', probTipBody);
  setTip(el('tg-lbl-up').closest('.tg-prob-labels'),  'Signal Probability', probTipBody);

  /* Confidence box + tooltip */
  const cv = el('tg-conf-value');
  cv.textContent = g.conf;
  cv.className   = `tg-conf-value ${g.confCls}`;
  el('tg-conf-score').textContent  = `${g.score} / 100`;
  el('tg-conf-advice').textContent = g.advice;
  const confBox = cv.closest('.tg-conf-box');
  if (confBox) setTip(confBox, 'Confidence Rating', dTGConfidence(g.conf, g.score));

  if (g.signal === 'neutral') {
    el('tg-levels').innerHTML = `<div class="tg-neutral-msg">Signals are conflicting. Wait for a clearer directional setup before entering a trade.</div>`;
    return;
  }

  /* Level rows with individual tooltips */
  const fp     = v => _fmtPrice(v, g.asset);
  const ds     = (a, b) => _distStr(a, b, g.asset);
  const isBuy  = g.signal === 'up';

  const slTip    = mkTip('Stop Loss',     dTGStopLoss(fp(g.sl), ds(g.price, g.sl), isBuy));
  const entryTip = mkTip('Entry Zone',    dTGEntry(fp(g.price)));
  const tp1Tip   = mkTip('Take Profit 1', dTGTP(1, fp(g.tp1), ds(g.price, g.tp1), `1:${g.rr1.toFixed(1)}`, true));
  const tp2Tip   = mkTip('Take Profit 2', dTGTP(2, fp(g.tp2), ds(g.price, g.tp2), `1:${g.rr2.toFixed(1)}`, false));
  const rr1Tip   = mkTip('Risk/Reward TP1', dTGRR(g.rr1.toFixed(1), 1));
  const rr2Tip   = mkTip('Risk/Reward TP2', dTGRR(g.rr2.toFixed(1), 2));

  const rrCell = (v, tipId) =>
    `<span data-tip="${tipId}" class="tg-rr-wrap">R:R 1:${v.toFixed(1)}</span>`;

  let rows;
  if (isBuy) {
    rows = [
      { tip: tp2Tip,   cls: 'tg-row-tp2',   label: '↑ Take Profit 2', price: g.tp2,  dist: ds(g.price, g.tp2), extra: rrCell(g.rr2, rr2Tip) },
      { tip: tp1Tip,   cls: 'tg-row-tp1',   label: '↑ Take Profit 1', price: g.tp1,  dist: ds(g.price, g.tp1), extra: rrCell(g.rr1, rr1Tip) },
      { tip: entryTip, cls: 'tg-row-entry', label: 'Entry Zone',       price: g.price, dist: 'current price',   extra: '' },
      { tip: slTip,    cls: 'tg-row-sl',    label: '↓ Stop Loss',      price: g.sl,   dist: ds(g.price, g.sl),  extra: '' },
    ];
  } else {
    rows = [
      { tip: slTip,    cls: 'tg-row-sl',    label: '↑ Stop Loss',      price: g.sl,   dist: ds(g.price, g.sl),  extra: '' },
      { tip: entryTip, cls: 'tg-row-entry', label: 'Entry Zone',        price: g.price, dist: 'current price',   extra: '' },
      { tip: tp1Tip,   cls: 'tg-row-tp1',   label: '↓ Take Profit 1',  price: g.tp1,  dist: ds(g.price, g.tp1), extra: rrCell(g.rr1, rr1Tip) },
      { tip: tp2Tip,   cls: 'tg-row-tp2',   label: '↓ Take Profit 2',  price: g.tp2,  dist: ds(g.price, g.tp2), extra: rrCell(g.rr2, rr2Tip) },
    ];
  }

  el('tg-levels').innerHTML = `
    <table class="tg-table">
      <thead><tr><th>Level</th><th>Price</th><th>Distance</th><th>Risk/Reward</th></tr></thead>
      <tbody>${rows.map(r =>
        `<tr class="${r.cls}" data-tip="${r.tip}">
          <td>${r.label}</td>
          <td><strong>${fp(r.price)}</strong></td>
          <td>${r.dist}</td>
          <td>${r.extra}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  const tab = new URLSearchParams(window.location.search).get('tab');
  switchTab(tab === 'stock' ? 'stock' : 'forex');
  buildTZSelector();
});

/* ═══════════════════════════════════════════════════════════════════════════
   TAB / FORM HELPERS
═══════════════════════════════════════════════════════════════════════════ */
function switchTab(tab) {
  currentTab = tab;
  el('tab-forex').classList.toggle('active', tab === 'forex');
  el('tab-stock').classList.toggle('active', tab === 'stock');
  el('form-forex').classList.toggle('hidden', tab !== 'forex');
  el('form-stock').classList.toggle('hidden', tab !== 'stock');
  el('results').classList.add('hidden');
  hideError();
}

function setForexPair(base, quote) {
  el('fx-base').value  = base;
  el('fx-quote').value = quote;
}

function setStock(sym, display) {
  el('stock-symbol-hidden').value  = sym;
  el('stock-search-input').value   = display || sym;
  closeStockDropdown();
}

/* ═══════════════════════════════════════════════════════════════════════════
   ANALYZE
═══════════════════════════════════════════════════════════════════════════ */
async function analyzeForex() {
  const base  = el('fx-base').value;
  const quote = el('fx-quote').value;
  if (base === quote) { showError('Base and quote currency must be different.'); return; }
  await runAnalysis({ asset_type: 'forex', symbol: base, quote }, 'fx');
}

async function analyzeStock() {
  const sym = (el('stock-symbol-hidden')?.value || el('stock-search-input')?.value || '').trim().toUpperCase();
  if (!sym) { showError('Please search and select a company, or type a ticker symbol.'); return; }
  await runAnalysis({ asset_type: 'stock', symbol: sym }, 'st');
}

async function runAnalysis(payload, prefix) {
  setLoading(prefix, true);
  hideError();
  el('results').classList.add('hidden');
  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    renderResults(await res.json());
  } catch (e) {
    showError(e.message || 'Request failed. Check the console for details.');
  } finally {
    setLoading(prefix, false);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   RENDER RESULTS
═══════════════════════════════════════════════════════════════════════════ */
function renderResults(d) {
  resetTips();
  _lastData = d;

  const daily  = d.timeframes.daily;
  const hourly = d.timeframes.hourly;
  const b      = d.breakdown;

  /* ── Header card ────────────────────────────────────────────────────── */
  el('r-asset').textContent = d.asset;
  el('r-price').textContent = `Price: ${d.last_price}`;
  el('r-meta').textContent  = `${d.asset_type.toUpperCase()} · Generated ${fmtTime(d.generated_at_utc)}`;

  const biasEl = el('r-bias-badge');
  biasEl.textContent = biasTxt(d.bias);
  biasEl.className   = `bias-badge ${d.bias}`;
  setTip(biasEl, 'Overall Market Bias', dBias(d.bias, d.score));

  /* ── Score gauge ────────────────────────────────────────────────────── */
  el('gauge-arc').style.strokeDashoffset = 267 * (1 - d.score / 100);
  el('gauge-num').textContent = d.score;
  setTip(el('gauge-card'), 'Alignment Score', dGauge(d.score));

  /* ── Key Indicators (quick stats) ───────────────────────────────────── */
  setVal('qs-drsi',  daily.rsi,                                            rsiClass(daily.rsi));
  setVal('qs-hrsi',  hourly.rsi,                                           rsiClass(hourly.rsi));
  setVal('qs-dtrend',trendTxt(daily.trend),                                daily.trend);
  setVal('qs-dmacd', daily.macd_above_signal ? '↑ Bullish' : '↓ Bearish', daily.macd_above_signal ? 'up' : 'down');
  setVal('qs-atr',   `${daily.volatility_atr_pct}%`,                      'neutral');
  setVal('qs-sent',  capFirst(d.sentiment?.label || 'neutral'),            d.sentiment?.label || 'neutral');

  rowTip('qs-drsi',   'Daily RSI (14)',   dRSI(daily.rsi,   'Daily'));
  rowTip('qs-hrsi',   'Hourly RSI (14)',  dRSI(hourly.rsi,  'Hourly'));
  rowTip('qs-dtrend', 'Daily Trend',      dTrend(daily.trend, 'Daily'));
  rowTip('qs-dmacd',  'Daily MACD',       dMACD(daily.macd_above_signal, 'Daily'));
  rowTip('qs-atr',    'Volatility ATR%',  dATR(daily.volatility_atr_pct, 'Daily'));
  rowTip('qs-sent',   'News Sentiment',   dSentLabel(d.sentiment?.label, d.sentiment?.score ?? 0));

  /* ── AI Summary ─────────────────────────────────────────────────────── */
  el('ai-summary-text').textContent   = d.ai_summary?.text || 'No summary available.';
  el('ai-provider-badge').textContent = d.ai_summary?.provider || 'Unknown';

  /* ── Technical tables ───────────────────────────────────────────────── */
  renderTechTable('daily-table',  daily,  'Daily');
  renderTechTable('hourly-table', hourly, 'Hourly');

  const dDir = el('daily-dir-badge');
  dDir.textContent = capFirst(daily.direction);
  dDir.className   = `dir-badge ${daily.direction}`;

  const hDir = el('hourly-dir-badge');
  hDir.textContent = capFirst(hourly.direction);
  hDir.className   = `dir-badge ${hourly.direction}`;

  /* Support / Resistance */
  el('d-support').textContent    = daily.support;
  el('d-resistance').textContent = daily.resistance;
  el('h-support').textContent    = hourly.support;
  el('h-resistance').textContent = hourly.resistance;

  setTip(el('d-support').closest('.level-box'),    'Daily Support',      dSupport(daily.support));
  setTip(el('d-resistance').closest('.level-box'), 'Daily Resistance',   dResistance(daily.resistance));
  setTip(el('h-support').closest('.level-box'),    'Hourly Support',     dHSupport(hourly.support));
  setTip(el('h-resistance').closest('.level-box'), 'Hourly Resistance',  dHResistance(hourly.resistance));

  /* ── Score Breakdown ────────────────────────────────────────────────── */
  renderBreakdown(b, d.asset_type);

  /* ── Intermarket ────────────────────────────────────────────────────── */
  if (d.asset_type === 'forex' && d.intermarket) {
    el('inter-sent-row').classList.remove('hidden');
    el('intermarket-card').classList.remove('hidden');
    const dollar   = d.intermarket.dollar || 'unknown';
    const dollarEl = el('inter-dollar');
    dollarEl.textContent = capFirst(dollar);
    dollarEl.className   = `inter-dollar ${dollar === 'strengthening' ? 'down' : dollar === 'weakening' ? 'up' : 'neutral'}`;
    setTip(dollarEl, 'USD Dollar Strength', dDollar(dollar));

    setVal('inter-eurusd', trendTxt(d.intermarket.eurusd_trend), d.intermarket.eurusd_trend);
    setVal('inter-usdjpy', trendTxt(d.intermarket.usdjpy_trend), d.intermarket.usdjpy_trend);
    rowTip('inter-eurusd', 'EUR/USD Daily Trend', dEURUSD(d.intermarket.eurusd_trend));
    rowTip('inter-usdjpy', 'USD/JPY Daily Trend', dUSDJPY(d.intermarket.usdjpy_trend));
  } else {
    el('intermarket-card').classList.add('hidden');
  }

  /* ── Sentiment ──────────────────────────────────────────────────────── */
  const sentEl = el('sent-label');
  const sentLbl = d.sentiment?.label || 'neutral';
  sentEl.textContent = capFirst(sentLbl);
  sentEl.className   = `sent-score ${sentLbl}`;
  setTip(sentEl, 'Sentiment Label', dSentimentLabel(sentLbl));

  setVal('sent-score',    String(d.sentiment?.score ?? 0),         sentLbl);
  setVal('sent-articles', String(d.sentiment?.article_count ?? 0), 'neutral');
  rowTip('sent-score',    'Sentiment Score',    dSentScore(d.sentiment?.score ?? 0));
  rowTip('sent-articles', 'Articles Scanned',   dArticles(d.sentiment?.article_count ?? 0));

  /* ── Economic Events ────────────────────────────────────────────────── */
  renderEvents(d.upcoming_events || []);

  /* ── Provider footer ────────────────────────────────────────────────── */
  el('pf-data').textContent = `${d.providers_used?.hourly_data || 'N/A'} (1h), ${d.providers_used?.daily_data || 'N/A'} (1d)`;
  el('pf-ai').textContent   = d.ai_summary?.provider || 'N/A';
  el('pf-time').textContent = fmtTime(d.generated_at_utc);

  /* ── Show / hide stock-only cards ──────────────────────────────────────── */
  const isStock = d.asset_type === 'stock';
  document.querySelectorAll('.stock-only').forEach(el2 => {
    el2.style.display = isStock ? (el2.classList.contains('two-col') ? 'grid' : 'block') : 'none';
  });

  renderTradeGuide(d);
  renderKeySignal(d);
  renderConflictBadges(d);
  renderYieldDiff(d);
  renderHeadlines(d);
  renderCOT(d);
  renderVolatilityRegime(d);

  /* ── Stock-specific renders ─────────────────────────────────────────────── */
  if (isStock) {
    renderEarningsProximityWarning(d);
    renderStockFundamentals(d);
    renderStockHistory(d);
    renderStockEarnings(d);
    renderStockAnalyst(d);
    renderStockInsider(d);
    renderShortInterest(d);
    renderInstitutionalOwnership(d);
    renderOptionsSentiment(d);
  }

  const resultsEl = el('results');
  if (resultsEl) {
    resultsEl.classList.remove('hidden');
    // Only scroll on the research page (not inside a dashboard modal)
    if (!document.getElementById('view-modal')) {
      resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   TECHNICAL TABLE  (daily + hourly, same structure)
═══════════════════════════════════════════════════════════════════════════ */
function renderTechTable(tbodyId, tf, label) {
  const rows = [
    {
      name: 'RSI (14)',
      val:  tf.rsi,
      cls:  rsiClass(tf.rsi),
      sig:  tf.rsi > 70 ? '↓ Overbought' : tf.rsi < 30 ? '↑ Oversold' : '→ Neutral',
      tip:  dRSI(tf.rsi, label),
    },
    {
      name: 'MACD vs Signal',
      val:  tf.macd_above_signal ? 'Above' : 'Below',
      cls:  tf.macd_above_signal ? 'up' : 'down',
      sig:  tf.macd_above_signal ? '↑ Bullish' : '↓ Bearish',
      tip:  dMACD(tf.macd_above_signal, label),
    },
    {
      name: 'MA20 vs MA50',
      val:  tf.ma20_above_ma50 ? 'Above' : 'Below',
      cls:  tf.ma20_above_ma50 ? 'up' : 'down',
      sig:  tf.ma20_above_ma50 ? '↑ Bullish' : '↓ Bearish',
      tip:  dMA(tf.ma20_above_ma50, label),
    },
    {
      name: 'Trend (vs MA50)',
      val:  capFirst(tf.trend),
      cls:  tf.trend,
      sig:  trendTxt(tf.trend),
      tip:  dTrend(tf.trend, label),
    },
    {
      name: 'ATR Volatility',
      val:  `${tf.volatility_atr_pct}%`,
      cls:  'neutral',
      sig:  tf.volatility_atr_pct > 1 ? 'High' : tf.volatility_atr_pct > 0.4 ? 'Medium' : 'Low',
      tip:  dATR(tf.volatility_atr_pct, label),
    },
  ];

  document.getElementById(tbodyId).innerHTML = rows.map(r => {
    const id = mkTip(`${label} ${r.name}`, r.tip);
    return `<tr data-tip="${id}">
      <td>${r.name}</td>
      <td class="td-${r.cls}">${r.val}</td>
      <td class="td-${r.cls}">${r.sig}</td>
    </tr>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   SCORE BREAKDOWN CARDS
═══════════════════════════════════════════════════════════════════════════ */
function renderBreakdown(b, assetType) {
  let items;

  if (assetType === 'stock') {
    const fund = b.fundamental               || {};
    const ana  = b.analyst_consensus         || {};
    const inst = b.institutional_ownership   || {};
    const hist = b.historical_trend          || {};
    const earn = b.earnings_quality          || {};

    items = [
      {
        name: 'Daily\nTechnical',
        pts:  b.daily_technical.points, max: 22, dir: b.daily_technical.direction, note: null,
        tip:  dScoreCard('Daily Technical', b.daily_technical.points, 22, b.daily_technical.direction,
                'Scored from 4 daily chart indicators: RSI, MACD, Moving Averages, and Trend. Full 22 pts when all 4 strongly agree.'),
      },
      {
        name: 'Hourly\nTechnical',
        pts:  b.hourly_technical.points, max: 18, dir: b.hourly_technical.direction, note: null,
        tip:  dScoreCard('Hourly Technical', b.hourly_technical.points, 18, b.hourly_technical.direction,
                'Scored from 4 hourly chart indicators. Full 18 pts when all short-term signals strongly agree.'),
      },
      {
        name: 'Fundamental\nScore',
        pts:  fund.points || 0, max: 14, dir: fund.direction || 'neutral',
        note: fund.available ? (fund.direction === 'up' ? 'Bullish' : fund.direction === 'down' ? 'Bearish' : 'Neutral') : 'No Data',
        tip:  dScoreCard('Fundamental Score', fund.points || 0, 14, fund.direction || 'neutral',
                fund.available
                  ? `P/E: ${fund.pe_ratio != null ? fund.pe_ratio.toFixed(1) + 'x' : 'N/A'} | Revenue Growth: ${fund.revenue_growth != null ? (fund.revenue_growth*100).toFixed(1)+'%' : 'N/A'} | Profit Margin: ${fund.profit_margin != null ? (fund.profit_margin*100).toFixed(1)+'%' : 'N/A'}. Full 14 pts for low valuation + strong growth + high margin.`
                  : 'Fundamental data unavailable. Requires Alpha Vantage API key.'),
      },
      {
        name: 'Analyst\nConsensus',
        pts:  ana.points || 0, max: 11, dir: ana.direction || 'neutral',
        note: ana.available ? (ana.consensus || 'No Data') : 'No Data',
        tip:  dScoreCard('Analyst Consensus', ana.points || 0, 11, ana.direction || 'neutral',
                ana.available
                  ? `Consensus: ${ana.consensus} | Upside to mean target: ${ana.upside_pct != null ? ana.upside_pct.toFixed(1) + '%' : 'N/A'}. Full 11 pts when majority rate Strong Buy.`
                  : 'Analyst data unavailable. Requires Finnhub API key.'),
      },
      {
        name: 'Institutional\nOwnership',
        pts:  inst.points || 0, max: 8, dir: inst.direction || 'neutral',
        note: inst.available ? capFirst(inst.signal || 'neutral') : 'No Data',
        tip:  dScoreCard('Institutional Ownership', inst.points || 0, 8, inst.direction || 'neutral',
                inst.available
                  ? `${inst.buy_count || 0} major holders accumulating vs ${inst.sell_count || 0} distributing. Full 8 pts when smart money is clearly accumulating.`
                  : 'Institutional data unavailable. Requires Finnhub API key.'),
      },
      {
        name: 'News\nSentiment',
        pts:  b.sentiment.points, max: 9, dir: b.sentiment.direction, note: b.sentiment.label,
        tip:  dScoreCard('News Sentiment', b.sentiment.points, 9, b.sentiment.direction,
                `Based on ${b.sentiment.articles} scanned news articles. Full 9 pts when sentiment is strongly bullish or bearish.`),
      },
      {
        name: 'Historical\nvs SPY',
        pts:  hist.points || 0, max: 9, dir: hist.direction || 'neutral',
        note: hist.vs_spy_1y != null ? `${hist.vs_spy_1y > 0 ? '+' : ''}${hist.vs_spy_1y.toFixed(0)}% vs SPY` : 'N/A',
        tip:  dScoreCard('Historical vs SPY', hist.points || 0, 9, hist.direction || 'neutral',
                hist.available
                  ? `1Y return: ${hist.return_1y != null ? hist.return_1y.toFixed(1)+'%' : 'N/A'} | vs SPY: ${hist.vs_spy_1y != null ? (hist.vs_spy_1y > 0 ? '+' : '') + hist.vs_spy_1y.toFixed(1)+'%' : 'N/A'}. Full 9 pts for strongly outperforming SPY over 1 year.`
                  : 'Historical data unavailable.'),
      },
      {
        name: 'Earnings\nQuality',
        pts:  earn.points || 0, max: 9, dir: earn.direction || 'neutral',
        note: earn.available ? `${earn.beats}/${earn.beats + earn.misses} beats` : 'No Data',
        tip:  dScoreCard('Earnings Quality', earn.points || 0, 9, earn.direction || 'neutral',
                earn.available
                  ? `Beat ${earn.beats} of ${earn.beats + earn.misses} estimates in the last 4 quarters. Full 9 pts for 4/4 beats.`
                  : 'Earnings data unavailable. Requires Finnhub API key.'),
      },
    ];
  } else {
    const inst = b.institutional || {};
    items = [
      {
        name: 'Daily\nTechnical',
        pts:  b.daily_technical.points, max: b.daily_technical.max, dir: b.daily_technical.direction, note: null,
        tip:  dScoreCard('Daily Technical', b.daily_technical.points, b.daily_technical.max, b.daily_technical.direction,
                'Scored from 4 daily chart indicators: RSI, MACD, Moving Averages, and Trend. Full 25 points when all 4 strongly agree in the same direction.'),
      },
      {
        name: 'Hourly\nTechnical',
        pts:  b.hourly_technical.points, max: b.hourly_technical.max, dir: b.hourly_technical.direction, note: null,
        tip:  dScoreCard('Hourly Technical', b.hourly_technical.points, b.hourly_technical.max, b.hourly_technical.direction,
                'Scored from 4 hourly chart indicators. Represents short-term momentum. Full 20 points when all hourly signals strongly agree.'),
      },
      {
        name: 'Intermarket\n(USD)',
        pts:  b.intermarket.points, max: b.intermarket.max, dir: b.intermarket.direction, note: b.intermarket.dollar,
        tip:  dScoreCard('Intermarket (USD)', b.intermarket.points, b.intermarket.max, b.intermarket.direction,
                'Measures US Dollar strength using EUR/USD and USD/JPY trends. Full 18 points when both pairs confirm Dollar direction.'),
      },
      {
        name: 'Institutional\n(COT)',
        pts:  inst.points || 0, max: inst.max || 15, dir: inst.direction || 'neutral',
        note: inst.available ? (inst.direction === 'up' ? 'Net Long' : inst.direction === 'down' ? 'Net Short' : 'Neutral') : 'No Data',
        tip:  dScoreCard('Institutional COT', inst.points || 0, inst.max || 15, inst.direction || 'neutral',
                `CFTC COT data: ${inst.label || 'No Data'}. Weekly trend: ${inst.weeks_trend || 'unknown'}. Full 15 points when institutions are clearly positioned in one direction.`),
      },
      {
        name: 'News\nSentiment',
        pts:  b.sentiment.points, max: b.sentiment.max, dir: b.sentiment.direction, note: b.sentiment.label,
        tip:  dScoreCard('News Sentiment', b.sentiment.points, b.sentiment.max, b.sentiment.direction,
                `Based on ${b.sentiment.articles} scanned news articles. Score of 0 means neutral or no articles found. Full 12 points when sentiment is strongly bullish or bearish.`),
      },
      {
        name: 'Event\nClarity',
        pts:  b.event_clarity.points, max: b.event_clarity.max, dir: 'up',
        note: `${b.event_clarity.high_impact} high-impact`,
        tip:  dScoreCard('Event Clarity', b.event_clarity.points, b.event_clarity.max, 'clarity',
                `${b.event_clarity.high_impact} high-impact economic events are upcoming. Each reduces this score because major news can instantly override all technical signals.`),
      },
    ];
  }

  el('breakdown-grid').innerHTML = items.map(item => {
    const id  = mkTip(item.name.replace('\n', ' '), item.tip);
    const pct = item.pts / item.max;
    const cls = pct >= 0.6 ? 'up' : pct >= 0.3 ? 'neutral' : 'down';
    const label = item.note ? capFirst(item.note) : capFirst(item.dir);
    return `<div class="bd-card" data-tip="${id}">
      <div class="bd-name">${item.name.replace('\n', '<br>')}</div>
      <div class="bd-pts ${cls}">${item.pts.toFixed(0)}</div>
      <div class="bd-max">/ ${item.max} pts</div>
      <div class="bd-dir ${item.dir}">${label}</div>
    </div>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   ECONOMIC EVENTS TABLE
═══════════════════════════════════════════════════════════════════════════ */
function renderEvents(events) {
  el('events-count').textContent = `${events.length} upcoming`;
  if (!events.length) {
    el('events-table').innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:1.5rem">No upcoming events found</td></tr>`;
    return;
  }
  el('events-table').innerHTML = events.map(ev => {
    const id  = mkTip(ev.event || 'Economic Event', dEvent(ev));
    const cls = `impact-${ev.impact}`;
    const q   = encodeURIComponent(`${ev.event || ''} ${ev.country || ''} economic`);
    const newsUrl = `https://news.google.com/search?q=${q}`;
    return `<tr data-tip="${id}">
      <td><a href="${newsUrl}" target="_blank" rel="noopener noreferrer" class="event-link">${ev.event || 'Unknown'}</a></td>
      <td>${ev.country || 'N/A'}</td>
      <td class="${cls}">${capFirst(ev.impact)}</td>
      <td style="white-space:nowrap">${fmtInTZ(ev.time)}</td>
      <td>${ev.estimate ?? 'N/A'}</td>
      <td>${ev.actual ?? 'N/A'}</td>
    </tr>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   LOADING / ERROR
═══════════════════════════════════════════════════════════════════════════ */
function setLoading(prefix, on) {
  el(`${prefix}-btn-text`).classList.toggle('hidden', on);
  el(`${prefix}-spinner`).classList.toggle('hidden', !on);
  const btn = el(`${prefix}-btn-text`).closest('button');
  if (btn) btn.disabled = on;
}

function showError(msg) {
  el('error-text').textContent = msg;
  el('error-banner').classList.remove('hidden');
}
function hideError() { el('error-banner').classList.add('hidden'); }

/* ═══════════════════════════════════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════════════════════════════════ */
function el(id)        { return document.getElementById(id); }
function capFirst(s)   { return s ? s.charAt(0).toUpperCase() + s.slice(1) : 'N/A'; }
function biasTxt(bias) { return bias === 'up' ? '↑ BULLISH' : bias === 'down' ? '↓ BEARISH' : '→ UNCLEAR'; }
function trendTxt(t)   { return t === 'up' ? '↑ Up' : t === 'down' ? '↓ Down' : '→ Neutral'; }
function rsiClass(v)   { return v > 70 ? 'down' : v < 30 ? 'up' : 'neutral'; }

function setVal(id, text, cls) {
  const e = el(id);
  e.textContent = text;
  e.className   = `qs-val ${cls}`;
}

/* Convert any UTC string (ISO or "YYYY-MM-DD HH:MM:SS") to the selected timezone */
function fmtInTZ(raw) {
  if (!raw) return 'N/A';
  try {
    const s   = raw.includes('T') ? raw : raw.replace(' ', 'T') + 'Z';
    const d   = new Date(s);
    if (isNaN(d.getTime())) return raw;
    return d.toLocaleString('en-GB', {
      timeZone: selectedTZ,
      day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  } catch { return raw; }
}

function fmtTime(iso) { return fmtInTZ(iso); }

function _tzOffset(tz) {
  try {
    const now  = new Date();
    const base = new Date(now.toLocaleString('en-US', { timeZone: 'UTC' }));
    const local = new Date(now.toLocaleString('en-US', { timeZone: tz }));
    const diff  = Math.round((local - base) / 60000);
    const sign  = diff >= 0 ? '+' : '-';
    const h     = String(Math.floor(Math.abs(diff) / 60)).padStart(2, '0');
    const m     = String(Math.abs(diff) % 60).padStart(2, '0');
    return `UTC${sign}${h}:${m}`;
  } catch { return ''; }
}

/* ═══════════════════════════════════════════════════════════════════════════
   TIMEZONE PICKER
═══════════════════════════════════════════════════════════════════════════ */
function buildTZSelector() {
  _renderTZList('');
  _updateTZLabel();
}

function _renderTZList(filter) {
  const list = el('tz-list');
  if (!list) return;
  const q = filter.toLowerCase().replace(/[_/]/g, ' ');
  const hits = ALL_TZ.filter(tz => {
    const name = tz.toLowerCase().replace(/[_/]/g, ' ');
    return name.includes(q);
  });
  list.innerHTML = hits.slice(0, 80).map(tz => {
    const city    = tz.split('/').pop().replace(/_/g, ' ');
    const region  = tz.includes('/') ? tz.split('/')[0] : '';
    const offset  = _tzOffset(tz);
    const active  = tz === selectedTZ ? ' active' : '';
    return `<div class="tz-item${active}" onclick="selectTZ('${tz}')">
      ${city}<span class="tz-item-offset">${offset}</span>
      ${region ? `<span class="tz-item-offset"> · ${region.replace(/_/g,' ')}</span>` : ''}
    </div>`;
  }).join('') || `<div class="tz-item" style="pointer-events:none">No results</div>`;
}

function _updateTZLabel() {
  const lbl = el('tz-label');
  if (!lbl) return;
  try {
    const abbr = new Intl.DateTimeFormat('en', { timeZone: selectedTZ, timeZoneName: 'short' })
      .formatToParts(new Date()).find(p => p.type === 'timeZoneName')?.value
      || selectedTZ.split('/').pop();
    lbl.textContent = abbr;
  } catch { lbl.textContent = selectedTZ.split('/').pop(); }
}

function toggleTZPanel() {
  const panel = el('tz-panel');
  if (!panel) return;
  const opening = !panel.classList.contains('open');
  panel.classList.toggle('open', opening);
  if (opening) {
    const inp = el('tz-search-input');
    if (inp) { inp.value = ''; _renderTZList(''); setTimeout(() => inp.focus(), 40); }
  }
}

function selectTZ(tz) {
  selectedTZ = tz;
  _updateTZLabel();
  el('tz-panel')?.classList.remove('open');
  _renderTZList('');
  if (_lastData) _rerenderTimes();
}

function _rerenderTimes() {
  if (!_lastData) return;
  renderEvents(_lastData.upcoming_events || []);
  el('r-meta').textContent = `${_lastData.asset_type.toUpperCase()} · Generated ${fmtInTZ(_lastData.generated_at_utc)}`;
  el('pf-time').textContent = fmtInTZ(_lastData.generated_at_utc);
}

/* Close picker or stock dropdown on outside click */
document.addEventListener('click', e => {
  if (!e.target.closest('#tz-picker'))            el('tz-panel')?.classList.remove('open');
  if (!e.target.closest('.stock-search-container')) closeStockDropdown();
});

/* ═══════════════════════════════════════════════════════════════════════════
   TOOLTIP DESCRIPTIONS -- NEW FEATURES
═══════════════════════════════════════════════════════════════════════════ */

function dKeySignal(text, dir) {
  const dirLabel = dir === 'up' ? 'BULLISH' : dir === 'down' ? 'BEARISH' : 'NEUTRAL';
  return `The single most impactful signal detected across all analysis layers.<br><strong>Signal: ${text}</strong><br>Direction: <strong>${dirLabel}</strong><br>This is the indicator or condition that carries the most weight in the current setup.<small>Use this signal as your primary confirmation when deciding whether to trade.</small>`;
}

function dMainRisk(text) {
  return `The primary risk factor that could invalidate or disrupt the current bias.<br><strong>${text}</strong><br>Pay close attention to this before entering a position. If this risk materialises, exit or avoid the trade.<small>Risk management always takes priority over signal alignment.</small>`;
}

function dConflictBadge(tip) {
  return tip;
}

function dCOT(label, trend, net) {
  const abs = Math.abs(net);
  const str = abs > 100000 ? 'Extreme' : abs > 50000 ? 'Strong' : abs > 20000 ? 'Moderate' : 'Light';
  return `<strong>CFTC Commitments of Traders (COT)</strong> -- published weekly by US regulators.<br>Shows the net position of large institutional speculators (hedge funds, banks).<br>Current: <strong>${label}</strong><br>Trend: <strong>${capFirst(trend)}</strong><br>Positioning strength: <strong>${str}</strong> (${Math.abs(net).toLocaleString()} contracts).<small>COT data lags by ~3 days (released each Friday for the prior Tuesday). Extremes often precede reversals. Use as confluence, not as a standalone signal.</small>`;
}

function dRegime(regime, adx, expanding) {
  const map = {
    trending:     'Price is moving in a clear direction. Trend-following strategies work well. Moving average and MACD signals are more reliable.',
    ranging:      'Price is moving sideways between support and resistance. Trend signals are less reliable. RSI and mean-reversion setups work better.',
    transitioning:'Market is between regimes -- neither clearly trending nor ranging. Lower conviction for all signals. Wait for a breakout or a clear trend to form.',
  };
  return `Market Regime: <strong>${capFirst(regime)}</strong><br>ADX(14) = <strong>${adx}</strong> | Bollinger Bands <strong>${expanding ? 'expanding' : 'contracting'}</strong><br>${map[regime] || map.transitioning}<small>ADX above 25 + expanding BB = Trending | ADX below 20 + contracting BB = Ranging</small>`;
}

function dYieldDiff(us10y, de10y, diff, label) {
  return `<strong>US 10Y vs DE 10Y Bond Yield Spread</strong><br>US Treasury: <strong>${us10y}%</strong> | German Bund: <strong>${de10y}%</strong> | Spread: <strong>${diff > 0 ? '+' : ''}${diff}%</strong><br>${label}<br>A wider spread means USD is more attractive to investors, putting downward pressure on EUR/USD.<small>Yield differential is a long-term macro factor. Short-term moves are driven more by technicals.</small>`;
}

function dHeadline(title, source) {
  return `<strong>Recent News Headline</strong><br>"${title}"<br>Source: ${source || 'Unknown'}<small>Click the headline to open the full article in a new tab. News sentiment is scored by counting bullish and bearish keywords across all articles.</small>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   KEY SIGNAL CARD
═══════════════════════════════════════════════════════════════════════════ */
function renderKeySignal(d) {
  const ks    = d.key_signal || { text: 'No dominant signal', direction: 'neutral' };
  const risk  = d.main_risk  || 'Monitor economic calendar';
  const ksEl  = el('ks-text');
  const riskEl = el('ks-risk');
  if (!ksEl) return;

  ksEl.textContent  = ks.text;
  ksEl.className    = `ks-text ${ks.direction || 'neutral'}`;
  riskEl.textContent = risk;

  setTip(el('ks-signal-half'), 'Key Signal',  dKeySignal(ks.text, ks.direction));
  setTip(el('ks-risk-half'),   'Main Risk',   dMainRisk(risk));
}

/* ═══════════════════════════════════════════════════════════════════════════
   CONFLICT BADGES
═══════════════════════════════════════════════════════════════════════════ */
function renderConflictBadges(d) {
  const badgesEl = el('conflict-badges');
  if (!badgesEl) return;
  const badges = d.conflicts?.badges || [];
  if (!badges.length) { badgesEl.innerHTML = ''; return; }

  badgesEl.innerHTML = badges.map(b => {
    const id = mkTip(b.label, dConflictBadge(b.tip));
    return `<span class="conflict-badge ${b.type}" data-tip="${id}">! ${b.label}</span>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   YIELD DIFFERENTIAL
═══════════════════════════════════════════════════════════════════════════ */
function renderYieldDiff(d) {
  const ydSec = el('yield-diff-section');
  if (!ydSec) return;
  const yd = d.yield_diff;
  if (!yd || !yd.available) { ydSec.style.display = 'none'; return; }

  ydSec.style.display = 'block';
  const dirCls = yd.direction === 'up' ? 'up' : yd.direction === 'down' ? 'down' : 'neutral';
  setVal('yd-us10y', `${yd.us10y}%`, 'neutral');
  setVal('yd-de10y', `${yd.de10y}%`, 'neutral');
  setVal('yd-diff',  `${yd.differential > 0 ? '+' : ''}${yd.differential}%`, dirCls);
  el('yd-label').textContent = yd.label;

  setTip(ydSec, 'Yield Differential', dYieldDiff(yd.us10y, yd.de10y, yd.differential, yd.label));
}

/* ═══════════════════════════════════════════════════════════════════════════
   NEWS HEADLINES
═══════════════════════════════════════════════════════════════════════════ */
function renderHeadlines(d) {
  const sec  = el('sent-headlines');
  const list = el('sent-headlines-list');
  if (!sec || !list) return;
  const headlines = d.breakdown?.sentiment?.headlines || d.sentiment?.headlines || [];
  if (!headlines.length) { sec.style.display = 'none'; return; }

  sec.style.display = 'block';
  list.innerHTML = headlines.map(h => {
    const id = mkTip('Headline', dHeadline(h.title, h.source));
    return `<a href="${h.url}" target="_blank" rel="noopener noreferrer"
               class="sh-item" data-tip="${id}">
      ${h.title}
      ${h.source ? `<div class="sh-source">${h.source}</div>` : ''}
    </a>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   COT CARD
═══════════════════════════════════════════════════════════════════════════ */
function renderCOT(d) {
  const card = el('cot-card');
  if (!card) return;
  const cot = d.cot;
  if (!cot || !cot.available) { card.style.display = 'none'; return; }

  card.style.display = 'block';
  const dir    = cot.direction || 'neutral';
  const netEl  = el('cot-net');
  netEl.textContent = cot.label || 'No Data';
  netEl.className   = `cot-net ${dir}`;

  const badge = el('cot-dir-badge');
  badge.textContent = dir === 'up' ? 'Net Long' : dir === 'down' ? 'Net Short' : 'Neutral';
  badge.className   = `dir-badge ${dir}`;

  setVal('cot-net-val',  (cot.net > 0 ? '+' : '') + (cot.net || 0).toLocaleString(), dir);
  setVal('cot-trend',    capFirst(cot.weeks_trend || 'unknown'),
         cot.weeks_trend === 'increasing' ? 'up' : cot.weeks_trend === 'decreasing' ? 'down' : 'neutral');
  setVal('cot-currency', cot.currency || 'N/A', 'neutral');

  setTip(card, 'COT Institutional Positioning',
    dCOT(cot.label, cot.weeks_trend, cot.net));
}

/* ═══════════════════════════════════════════════════════════════════════════
   VOLATILITY REGIME CARD
═══════════════════════════════════════════════════════════════════════════ */
function renderVolatilityRegime(d) {
  const card = el('regime-card');
  if (!card) return;
  const r = d.volatility_regime;
  if (!r) { card.style.display = 'none'; return; }

  card.style.display = 'block';
  /* Collapse to 1-column if COT card is hidden */
  const row = el('cot-regime-row');
  if (row) {
    const cotHidden = (el('cot-card')?.style.display === 'none');
    row.style.gridTemplateColumns = cotHidden ? '1fr' : '';
  }
  const regime = r.regime || 'transitioning';

  const badge = el('regime-badge');
  badge.textContent = capFirst(regime);
  badge.className   = `regime-badge ${regime}`;

  el('regime-label').textContent = r.label || regime;

  const adxCls = r.adx > 25 ? 'up' : r.adx < 20 ? 'neutral' : 'neutral';
  setVal('regime-adx',      String(r.adx),             adxCls);
  setVal('regime-bb',       `${r.bb_width}%`,           'neutral');
  setVal('regime-expanding', r.bb_expanding ? 'Yes' : 'No',
         r.bb_expanding ? 'up' : 'down');

  setTip(card, 'Volatility Regime',
    dRegime(regime, r.adx, r.bb_expanding));
}

/* ═══════════════════════════════════════════════════════════════════════════
   STOCK SEARCH
═══════════════════════════════════════════════════════════════════════════ */
let _stockSearchTimer = null;
let _stockDropdownIdx = -1;

async function onStockSearch(q) {
  el('stock-symbol-hidden').value = '';
  clearTimeout(_stockSearchTimer);
  if (!q || q.trim().length < 1) { closeStockDropdown(); return; }
  _stockSearchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search-stock?q=${encodeURIComponent(q.trim())}`);
      if (!res.ok) return;
      const data = await res.json();
      renderStockDropdown(data.results || []);
    } catch { /* silent */ }
  }, 350);
}

function onStockSearchKey(e) {
  const dd    = el('stock-dropdown');
  const items = dd ? dd.querySelectorAll('.sd-item') : [];
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _stockDropdownIdx = Math.min(_stockDropdownIdx + 1, items.length - 1);
    items.forEach((item, i) => item.classList.toggle('active', i === _stockDropdownIdx));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _stockDropdownIdx = Math.max(_stockDropdownIdx - 1, 0);
    items.forEach((item, i) => item.classList.toggle('active', i === _stockDropdownIdx));
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (_stockDropdownIdx >= 0 && items[_stockDropdownIdx]) {
      items[_stockDropdownIdx].click();
    } else {
      const sym = e.target.value.trim().toUpperCase();
      if (sym) { setStock(sym, sym); analyzeStock(); }
    }
  } else if (e.key === 'Escape') {
    closeStockDropdown();
  }
}

function renderStockDropdown(results) {
  const dd = el('stock-dropdown');
  if (!dd) return;
  _stockDropdownIdx = -1;
  if (!results.length) { closeStockDropdown(); return; }
  dd.innerHTML = results.slice(0, 8).map(r =>
    `<div class="sd-item" onclick="selectStock('${r.symbol}','${r.symbol} - ${(r.name||'').replace(/'/g, '')}')">
      <span class="sd-symbol">${r.symbol}</span>
      <span class="sd-name">${r.name || ''}</span>
      <span class="sd-type">${r.type || ''}</span>
    </div>`
  ).join('');
  dd.classList.remove('hidden');
}

function selectStock(symbol, displayName) {
  el('stock-symbol-hidden').value = symbol;
  el('stock-search-input').value  = displayName;
  closeStockDropdown();
}

function closeStockDropdown() {
  const dd = el('stock-dropdown');
  if (dd) dd.classList.add('hidden');
  _stockDropdownIdx = -1;
}

/* ═══════════════════════════════════════════════════════════════════════════
   STOCK TOOLTIP DESCRIPTIONS
═══════════════════════════════════════════════════════════════════════════ */

function dFundamentals(fund) {
  const pe = fund.pe_ratio;
  const peNote = pe == null ? 'P/E data unavailable.' :
    pe < 12 ? `P/E of ${pe.toFixed(1)}x is very low -- potentially undervalued or in a declining sector.` :
    pe < 20 ? `P/E of ${pe.toFixed(1)}x is fair value -- reasonably priced relative to earnings.` :
    pe < 35 ? `P/E of ${pe.toFixed(1)}x is elevated -- growth premium baked in. Any earnings miss could trigger a sell-off.` :
    `P/E of ${pe.toFixed(1)}x is very high -- significant growth already priced in. High reversal risk.`;
  const rev = fund.revenue_growth;
  const revNote = rev == null ? '' : rev > 0.1 ? `Revenue growing ${(rev*100).toFixed(1)}% YoY -- strong fundamental momentum.` :
    rev < 0 ? `Revenue declining ${(Math.abs(rev)*100).toFixed(1)}% YoY -- fundamental headwind.` :
    `Revenue growing ${(rev*100).toFixed(1)}% YoY -- modest growth.`;
  return `<strong>Company Fundamentals</strong><br>${peNote}${revNote ? '<br>' + revNote : ''}<small>Source: Alpha Vantage OVERVIEW endpoint. Updated quarterly.</small>`;
}

function dHistorical(vs1y, ret1y) {
  const val = vs1y != null ? vs1y : ret1y;
  const msg = val == null ? 'Historical data unavailable.' :
    val > 20 ? `Strongly outperforming the S&P 500 by ${val.toFixed(1)}% over 1 year. Strong relative momentum.` :
    val > 5  ? `Outperforming the S&P 500 by ${val.toFixed(1)}% over 1 year. Positive relative strength.` :
    val > -5 ? `Performing in line with the S&P 500 (${val.toFixed(1)}% relative). Neutral relative strength.` :
    val > -20 ? `Underperforming the S&P 500 by ${Math.abs(val).toFixed(1)}% over 1 year. Weak relative performance.` :
    `Strongly underperforming the S&P 500 by ${Math.abs(val).toFixed(1)}% over 1 year. Consider why before buying.`;
  return `<strong>Historical Performance vs SPY</strong><br>${msg}<small>Source: Yahoo Finance 5Y weekly data. Returns calculated from adjusted closes.</small>`;
}

function dEarnings(beats, misses, nextDate) {
  const total = beats + misses;
  const pct   = total > 0 ? Math.round(beats / total * 100) : 0;
  const msg = total === 0 ? 'No earnings data available.' :
    pct >= 75 ? `Beat earnings estimates ${beats}/${total} quarters (${pct}%) -- strong execution track record.` :
    pct >= 50 ? `Beat ${beats}/${total} quarters -- average execution. Watch for trend.` :
    `Beat only ${beats}/${total} quarters (${pct}%) -- inconsistent execution. Higher risk of guidance cuts.`;
  const dateMsg = nextDate ? `<br>Next earnings report: <strong>${nextDate}</strong> -- expect volatility around this date.` : '';
  return `<strong>Earnings History</strong><br>${msg}${dateMsg}<small>Positive surprise = company beat analyst EPS estimate that quarter.</small>`;
}

function dAnalystRating(consensus, upside) {
  const upsideMsg = upside != null ? ` Mean price target implies <strong>${upside > 0 ? '+' : ''}${upside.toFixed(1)}%</strong> ${upside > 0 ? 'upside' : 'downside'} from current price.` : '';
  const map = {
    'Strong Buy':  `Analysts strongly recommend buying. High conviction in upside potential.${upsideMsg}`,
    'Buy':         `Majority of analysts rate this a buy.${upsideMsg}`,
    'Hold':        `Analysts suggest holding existing positions -- neutral near-term outlook.${upsideMsg}`,
    'Sell':        `Analysts suggest reducing exposure -- downside risk expected.${upsideMsg}`,
    'Strong Sell': `Strong analyst consensus to sell -- significant downside expected.${upsideMsg}`,
    'No Data':     'Analyst rating data unavailable.',
  };
  return `<strong>Analyst Consensus: ${consensus}</strong><br>${map[consensus] || map['No Data']}<small>Source: Finnhub analyst recommendations. Consensus based on most recent month's ratings.</small>`;
}

function dInsider(buyCount, sellCount, netShares) {
  const total = buyCount + sellCount;
  let msg = total === 0 ? 'No recent open-market insider transactions found.' :
    buyCount > sellCount * 2 ? `Insiders are buying heavily (${buyCount} buys vs ${sellCount} sells) -- bullish internal signal.` :
    sellCount > buyCount * 2 ? `Insiders are selling heavily (${sellCount} sells vs ${buyCount} buys) -- caution advised.` :
    `Mixed insider activity (${buyCount} buys / ${sellCount} sells) -- no strong signal.`;
  if (netShares > 0) msg += ` Net ${netShares.toLocaleString()} shares purchased.`;
  else if (netShares < 0) msg += ` Net ${Math.abs(netShares).toLocaleString()} shares sold.`;
  return `<strong>Insider Transactions</strong><br>${msg}<small>Only open-market purchases (P) and sales (S) are shown. Excludes options exercises and awards.</small>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   STOCK RENDER FUNCTIONS
═══════════════════════════════════════════════════════════════════════════ */

function renderStockFundamentals(d) {
  const fund = d.fundamentals;
  if (!fund || !fund.available) {
    el('fund-sector-badge').textContent = 'No Data';
    el('fund-metrics-grid').innerHTML = '<div style="color:var(--muted);font-size:0.82rem;padding:0.5rem 0">Fundamentals unavailable. Add ALPHA_VANTAGE_KEY to .env to enable.</div>';
    el('week52-bar-section')?.classList.add('hidden');
    el('pe-vs-sector-section')?.classList.add('hidden');
    return;
  }

  const badge = el('fund-sector-badge');
  badge.textContent = fund.sector || 'N/A';
  badge.className   = 'dir-badge neutral';

  const descEl = el('fund-company-desc');
  if (fund.description) {
    descEl.textContent = fund.description;
    descEl.classList.remove('hidden');
  } else {
    descEl.classList.add('hidden');
  }

  const fmt = (v, prefix='', suffix='', decimals=2) =>
    v != null ? `${prefix}${typeof v === 'number' ? v.toFixed(decimals) : v}${suffix}` : 'N/A';
  const pct = v => v != null ? `${(v * 100).toFixed(1)}%` : 'N/A';

  const metrics = [
    { label: 'P/E Ratio',   value: fmt(fund.pe_ratio, '', 'x', 1),
      cls:  fund.pe_ratio == null ? '' : fund.pe_ratio < 20 ? 'up' : fund.pe_ratio > 35 ? 'down' : '',
      note: fund.forward_pe != null ? `Fwd: ${fund.forward_pe.toFixed(1)}x` : '' },
    { label: 'EPS',         value: fmt(fund.eps, '$'), cls: (fund.eps||0) > 0 ? 'up' : 'down', note: 'TTM' },
    { label: 'Market Cap',  value: fund.market_cap || 'N/A', cls: '', note: fund.sector || '' },
    { label: 'Beta',        value: fmt(fund.beta, '', '', 2),
      cls:  fund.beta == null ? '' : fund.beta < 1 ? 'up' : fund.beta > 1.5 ? 'down' : '',
      note: fund.beta != null ? (fund.beta < 1 ? 'Low volatility' : fund.beta > 1.5 ? 'High volatility' : 'Moderate') : '' },
    { label: 'Revenue Growth', value: pct(fund.revenue_growth),
      cls:  fund.revenue_growth == null ? '' : fund.revenue_growth > 0 ? 'up' : 'down', note: 'QoQ YoY' },
    { label: 'Profit Margin',  value: pct(fund.profit_margin),
      cls:  fund.profit_margin == null ? '' : fund.profit_margin > 0.1 ? 'up' : fund.profit_margin < 0 ? 'down' : '', note: 'TTM' },
    { label: 'ROE',         value: pct(fund.roe),
      cls:  fund.roe == null ? '' : fund.roe > 0.15 ? 'up' : fund.roe < 0 ? 'down' : '', note: 'Return on Equity' },
    { label: '52W High',    value: fmt(fund.week52_high, '$'), cls: 'up',  note: '' },
    { label: '52W Low',     value: fmt(fund.week52_low,  '$'), cls: 'down', note: '' },
  ];

  el('fund-metrics-grid').innerHTML = metrics.map(m => {
    const tipId = mkTip('Fundamentals', dFundamentals(fund));
    return `<div class="fund-metric" data-tip="${tipId}">
      <div class="fund-metric-label">${m.label}</div>
      <div class="fund-metric-value ${m.cls}">${m.value}</div>
      ${m.note ? `<div class="fund-metric-note">${m.note}</div>` : ''}
    </div>`;
  }).join('');

  // 52-Week range bar
  const w52Sec = el('week52-bar-section');
  const low  = fund.week52_low;
  const high = fund.week52_high;
  const price = parseFloat(d.last_price);
  if (w52Sec && low != null && high != null && !isNaN(price) && high > low) {
    const pct52 = Math.max(0, Math.min(100, (price - low) / (high - low) * 100));
    const t52   = mkTip('52-Week Range', d52WRange(low, high, price));
    w52Sec.innerHTML = `
      <div class="week52-bar-label">52-Week Range Position</div>
      <div class="week52-bar-track" data-tip="${t52}">
        <div class="week52-bar-marker" style="left:${pct52.toFixed(1)}%"></div>
      </div>
      <div class="week52-bar-labels">
        <span class="ret-down">$${Number(low).toFixed(2)} Low</span>
        <span style="color:var(--muted)">${pct52.toFixed(0)}% of range</span>
        <span class="ret-up">$${Number(high).toFixed(2)} High</span>
      </div>`;
    w52Sec.classList.remove('hidden');
  } else if (w52Sec) {
    w52Sec.classList.add('hidden');
  }

  // PE vs sector comparison
  const pvSec = el('pe-vs-sector-section');
  const pvPct  = fund.pe_vs_sector_pct;
  const pvAvg  = fund.sector_pe_avg;
  if (pvSec && pvPct != null && pvAvg != null) {
    const pvCls  = pvPct > 15 ? 'pv-premium' : pvPct < -15 ? 'pv-discount' : 'pv-inline';
    const pvDir  = pvPct > 15 ? `+${pvPct.toFixed(0)}% premium vs sector` : pvPct < -15 ? `${pvPct.toFixed(0)}% discount vs sector` : 'In line with sector';
    const pvTip  = mkTip('Valuation vs Sector', dValuationVsSector(fund.pe_ratio, pvAvg, pvPct));
    pvSec.innerHTML = `<span class="pv-label" data-tip="${pvTip}">P/E vs Sector Avg (${pvAvg}x): <span class="pv-value ${pvCls}">${pvDir}</span></span>`;
    pvSec.classList.remove('hidden');
  } else if (pvSec) {
    pvSec.classList.add('hidden');
  }
}

function renderStockHistory(d) {
  const h = d.history;
  const histDir = el('hist-dir-badge');
  if (!h || !h.available) {
    histDir.textContent = 'No Data';
    histDir.className = 'dir-badge neutral';
    el('hist-label').textContent = 'Historical data unavailable.';
    el('hist-table-body').innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center">Yahoo Finance data unavailable</td></tr>';
    return;
  }

  histDir.textContent = h.direction === 'up' ? 'Outperforming' : h.direction === 'down' ? 'Underperforming' : 'In-Line';
  histDir.className   = `dir-badge ${h.direction}`;
  el('hist-label').textContent = h.label || '';
  setTip(el('history-card'), 'Historical Performance', dHistorical(h.vs_spy?.['1Y'], h.returns?.['1Y']));

  const periods = ['1M', '3M', '6M', '1Y', '2Y', '5Y'];
  const fmt = v => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : 'N/A';

  // Sector relative strength row for 1M
  const sectorEtf = h.sector_etf;
  const sectorTip = sectorEtf ? mkTip('Sector Relative Strength', dSectorStrength(h.vs_sector_1m, sectorEtf)) : null;
  const sectorRow = (sectorEtf && h.sector_1m != null) ? (() => {
    const vs1m    = h.vs_sector_1m;
    const svCls   = vs1m == null ? 'ret-neutral' : vs1m > 0 ? 'ret-up' : 'ret-down';
    const etfCls  = h.sector_1m > 0 ? 'ret-up' : h.sector_1m < 0 ? 'ret-down' : 'ret-neutral';
    const stk1m   = h.returns?.['1M'];
    const stkCls  = stk1m == null ? 'ret-neutral' : stk1m > 0 ? 'ret-up' : 'ret-down';
    return `<tr style="border-top:1px solid var(--border2)" data-tip="${sectorTip}">
      <td>1M vs ${sectorEtf}</td>
      <td class="${stkCls}">${fmt(stk1m)}</td>
      <td class="${etfCls}">${fmt(h.sector_1m)}</td>
      <td class="${svCls}">${fmt(vs1m)}</td>
    </tr>`;
  })() : '';

  el('hist-table-body').innerHTML = periods.map(p => {
    const ret  = h.returns?.[p];
    const spy  = h.spy_returns?.[p];
    const vs   = h.vs_spy?.[p];
    const rCls = ret  == null ? 'ret-neutral' : ret  > 0 ? 'ret-up'  : 'ret-down';
    const sCls = spy  == null ? 'ret-neutral' : spy  > 0 ? 'ret-up'  : 'ret-down';
    const vCls = vs   == null ? 'ret-neutral' : vs   > 0 ? 'ret-up'  : 'ret-down';
    return `<tr>
      <td>${p}</td>
      <td class="${rCls}">${fmt(ret)}</td>
      <td class="${sCls}">${fmt(spy)}</td>
      <td class="${vCls}">${fmt(vs)}</td>
    </tr>`;
  }).join('') + sectorRow;
}

function renderStockEarnings(d) {
  const earn = d.earnings;
  const badge = el('earnings-record-badge');
  if (!earn || !earn.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    el('earnings-next-date').textContent = '';
    el('earnings-table-body').innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center">Earnings data unavailable. Add FINNHUB_KEY to .env.</td></tr>';
    return;
  }

  const beats  = earn.beats  || 0;
  const misses = earn.misses || 0;
  const total  = beats + misses;
  badge.textContent = `${beats}/${total} Beats`;
  badge.className   = `dir-badge ${beats > misses ? 'up' : beats < misses ? 'down' : 'neutral'}`;
  setTip(el('earnings-card'), 'Earnings History', dEarnings(beats, misses, earn.next_date));

  const nextEl = el('earnings-next-date');
  nextEl.textContent = earn.next_date ? `Next earnings: ${earn.next_date}` : '';
  nextEl.style.display = earn.next_date ? 'block' : 'none';

  el('earnings-table-body').innerHTML = (earn.quarters || []).map(q => {
    const beat = q.beat;
    const beatCls = beat == null ? '' : beat ? 'earn-beat' : 'earn-miss';
    const supCls  = q.surprise_pct == null ? '' : q.surprise_pct > 0 ? 'surprise-pos' : 'surprise-neg';
    const sup     = q.surprise_pct != null ? `${q.surprise_pct > 0 ? '+' : ''}${q.surprise_pct.toFixed(1)}%` : 'N/A';
    return `<tr>
      <td>${q.period || 'N/A'}</td>
      <td class="${beatCls}">${q.actual != null ? q.actual.toFixed(2) : 'N/A'}</td>
      <td>${q.estimate != null ? q.estimate.toFixed(2) : 'N/A'}</td>
      <td class="${supCls} ${beatCls}">${sup} ${beat != null ? (beat ? 'Beat' : 'Miss') : ''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="4" style="color:var(--muted)">No quarterly data</td></tr>';
}

function renderStockAnalyst(d) {
  const ana = d.analyst;
  const badge = el('analyst-consensus-badge');
  if (!ana || !ana.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    el('analyst-target').textContent = '';
    el('analyst-bar-fill').style.width = '50%';
    el('analyst-bar-legend').innerHTML = '';
    el('analyst-ratings-body').innerHTML = '<tr><td colspan="2" style="color:var(--muted)">Analyst data unavailable. Add FINNHUB_KEY to .env.</td></tr>';
    return;
  }

  const consensus = ana.consensus || 'No Data';
  const conDir = ['Strong Buy','Buy'].includes(consensus) ? 'up' : ['Sell','Strong Sell'].includes(consensus) ? 'down' : 'neutral';
  badge.textContent = consensus; badge.className = `dir-badge ${conDir}`;
  setTip(el('analyst-card'), 'Analyst Consensus', dAnalystRating(consensus, ana.upside_pct));

  // Price target
  const upside  = ana.upside_pct;
  const ptMean  = ana.price_target_mean;
  let targetTxt = '';
  if (ptMean) {
    targetTxt = `Mean target: $${Number(ptMean).toFixed(2)}`;
    if (upside != null) targetTxt += ` (${upside > 0 ? '+' : ''}${upside.toFixed(1)}% ${upside > 0 ? 'upside' : 'downside'})`;
  }
  el('analyst-target').textContent = targetTxt;

  // Consensus bar: buy% fills from left (green), sell% fills from right (red)
  const total    = ana.total || 1;
  const buyPct   = Math.round((ana.strong_buy + ana.buy) / total * 100);
  const sellPct  = Math.round((ana.strong_sell + ana.sell) / total * 100);
  const holdPct  = 100 - buyPct - sellPct;
  el('analyst-bar-fill').style.width = `${buyPct}%`;
  el('analyst-bar-legend').innerHTML =
    `<span class="ret-up">${buyPct}% Buy</span>` +
    `<span class="ret-neutral">${holdPct}% Hold</span>` +
    `<span class="ret-down">${sellPct}% Sell</span>`;

  el('analyst-ratings-body').innerHTML = [
    ['Strong Buy',  ana.strong_buy,  'up'],
    ['Buy',         ana.buy,         'up'],
    ['Hold',        ana.hold,        'neutral'],
    ['Sell',        ana.sell,        'down'],
    ['Strong Sell', ana.strong_sell, 'down'],
  ].map(([lbl, cnt, cls]) =>
    `<tr><td>${lbl}</td><td class="qs-val ${cls}">${cnt}</td></tr>`
  ).join('');
}

function renderStockInsider(d) {
  const ins = d.insider;
  const badge = el('insider-summary-badge');
  if (!ins || !ins.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    el('insider-summary').textContent = '';
    el('insider-table-body').innerHTML = '<tr><td colspan="6" style="color:var(--muted);text-align:center">No recent insider transactions found.</td></tr>';
    return;
  }

  const bc = ins.buy_count  || 0;
  const sc = ins.sell_count || 0;
  const netDir = bc > sc * 1.5 ? 'up' : sc > bc * 1.5 ? 'down' : 'neutral';
  badge.textContent = `${bc} Buys / ${sc} Sells`;
  badge.className   = `dir-badge ${netDir}`;
  setTip(el('insider-card'), 'Insider Activity', dInsider(bc, sc, ins.net_shares || 0));

  const net = ins.net_shares || 0;
  el('insider-summary').textContent =
    `${bc} open-market purchases, ${sc} sales in recent months.` +
    (net !== 0 ? ` Net: ${net > 0 ? '+' : ''}${net.toLocaleString()} shares.` : '');

  el('insider-table-body').innerHTML = (ins.transactions || []).map(tx => {
    const cls    = tx.type === 'BUY' ? 'insider-buy' : 'insider-sell';
    const shares = tx.shares ? tx.shares.toLocaleString() : 'N/A';
    const price  = tx.price  ? `$${tx.price.toFixed(2)}` : 'N/A';
    const value  = tx.value  ? `$${(tx.value / 1000).toFixed(0)}K` : 'N/A';
    return `<tr>
      <td><strong>${tx.name}</strong>${tx.title ? `<div style="font-size:0.7rem;color:var(--muted)">${tx.title}</div>` : ''}</td>
      <td class="${cls}">${tx.type}</td>
      <td>${shares}</td>
      <td>${price}</td>
      <td>${value}</td>
      <td style="white-space:nowrap">${tx.date || 'N/A'}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" style="color:var(--muted)">No transactions</td></tr>';
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADVANCED STOCK FEATURE TOOLTIP DESCRIPTIONS
═══════════════════════════════════════════════════════════════════════════ */

function dShortInterest(pct, dtc, squeezeRisk) {
  const pctNote = pct == null ? 'Short interest data unavailable.' :
    pct > 20 ? `${pct.toFixed(1)}% of the float is sold short. HIGH short interest. Any sharp price rise can trigger forced short covering (short squeeze).` :
    pct > 10 ? `${pct.toFixed(1)}% of the float is sold short. MODERATE short interest. Watch for squeeze conditions if price breaks higher.` :
    `${pct.toFixed(1)}% of the float is sold short. LOW short interest. Most participants are not betting against this stock.`;
  const dtcNote = dtc != null ? `<br>Days to Cover: <strong>${dtc.toFixed(1)} days</strong> (how long at current volume to close all short positions).` : '';
  const sqNote  = squeezeRisk ? '<br><strong>Squeeze Risk: HIGH.</strong> Short sellers must buy to cover if price rises, accelerating the move.' : '';
  return `<strong>Short Interest</strong><br>${pctNote}${dtcNote}${sqNote}<small>Source: Finnhub. Updated bi-monthly. Above 20% is considered elevated short interest.</small>`;
}

function dInstitutional(signal, buyCount, sellCount) {
  const total = (buyCount || 0) + (sellCount || 0);
  const msg = signal === 'accumulation' ?
    '<strong>Institutional Accumulation:</strong> More major holders are increasing positions than reducing. Smart money is broadly bullish.' :
    signal === 'distribution' ?
    '<strong>Institutional Distribution:</strong> More major holders are reducing positions than increasing. Smart money is broadly selling.' :
    '<strong>Neutral Activity:</strong> Institutional buy and sell activity is roughly balanced. No clear smart money direction.';
  return `<strong>Institutional Ownership</strong><br>${msg}<br>${buyCount} holders increasing vs ${sellCount} reducing among top ${total} tracked.<small>Source: Finnhub 13F filings. Positive QoQ Change = bought more shares since last quarter.</small>`;
}

function dOptionsSentiment(ratio, signal, callOI, putOI) {
  const rNote = ratio == null ? 'Options data unavailable.' :
    ratio >= 1.5 ? `Put/Call ratio of ${ratio.toFixed(2)} signals EXTREME FEAR. Heavy put buying. Historically a contrarian bullish signal at extremes.` :
    ratio >= 1.0 ? `Put/Call ratio of ${ratio.toFixed(2)} signals BEARISH options positioning. More puts than calls are being bought.` :
    ratio >= 0.7 ? `Put/Call ratio of ${ratio.toFixed(2)} signals NEUTRAL options positioning. Calls and puts roughly balanced.` :
    `Put/Call ratio of ${ratio.toFixed(2)} signals BULLISH options positioning. Significantly more call buying than put buying.`;
  const oiNote = (callOI || putOI) ? `<br>Call OI: ${callOI ? callOI.toLocaleString() : 'N/A'} | Put OI: ${putOI ? putOI.toLocaleString() : 'N/A'}` : '';
  return `<strong>Options Sentiment (Put/Call Ratio)</strong><br>${rNote}${oiNote}<small>Ratio = Total Put OI / Total Call OI. Below 0.7 = bullish. Above 1.0 = bearish. Above 1.5 = extreme fear.</small>`;
}

function dSectorStrength(vs1M, etf) {
  const msg = vs1M == null ? 'Sector performance data unavailable.' :
    vs1M > 5  ? `Outperforming sector ETF (${etf}) by ${vs1M.toFixed(1)}% this month. Strong relative strength vs sector peers.` :
    vs1M > 0  ? `Slightly outperforming sector ETF (${etf}) by ${vs1M.toFixed(1)}% this month.` :
    vs1M > -5 ? `Slightly underperforming sector ETF (${etf}) by ${Math.abs(vs1M).toFixed(1)}% this month.` :
    `Significantly underperforming sector ETF (${etf}) by ${Math.abs(vs1M).toFixed(1)}% this month. Weak relative strength.`;
  return `<strong>Sector Relative Strength (1M)</strong><br>${msg}<small>Compares the stock's 1-month return to its benchmark sector ETF. Positive = outperforming sector peers.</small>`;
}

function dValuationVsSector(pe, sectorPe, pct) {
  const msg = pct == null ? 'Sector P/E comparison unavailable.' :
    pct > 50 ? `P/E of ${pe != null ? pe.toFixed(1) : 'N/A'}x is ${pct.toFixed(0)}% ABOVE sector average (${sectorPe}x). Significant premium. Any earnings miss risks a sharp de-rating.` :
    pct > 15 ? `P/E of ${pe != null ? pe.toFixed(1) : 'N/A'}x is ${pct.toFixed(0)}% above sector average (${sectorPe}x). Modest premium; acceptable if growth justifies it.` :
    pct > -15 ? `P/E of ${pe != null ? pe.toFixed(1) : 'N/A'}x is roughly in line with sector average (${sectorPe}x). Fair valuation relative to peers.` :
    `P/E of ${pe != null ? pe.toFixed(1) : 'N/A'}x is ${Math.abs(pct).toFixed(0)}% BELOW sector average (${sectorPe}x). Discount to peers.`;
  return `<strong>Valuation vs Sector Average P/E</strong><br>${msg}<small>Sector average P/E is based on typical historical ranges. Extreme premiums increase reversal risk.</small>`;
}

function d52WRange(low, high, price) {
  const range = high - low;
  const pct   = range > 0 ? Math.round((price - low) / range * 100) : 0;
  const pos   = pct >= 90 ? 'near the 52-week HIGH' : pct >= 70 ? 'in the upper range' :
                pct >= 30 ? 'in the mid-range' : pct >= 10 ? 'in the lower range' : 'near the 52-week LOW';
  return `<strong>52-Week Range Position</strong><br>Current price is ${pos} at <strong>${pct}%</strong> of the annual trading range.<br>52W Low: $${Number(low).toFixed(2)} | 52W High: $${Number(high).toFixed(2)}<small>Near 52W high with strong momentum may signal breakout. Near 52W low may be a value opportunity or downtrend.</small>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADVANCED STOCK RENDER FUNCTIONS
═══════════════════════════════════════════════════════════════════════════ */

function renderEarningsProximityWarning(d) {
  const banner = el('earnings-warning-banner');
  if (!banner) return;
  const earn = d.earnings;
  if (!earn || !earn.next_date) {
    banner.className = 'earnings-warning-banner hidden stock-only'; return;
  }
  let daysAway;
  try {
    const nextD = new Date(earn.next_date + 'T00:00:00Z');
    const today = new Date(); today.setHours(0, 0, 0, 0);
    daysAway = Math.round((nextD - today) / 86400000);
  } catch { banner.className = 'earnings-warning-banner hidden stock-only'; return; }

  if (daysAway < 0 || daysAway > 30) {
    banner.className = 'earnings-warning-banner hidden stock-only'; return;
  }
  if (daysAway <= 14) {
    banner.className = 'earnings-warning-banner red stock-only';
    banner.innerHTML = `<span>&#9888;</span> Earnings in <strong>${daysAway} day${daysAway !== 1 ? 's' : ''}</strong> (${earn.next_date}) - High volatility risk. Consider reducing exposure.`;
  } else {
    banner.className = 'earnings-warning-banner orange stock-only';
    banner.innerHTML = `<span>&#128276;</span> Earnings in <strong>${daysAway} days</strong> (${earn.next_date}) - Monitor for pre-earnings positioning.`;
  }
}

function renderShortInterest(d) {
  const si    = d.short_interest;
  const badge = el('si-badge');
  const main  = el('si-main-stat');
  if (!badge || !main) return;

  if (!si || !si.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    main.textContent  = 'N/A'; main.className = 'si-main-stat si-unknown';
    setVal('si-pct',    'N/A', 'neutral');
    setVal('si-dtc',    'N/A', 'neutral');
    setVal('si-squeeze','N/A', 'neutral');
    return;
  }

  const pct    = si.short_percent;
  const dtc    = si.days_to_cover;
  const signal = si.signal || 'unknown';
  const sigDir = signal === 'high' ? 'down' : signal === 'moderate' ? 'neutral' : signal === 'low' ? 'up' : 'neutral';

  badge.textContent = signal === 'high' ? 'High Short' : signal === 'moderate' ? 'Moderate' : signal === 'low' ? 'Low Short' : 'Unknown';
  badge.className   = `dir-badge ${sigDir}`;
  main.textContent  = pct != null ? `${pct.toFixed(1)}% Float Short` : 'N/A';
  main.className    = `si-main-stat si-${signal}`;

  setVal('si-pct',    pct != null ? `${pct.toFixed(1)}%` : 'N/A', sigDir);
  setVal('si-dtc',    dtc != null ? `${dtc.toFixed(1)} days` : 'N/A', 'neutral');
  setVal('si-squeeze', si.squeeze_risk ? 'YES - Squeeze Risk' : 'No', si.squeeze_risk ? 'down' : 'up');

  const siSrc = si.source ? ` <span style="font-size:0.7rem;color:var(--muted);font-weight:400">via ${si.source}</span>` : '';
  el('short-interest-card').querySelector('.card-title').innerHTML = `📉 Short Interest${siSrc}`;
  setTip(el('short-interest-card'), 'Short Interest', dShortInterest(pct, dtc, si.squeeze_risk));
}

function renderInstitutionalOwnership(d) {
  const inst  = d.institutional;
  const badge = el('inst-badge');
  const sumEl = el('inst-summary');
  if (!badge || !sumEl) return;

  if (!inst || !inst.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    sumEl.textContent = 'Institutional ownership data unavailable.';
    el('inst-table-body').innerHTML = '<tr><td colspan="3" style="color:var(--muted);text-align:center">No data. Requires Finnhub API key.</td></tr>';
    return;
  }

  const signal = inst.signal || 'neutral';
  const sigDir = signal === 'accumulation' ? 'up' : signal === 'distribution' ? 'down' : 'neutral';
  badge.textContent = capFirst(signal);
  badge.className   = `dir-badge ${sigDir}`;

  const bc = inst.buy_count || 0, sc = inst.sell_count || 0;
  sumEl.textContent = `${bc} major holders increasing vs ${sc} reducing positions (top 20 tracked).`;
  const instSrc = inst.source ? ` <span style="font-size:0.7rem;color:var(--muted);font-weight:400">via ${inst.source}</span>` : '';
  el('institutional-card').querySelector('.card-title').innerHTML = `🏛 Institutional Ownership${instSrc}`;
  if (inst.source === 'Yahoo Finance') {
    sumEl.textContent = `Top ${(inst.top_holders || []).length} holders shown. Direction data unavailable (Yahoo Finance fallback - no QoQ change).`;
  }
  setTip(el('institutional-card'), 'Institutional Ownership', dInstitutional(signal, bc, sc));

  el('inst-table-body').innerHTML = (inst.top_holders || []).map(h => {
    const chgCls  = h.change > 0 ? 'ret-up' : h.change < 0 ? 'ret-down' : 'ret-neutral';
    const chgText = h.change !== 0 ? `${h.change > 0 ? '+' : ''}${h.change.toLocaleString()}` : 'Unchanged';
    return `<tr>
      <td style="font-size:0.8rem">${h.name}</td>
      <td>${h.percent.toFixed(2)}%</td>
      <td class="${chgCls}" style="white-space:nowrap">${chgText}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="3" style="color:var(--muted)">No holder data</td></tr>';
}

function renderOptionsSentiment(d) {
  const opt   = d.options_sentiment;
  const badge = el('opt-badge');
  const main  = el('opt-main');
  if (!badge || !main) return;

  if (!opt || !opt.available) {
    badge.textContent = 'No Data'; badge.className = 'dir-badge neutral';
    main.textContent  = 'Options data unavailable.'; main.className = 'opt-main opt-neutral';
    setVal('opt-call-oi', 'N/A', 'neutral');
    setVal('opt-put-oi',  'N/A', 'neutral');
    setVal('opt-ratio',   'N/A', 'neutral');
    return;
  }

  const signal = opt.signal || 'neutral';
  const sigDir = signal === 'bullish' ? 'up' : (signal === 'bearish' || signal === 'extreme_fear') ? 'down' : 'neutral';
  badge.textContent = opt.label || capFirst(signal);
  badge.className   = `dir-badge ${sigDir}`;
  main.textContent  = `P/C Ratio: ${opt.ratio != null ? opt.ratio.toFixed(2) : 'N/A'}`;
  main.className    = `opt-main opt-${signal.replace('_', '-')}`;

  const fmtOI = v => v != null ? (v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v.toLocaleString()) : 'N/A';
  setVal('opt-call-oi', fmtOI(opt.call_oi), 'up');
  setVal('opt-put-oi',  fmtOI(opt.put_oi),  'down');
  setVal('opt-ratio',   opt.ratio != null ? opt.ratio.toFixed(2) : 'N/A', sigDir);

  const optSrc = opt.source ? ` <span style="font-size:0.7rem;color:var(--muted);font-weight:400">via ${opt.source}</span>` : '';
  el('options-sent-card').querySelector('.card-title').innerHTML = `⚙ Options Sentiment (Put/Call Ratio)${optSrc}`;
  setTip(el('options-sent-card'), 'Options Sentiment', dOptionsSentiment(opt.ratio, signal, opt.call_oi, opt.put_oi));
}
