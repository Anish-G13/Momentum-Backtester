import fs from "fs";
import path from "path";

export interface BacktestConfig {
  startDate: string;
  endDate: string;
  initialCapital: number;
  positions: number;
  lookbackMonths: number;
  skipLastMonth: boolean;
  includeShorts: boolean;
  rebalanceFreq: string;
  universe: string;
  verifyDate?: string | null;
  maxPositionsPerSector?: number;
  minAvgDollarVolume?: number;
  minMarketCap?: number;
  rankingMethod?: string; // "raw_return" | "risk_adjusted"
  regimeFilter?: boolean;
  regimeReducedExposurePct?: number;
  earningsBlackoutDays?: number;
  strategyMode?: string;
  factorWeights?: { momentum?: number; quality?: number; low_vol?: number } | string;
}

export interface TradeRecord {
  Date: string;
  Ticker: string;
  Action: "BUY" | "SELL" | "SHORT" | "COVER";
  Price: number;
  Shares: number;
  "Portfolio Value": number;
}

export interface PortfolioDailyRecord {
  Date: string;
  "Portfolio Value": number;
  Cash: number;
}

export interface RebalanceSnapshotDetail {
  ticker: string;
  shares: number;
  price: number;
  weight: number;
  value: number;
  momentumScore?: number;
  sector?: string;
  action?: string;
}

export interface RebalanceSnapshot {
  date: string;
  signalDate: string;
  portfolioValue: number;
  cash: number;
  count: number;
  tickers: string[];
  details: RebalanceSnapshotDetail[];
  exitedTickers: string[];
}

export interface VerificationRecord {
  Ticker: string;
  Rank: number | null;
  MomentumScore: number | null;
  Selected: "LONG" | "SHORT" | "NO";
  Start_Date: string | null;
  Start_Price: number | null;
  End_Date: string | null;
  End_Price: number | null;
  Status: "VALID" | "INSUFFICIENT_HISTORY" | "STALE_DATA" | "FILTERED_OUT";
  Sector?: string;
  SharesOutstanding?: number;
}

export interface BacktestResult {
  metrics: {
    "Starting Capital": number;
    "Ending Capital": number;
    "Total Return": number;
    "Annualized Return (CAGR)": number;
    "Maximum Drawdown": number;
    "Volatility": number;
    "Sharpe Ratio": number;
    "Calmar Ratio"?: number;
    "Number of Trades": number;
    "Average Holding Period (Days)": number;
    "Benchmark Ticker": string;
    "Benchmark Total Return": number;
    "Benchmark CAGR": number;
    "Benchmark Max Drawdown": number;
    "Benchmark Volatility": number;
    "Benchmark Sharpe Ratio": number;
    "Alpha vs Benchmark": number;
  };
  config: Record<string, any>;
  portfolio_history: PortfolioDailyRecord[];
  benchmark_history: PortfolioDailyRecord[];
  trades: TradeRecord[];
  rebalance_snapshots: RebalanceSnapshot[];
  verification_records: VerificationRecord[];
  files: {
    trades_csv: string;
    portfolio_csv: string;
    verification_csv: string;
    equity_curve_png?: string;
    drawdown_png?: string;
  };
  images?: {
    equity_curve?: string;
    drawdown?: string;
  };
}

// In-memory price cache: Ticker -> Map of "YYYY-MM-DD" -> Adj Close price
interface PriceData {
  dates: string[]; // sorted
  prices: number[];
  volumes?: number[];
  dateMap: Map<string, number>; // date -> price
  volMap?: Map<string, number>; // date -> volume
}

const priceCache = new Map<string, PriceData>();
let tickerMetadataCache: Record<string, { quoteType?: string; longName?: string; sharesOutstanding?: number | null; sector?: string | null }> | null = null;

const KNOWN_ISSUER_MAP: Record<string, string> = {
  GOOG: "Alphabet Inc.",
  GOOGL: "Alphabet Inc.",
  "BRK-A": "Berkshire Hathaway Inc.",
  "BRK-B": "Berkshire Hathaway Inc.",
  "BRK.A": "Berkshire Hathaway Inc.",
  "BRK.B": "Berkshire Hathaway Inc.",
  FOX: "Fox Corporation",
  FOXA: "Fox Corporation",
  NWS: "News Corporation",
  NWSA: "News Corporation",
  "BF-A": "Brown-Forman Corporation",
  "BF-B": "Brown-Forman Corporation",
  LEN: "Lennar Corporation",
  "LEN-B": "Lennar Corporation",
  UA: "Under Armour, Inc.",
  UAA: "Under Armour, Inc.",
  UHAL: "U-Haul Holding Company",
  "UHAL-B": "U-Haul Holding Company",
  FWONA: "Formula One Group",
  FWONK: "Formula One Group",
  LBRDA: "Liberty Broadband Corporation",
  LBRDK: "Liberty Broadband Corporation",
  LBTYA: "Liberty Global Ltd.",
  LBTYK: "Liberty Global Ltd.",
  LLYVA: "Liberty Live Holdings, Inc.",
  LLYVK: "Liberty Live Holdings, Inc.",
  GLIBA: "Liberty Capital Corporation",
  GLIBK: "Liberty Capital Corporation",
  HEI: "HEICO Corporation",
  "HEI-A": "HEICO Corporation",
  CWEN: "Clearway Energy, Inc.",
  "CWEN-A": "Clearway Energy, Inc.",
  "MOG-A": "Moog Inc.",
  "MOG-B": "Moog Inc.",
  GEF: "Greif, Inc.",
  "GEF-B": "Greif, Inc.",
  BIO: "Bio-Rad Laboratories, Inc.",
  "BIO-B": "Bio-Rad Laboratories, Inc.",
  BATRA: "Atlanta Braves Holdings",
  BATRK: "Atlanta Braves Holdings",
  LSXMA: "Liberty SiriusXM Group",
  LSXMK: "Liberty SiriusXM Group",
};

export function getParentIssuer(ticker: string): string {
  const tUpper = ticker.toUpperCase();
  if (KNOWN_ISSUER_MAP[tUpper]) {
    return KNOWN_ISSUER_MAP[tUpper];
  }
  const meta = getTickerMetadata();
  if (meta[tUpper]?.longName) {
    const longName = meta[tUpper].longName!;
    const cleaned = longName.replace(/\b(class|series)\s+[a-z0-9]+\b/gi, "")
      .replace(/[\s,.-]+/g, " ")
      .trim()
      .toLowerCase();
    if (cleaned) return cleaned;
  }
  return tUpper.replace(/[-.][A-Z]$/, "");
}

export function getTickerMetadata(): Record<string, any> {
  if (tickerMetadataCache) return tickerMetadataCache;
  const metaPath = path.join(process.cwd(), "backtester", "cache", "ticker_metadata.json");
  if (fs.existsSync(metaPath)) {
    try {
      tickerMetadataCache = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
      return tickerMetadataCache!;
    } catch (e) {
      console.warn("Failed to load ticker_metadata.json", e);
    }
  }
  tickerMetadataCache = {};
  return tickerMetadataCache;
}

export function loadTickerPriceData(ticker: string): PriceData | null {
  const tUpper = ticker.toUpperCase();
  if (priceCache.has(tUpper)) {
    return priceCache.get(tUpper)!;
  }

  const csvPath = path.join(process.cwd(), "backtester", "cache", `${tUpper}.csv`);
  if (!fs.existsSync(csvPath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(csvPath, "utf-8");
    const lines = content.split("\n");
    if (lines.length < 2) return null;

    const header = lines[0].split(",").map(h => h.trim().toLowerCase());
    const dateIdx = header.indexOf("date");
    const adjCloseIdx = header.indexOf("adj close");
    const closeIdx = header.indexOf("close");
    const volIdx = header.indexOf("volume");

    const pIdx = adjCloseIdx >= 0 ? adjCloseIdx : (closeIdx >= 0 ? closeIdx : 1);

    const dates: string[] = [];
    const prices: number[] = [];
    const volumes: number[] = [];
    const dateMap = new Map<string, number>();
    const volMap = new Map<string, number>();

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const parts = line.split(",");
      const d = parts[dateIdx]?.trim();
      const p = parseFloat(parts[pIdx]);
      if (d && !isNaN(p) && p > 0) {
        dates.push(d);
        prices.push(p);
        dateMap.set(d, p);

        if (volIdx >= 0 && parts[volIdx]) {
          const v = parseFloat(parts[volIdx]);
          const volVal = isNaN(v) ? 0 : v;
          volumes.push(volVal);
          volMap.set(d, volVal);
        }
      }
    }

    const data: PriceData = { dates, prices, volumes, dateMap, volMap };
    priceCache.set(tUpper, data);
    return data;
  } catch (e) {
    console.error(`Error loading price data for ${ticker}:`, e);
    return null;
  }
}

// Binary search to find price on or immediately before target date
export function getLastPriceBefore(priceData: PriceData, targetDate: string): { date: string; price: number; index: number } | null {
  const dates = priceData.dates;
  let low = 0;
  let high = dates.length - 1;
  let resultIdx = -1;

  while (low <= high) {
    const mid = (low + high) >> 1;
    if (dates[mid] <= targetDate) {
      resultIdx = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  if (resultIdx === -1) return null;
  return {
    date: dates[resultIdx],
    price: priceData.prices[resultIdx],
    index: resultIdx
  };
}

export function loadUniverseTickers(universeFile: string, targetDate?: string): string[] {
  let filename = "sp500.csv";
  const uLow = universeFile.toLowerCase();
  if (uLow.includes("custom_momentum")) {
    filename = "custom_momentum.csv";
  } else if (uLow.includes("russell")) {
    filename = "russell1000.csv";
  } else if (uLow.includes("custom_universe")) {
    filename = "custom_universe.csv";
  } else if (universeFile.endsWith(".csv")) {
    filename = universeFile;
  }

  const univPath = path.join(process.cwd(), "backtester", filename);
  if (!fs.existsSync(univPath)) {
    return [];
  }

  const content = fs.readFileSync(univPath, "utf-8");
  const lines = content.split("\n").map(l => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];

  const header = lines[0].split(",").map(h => h.trim().toLowerCase());
  const tickerIdx = header.indexOf("ticker") >= 0 ? header.indexOf("ticker") : 0;
  const addedIdx = header.indexOf("dateadded");
  const removedIdx = header.indexOf("dateremoved");

  const results: string[] = [];

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",").map(p => p.trim());
    const ticker = parts[tickerIdx]?.toUpperCase();
    if (!ticker || ticker === "TICKER") continue;

    if (targetDate && addedIdx >= 0 && removedIdx >= 0) {
      const added = parts[addedIdx] || "1900-01-01";
      const removed = parts[removedIdx] || "9999-12-31";
      if (targetDate < added || targetDate > removed) {
        continue;
      }
    }

    results.push(ticker);
  }

  return Array.from(new Set(results));
}

// Compute date minus N months
export function subtractMonths(dateStr: string, months: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  const currentMonth = d.getUTCMonth();
  d.setUTCMonth(currentMonth - months);
  return d.toISOString().split("T")[0];
}

// Compute days difference between two YYYY-MM-DD dates
export function daysBetween(d1: string, d2: string): number {
  const t1 = new Date(d1 + "T00:00:00Z").getTime();
  const t2 = new Date(d2 + "T00:00:00Z").getTime();
  return Math.round(Math.abs(t2 - t1) / (1000 * 60 * 60 * 24));
}

export function generateSvgChart(title: string, dataPoints: { date: string; strategy: number; benchmark?: number }[], isDrawdown = false): string {
  const width = 800;
  const height = 400;
  const margin = { top: 40, right: 30, bottom: 40, left: 70 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  if (dataPoints.length === 0) return "";

  const stratVals = dataPoints.map(d => d.strategy);
  const benchVals = dataPoints.map(d => d.benchmark ?? d.strategy);
  const allVals = isDrawdown ? [...stratVals, ...(dataPoints[0]?.benchmark !== undefined ? benchVals : []), 0] : [...stratVals, ...benchVals];

  let minVal = Math.min(...allVals);
  let maxVal = Math.max(...allVals);
  if (minVal === maxVal) {
    minVal *= 0.9;
    maxVal *= 1.1;
  }

  const getY = (val: number) => {
    const pct = (val - minVal) / (maxVal - minVal);
    return margin.top + innerH - pct * innerH;
  };

  const getX = (idx: number) => {
    return margin.left + (idx / (dataPoints.length - 1 || 1)) * innerW;
  };

  let stratPath = "";
  let benchPath = "";

  dataPoints.forEach((d, i) => {
    const x = getX(i);
    const yS = getY(d.strategy);
    stratPath += (i === 0 ? `M ${x.toFixed(1)} ${yS.toFixed(1)}` : ` L ${x.toFixed(1)} ${yS.toFixed(1)}`);
    if (d.benchmark !== undefined) {
      const yB = getY(d.benchmark);
      benchPath += (i === 0 ? `M ${x.toFixed(1)} ${yB.toFixed(1)}` : ` L ${x.toFixed(1)} ${yB.toFixed(1)}`);
    }
  });

  const numGridLines = 5;
  let gridLines = "";
  for (let i = 0; i <= numGridLines; i++) {
    const val = minVal + (i / numGridLines) * (maxVal - minVal);
    const y = getY(val);
    const label = isDrawdown ? `${(val * 100).toFixed(1)}%` : `$${Math.round(val).toLocaleString()}`;
    gridLines += `
      <line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#27272a" stroke-dasharray="3,3" />
      <text x="${margin.left - 10}" y="${y + 4}" fill="#71717a" font-size="10" text-anchor="end" font-family="monospace">${label}</text>
    `;
  }

  const firstDate = dataPoints[0].date;
  const lastDate = dataPoints[dataPoints.length - 1].date;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="100%" height="100%" style="background-color: #09090b; border-radius: 12px;">
      <text x="${margin.left}" y="24" fill="#f4f4f5" font-size="14" font-weight="bold" font-family="sans-serif">${title}</text>
      ${gridLines}
      ${benchPath ? `<path d="${benchPath}" fill="none" stroke="#71717a" stroke-width="1.5" stroke-dasharray="4,4" />` : ""}
      <path d="${stratPath}" fill="none" stroke="${isDrawdown ? '#f43f5e' : '#10b981'}" stroke-width="2.5" />
      <text x="${margin.left}" y="${height - 15}" fill="#71717a" font-size="10" font-family="monospace">${firstDate}</text>
      <text x="${width - margin.right}" y="${height - 15}" fill="#71717a" font-size="10" text-anchor="end" font-family="monospace">${lastDate}</text>
      <g transform="translate(${width - 220}, 15)">
        <rect x="0" y="0" width="12" height="12" fill="${isDrawdown ? '#f43f5e' : '#10b981'}" rx="2" />
        <text x="18" y="10" fill="#e4e4e7" font-size="11" font-family="sans-serif">Strategy</text>
        ${benchPath ? `
          <rect x="80" y="0" width="12" height="12" fill="#71717a" rx="2" />
          <text x="98" y="10" fill="#e4e4e7" font-size="11" font-family="sans-serif">SPY Benchmark</text>
        ` : ""}
      </g>
    </svg>
  `;

  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

export function runBacktestEngine(config: BacktestConfig): BacktestResult {
  const {
    startDate = "2025-07-31",
    endDate = "2026-08-04",
    initialCapital = 30000,
    positions = 10,
    lookbackMonths = 12,
    skipLastMonth = true,
    includeShorts = false,
    rebalanceFreq = "monthly",
    universe = "russell1000.csv",
    verifyDate,
    maxPositionsPerSector = 0,
    minAvgDollarVolume = 0,
    minMarketCap = 0,
    rankingMethod = "raw_return",
    regimeFilter = false,
    regimeReducedExposurePct = 0.5,
  } = config;

  // 1. Load SPY benchmark price series
  const spyData = loadTickerPriceData("SPY");
  if (!spyData) {
    throw new Error("Benchmark SPY data not found in cache.");
  }

  // Get list of trading days in [startDate, endDate]
  const tradingDays = spyData.dates.filter(d => d >= startDate && d <= endDate);
  if (tradingDays.length < 2) {
    throw new Error(`Insufficient trading days between ${startDate} and ${endDate}.`);
  }

  const metadata = getTickerMetadata();

  // 2. Determine rebalance dates
  const rebalanceDates: string[] = [];
  if (rebalanceFreq.toLowerCase() === "weekly") {
    // Rebalance every 5 trading days
    for (let i = 0; i < tradingDays.length; i += 5) {
      rebalanceDates.push(tradingDays[i]);
    }
  } else if (rebalanceFreq.toLowerCase() === "quarterly") {
    // End of March, June, September, December
    let lastMonth = "";
    for (let i = 0; i < tradingDays.length; i++) {
      const d = tradingDays[i];
      const month = d.substring(0, 7);
      const mNum = parseInt(d.substring(5, 7), 10);
      const isNextNewMonth = i === tradingDays.length - 1 || tradingDays[i + 1].substring(0, 7) !== month;
      if (isNextNewMonth && (mNum === 3 || mNum === 6 || mNum === 9 || mNum === 12)) {
        rebalanceDates.push(d);
      }
    }
  } else {
    // Monthly (default): last trading day of each month
    for (let i = 0; i < tradingDays.length; i++) {
      const d = tradingDays[i];
      const month = d.substring(0, 7);
      const isLastOfMonth = i === tradingDays.length - 1 || tradingDays[i + 1].substring(0, 7) !== month;
      if (isLastOfMonth) {
        rebalanceDates.push(d);
      }
    }
  }

  // Always include the first date if not already present
  if (rebalanceDates.length === 0 || rebalanceDates[0] > tradingDays[0]) {
    rebalanceDates.unshift(tradingDays[0]);
  }

  const universeTickers = loadUniverseTickers(universe);

  // 3. Preload all universe price data for fast execution
  const tickerPrices = new Map<string, PriceData>();
  for (const t of universeTickers) {
    const pData = loadTickerPriceData(t);
    if (pData) {
      tickerPrices.set(t, pData);
    }
  }

  // 4. State tracking
  let cash = initialCapital;
  let currentPositions = new Map<string, { shares: number; entryPrice: number; action: "LONG" | "SHORT" }>();
  const tradeLogs: TradeRecord[] = [];
  const rebalanceSnapshots: RebalanceSnapshot[] = [];
  const portfolioHistory: PortfolioDailyRecord[] = [];
  const benchmarkHistory: PortfolioDailyRecord[] = [];

  const spyStartPrice = spyData.dateMap.get(tradingDays[0]) || spyData.prices[0];
  const spyInitialShares = initialCapital / spyStartPrice;

  // Track SPY 200 SMA
  const getSpy200Sma = (currentDate: string): number | null => {
    const idx = spyData.dates.indexOf(currentDate);
    if (idx < 200) return null;
    let sum = 0;
    for (let i = idx - 199; i <= idx; i++) {
      sum += spyData.prices[i];
    }
    return sum / 200;
  };

  // Helper to compute momentum score for a ticker on rebalance date
  const computeMomentum = (ticker: string, rebalDate: string): { score: number; pStart: number; pEnd: number; startDate: string; endDate: string; status: string } => {
    const pData = tickerPrices.get(ticker);
    if (!pData) {
      return { score: 0, pStart: 0, pEnd: 0, startDate: "", endDate: "", status: "INSUFFICIENT_HISTORY" };
    }

    const startTarget = subtractMonths(rebalDate, lookbackMonths);
    const endTarget = skipLastMonth ? subtractMonths(rebalDate, 1) : rebalDate;

    const pStartObj = getLastPriceBefore(pData, startTarget);
    const pEndObj = getLastPriceBefore(pData, endTarget);
    const pCurrObj = getLastPriceBefore(pData, rebalDate);

    if (!pStartObj || !pEndObj || !pCurrObj || pStartObj.price <= 0 || pEndObj.price <= 0) {
      return { score: 0, pStart: 0, pEnd: 0, startDate: "", endDate: "", status: "INSUFFICIENT_HISTORY" };
    }

    // Check staleness (gap > 14 days)
    if (daysBetween(startTarget, pStartObj.date) > 14 || daysBetween(endTarget, pEndObj.date) > 14) {
      return { score: 0, pStart: pStartObj.price, pEnd: pEndObj.price, startDate: pStartObj.date, endDate: pEndObj.date, status: "STALE_DATA" };
    }

    // Liquidity floor filters
    if (minAvgDollarVolume > 0 && pData.volumes && pData.volumes.length > 0) {
      const idxCurr = pCurrObj.index;
      const startIdx = Math.max(0, idxCurr - 19);
      let dollarVolSum = 0;
      let count = 0;
      for (let i = startIdx; i <= idxCurr; i++) {
        if (pData.volumes[i] && pData.prices[i]) {
          dollarVolSum += pData.prices[i] * pData.volumes[i];
          count++;
        }
      }
      const avgDollarVol = count > 0 ? dollarVolSum / count : 0;
      if (avgDollarVol < minAvgDollarVolume) {
        return { score: 0, pStart: pStartObj.price, pEnd: pEndObj.price, startDate: pStartObj.date, endDate: pEndObj.date, status: "FILTERED_OUT" };
      }
    }

    if (minMarketCap > 0) {
      const meta = metadata[ticker];
      const shares = meta?.sharesOutstanding;
      if (shares && shares > 0) {
        const mcap = pCurrObj.price * shares;
        if (mcap < minMarketCap) {
          return { score: 0, pStart: pStartObj.price, pEnd: pEndObj.price, startDate: pStartObj.date, endDate: pEndObj.date, status: "FILTERED_OUT" };
        }
      }
    }

    const rawReturn = (pEndObj.price - pStartObj.price) / pStartObj.price;
    let score = rawReturn;

    if (rankingMethod === "risk_adjusted") {
      // Return divided by trailing annualized volatility
      const sIdx = pStartObj.index;
      const eIdx = pEndObj.index;
      if (eIdx - sIdx >= 10) {
        const dailyRets: number[] = [];
        for (let i = sIdx + 1; i <= eIdx; i++) {
          dailyRets.push((pData.prices[i] - pData.prices[i - 1]) / pData.prices[i - 1]);
        }
        const mean = dailyRets.reduce((a, b) => a + b, 0) / dailyRets.length;
        const variance = dailyRets.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (dailyRets.length - 1);
        const std = Math.sqrt(variance);
        const annVol = std * Math.sqrt(252);
        if (annVol > 0.0001) {
          score = rawReturn / annVol;
        }
      }
    }

    return {
      score,
      pStart: pStartObj.price,
      pEnd: pEndObj.price,
      startDate: pStartObj.date,
      endDate: pEndObj.date,
      status: "VALID"
    };
  };

  const rebalanceSet = new Set(rebalanceDates);

  // 5. Daily Simulation Loop
  for (let dayIdx = 0; dayIdx < tradingDays.length; dayIdx++) {
    const currentDate = tradingDays[dayIdx];

    // Check if rebalance day
    if (rebalanceSet.has(currentDate)) {
      // Calculate current total portfolio value before rebalance
      let currentVal = cash;
      for (const [t, pos] of currentPositions.entries()) {
        const pData = tickerPrices.get(t);
        const lastP = pData ? getLastPriceBefore(pData, currentDate)?.price : pos.entryPrice;
        const p = lastP ?? pos.entryPrice;
        if (pos.action === "LONG") {
          currentVal += pos.shares * p;
        } else {
          // Short: value = entryVal + (entryVal - currentVal)
          currentVal += pos.shares * (2 * pos.entryPrice - p);
        }
      }

      // Check market regime filter
      let exposureScale = 1.0;
      if (regimeFilter) {
        const spyPrice = spyData.dateMap.get(currentDate) || 0;
        const spy200 = getSpy200Sma(currentDate);
        if (spy200 !== null && spyPrice < spy200) {
          exposureScale = regimeReducedExposurePct;
        }
      }

      // Evaluate momentum scores for active universe
      const candidates: { ticker: string; score: number; sector: string; issuer: string; price: number }[] = [];

      for (const ticker of universeTickers) {
        if (ticker === "SPY") continue;
        const res = computeMomentum(ticker, currentDate);
        if (res.status === "VALID") {
          const pData = tickerPrices.get(ticker)!;
          const currP = getLastPriceBefore(pData, currentDate)?.price || 0;
          if (currP > 0) {
            const sec = metadata[ticker]?.sector || "Unknown";
            const issuer = getParentIssuer(ticker);
            candidates.push({ ticker, score: res.score, sector: sec, issuer, price: currP });
          }
        }
      }

      // Sort descending by score
      candidates.sort((a, b) => b.score - a.score);

      // Select top N respecting sector cap and issuer deduplication
      const selectedLong: typeof candidates = [];
      const sectorCounts: Record<string, number> = {};
      const seenIssuers = new Set<string>();

      for (const cand of candidates) {
        if (selectedLong.length >= positions) break;
        if (seenIssuers.has(cand.issuer)) continue;
        if (maxPositionsPerSector > 0 && (sectorCounts[cand.sector] || 0) >= maxPositionsPerSector) {
          continue;
        }

        selectedLong.push(cand);
        seenIssuers.add(cand.issuer);
        sectorCounts[cand.sector] = (sectorCounts[cand.sector] || 0) + 1;
      }

      // Execute trades
      const newTickersSet = new Set(selectedLong.map(c => c.ticker));
      const exitedTickers: string[] = [];

      // Sell positions no longer held
      for (const [t, pos] of Array.from(currentPositions.entries())) {
        if (!newTickersSet.has(t)) {
          const pData = tickerPrices.get(t);
          const p = pData ? (getLastPriceBefore(pData, currentDate)?.price || pos.entryPrice) : pos.entryPrice;
          tradeLogs.push({
            Date: currentDate,
            Ticker: t,
            Action: pos.action === "LONG" ? "SELL" : "COVER",
            Price: p,
            Shares: pos.shares,
            "Portfolio Value": currentVal
          });
          currentPositions.delete(t);
          exitedTickers.push(t);
        }
      }

      // Re-allocate capital
      const targetEquityCapital = currentVal * exposureScale;
      const targetDollarsPerPos = selectedLong.length > 0 ? targetEquityCapital / selectedLong.length : 0;

      const newPositions = new Map<string, { shares: number; entryPrice: number; action: "LONG" | "SHORT" }>();
      const snapshotDetails: RebalanceSnapshotDetail[] = [];
      let totalStockValue = 0;

      for (const cand of selectedLong) {
        const targetShares = targetDollarsPerPos / cand.price;
        const existing = currentPositions.get(cand.ticker);

        if (!existing) {
          tradeLogs.push({
            Date: currentDate,
            Ticker: cand.ticker,
            Action: "BUY",
            Price: cand.price,
            Shares: targetShares,
            "Portfolio Value": currentVal
          });
        }

        newPositions.set(cand.ticker, { shares: targetShares, entryPrice: cand.price, action: "LONG" });
        const posVal = targetShares * cand.price;
        totalStockValue += posVal;

        snapshotDetails.push({
          ticker: cand.ticker,
          shares: targetShares,
          price: cand.price,
          weight: currentVal > 0 ? posVal / currentVal : 0,
          value: posVal,
          momentumScore: cand.score,
          sector: cand.sector,
          action: "LONG"
        });
      }

      currentPositions = newPositions;
      cash = Math.max(0, currentVal - totalStockValue);

      rebalanceSnapshots.push({
        date: currentDate,
        signalDate: currentDate,
        portfolioValue: currentVal,
        cash,
        count: selectedLong.length,
        tickers: selectedLong.map(c => c.ticker),
        details: snapshotDetails,
        exitedTickers
      });
    }

    // Daily portfolio valuation
    let dailyPortfolioVal = cash;
    for (const [t, pos] of currentPositions.entries()) {
      const pData = tickerPrices.get(t);
      const p = pData ? (getLastPriceBefore(pData, currentDate)?.price || pos.entryPrice) : pos.entryPrice;
      dailyPortfolioVal += pos.shares * p;
    }

    const spyPrice = spyData.dateMap.get(currentDate) || spyStartPrice;
    const spyVal = spyInitialShares * spyPrice;

    portfolioHistory.push({
      Date: currentDate,
      "Portfolio Value": Math.round(dailyPortfolioVal * 100) / 100,
      Cash: Math.round(cash * 100) / 100
    });

    benchmarkHistory.push({
      Date: currentDate,
      "Portfolio Value": Math.round(spyVal * 100) / 100,
      Cash: 0
    });
  }

  // 6. Compute Comprehensive Metrics
  const startVal = portfolioHistory[0]?.["Portfolio Value"] || initialCapital;
  const endVal = portfolioHistory[portfolioHistory.length - 1]?.["Portfolio Value"] || startVal;
  const totalReturn = (endVal - startVal) / startVal;

  const numDays = daysBetween(tradingDays[0], tradingDays[tradingDays.length - 1]) || 1;
  const years = numDays / 365.25;
  const cagr = years > 0 && startVal > 0 ? Math.pow(endVal / startVal, 1.0 / years) - 1.0 : 0;

  // Max Drawdown calculation
  let peak = startVal;
  let maxDrawdown = 0;
  const drawdownHistory: number[] = [];

  for (const h of portfolioHistory) {
    const val = h["Portfolio Value"];
    if (val > peak) peak = val;
    const dd = peak > 0 ? (peak - val) / peak : 0;
    if (dd > maxDrawdown) maxDrawdown = dd;
    drawdownHistory.push(-dd);
  }

  // Daily Returns & Volatility
  const dailyReturns: number[] = [];
  for (let i = 1; i < portfolioHistory.length; i++) {
    const prev = portfolioHistory[i - 1]["Portfolio Value"];
    const curr = portfolioHistory[i]["Portfolio Value"];
    if (prev > 0) dailyReturns.push((curr - prev) / prev);
  }

  const meanRet = dailyReturns.length > 0 ? dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length : 0;
  const variance = dailyReturns.length > 1
    ? dailyReturns.reduce((a, b) => a + Math.pow(b - meanRet, 2), 0) / (dailyReturns.length - 1)
    : 0;
  const dailyVol = Math.sqrt(variance);
  const annualizedVol = dailyVol * Math.sqrt(252);
  const sharpe = annualizedVol > 0 ? (meanRet * 252 - 0.02) / annualizedVol : 0;

  // Benchmark Metrics
  const spyEnd = benchmarkHistory[benchmarkHistory.length - 1]?.["Portfolio Value"] || initialCapital;
  const spyTotalReturn = (spyEnd - initialCapital) / initialCapital;
  const spyCagr = years > 0 ? Math.pow(spyEnd / initialCapital, 1.0 / years) - 1.0 : 0;

  let spyPeak = initialCapital;
  let spyMaxDd = 0;
  const spyDrawdownHistory: number[] = [];
  const spyDailyReturns: number[] = [];

  for (let i = 0; i < benchmarkHistory.length; i++) {
    const val = benchmarkHistory[i]["Portfolio Value"];
    if (val > spyPeak) spyPeak = val;
    const dd = spyPeak > 0 ? (spyPeak - val) / spyPeak : 0;
    if (dd > spyMaxDd) spyMaxDd = dd;
    spyDrawdownHistory.push(-dd);

    if (i > 0) {
      const prev = benchmarkHistory[i - 1]["Portfolio Value"];
      if (prev > 0) spyDailyReturns.push((val - prev) / prev);
    }
  }

  const spyMean = spyDailyReturns.length > 0 ? spyDailyReturns.reduce((a, b) => a + b, 0) / spyDailyReturns.length : 0;
  const spyVar = spyDailyReturns.length > 1
    ? spyDailyReturns.reduce((a, b) => a + Math.pow(b - spyMean, 2), 0) / (spyDailyReturns.length - 1)
    : 0;
  const spyVol = Math.sqrt(spyVar) * Math.sqrt(252);
  const spySharpe = spyVol > 0 ? (spyMean * 252 - 0.02) / spyVol : 0;

  // Holding Period calculation
  const holdingDays: number[] = [];
  const buyDates = new Map<string, string[]>();
  for (const t of tradeLogs) {
    if (t.Action === "BUY") {
      const list = buyDates.get(t.Ticker) || [];
      list.push(t.Date);
      buyDates.set(t.Ticker, list);
    } else if (t.Action === "SELL") {
      const list = buyDates.get(t.Ticker);
      if (list && list.length > 0) {
        const bDate = list.shift()!;
        holdingDays.push(daysBetween(bDate, t.Date));
      }
    }
  }
  const avgHoldingDays = holdingDays.length > 0
    ? holdingDays.reduce((a, b) => a + b, 0) / holdingDays.length
    : 30.0;

  // 7. Verification Records for verifyDate
  const verificationDate = verifyDate || rebalanceDates[rebalanceDates.length - 1] || endDate;
  const verificationRecords: VerificationRecord[] = [];

  const rawCandidates: { ticker: string; score: number; pStart: number; pEnd: number; startDate: string; endDate: string; status: string }[] = [];

  for (const t of universeTickers) {
    const res = computeMomentum(t, verificationDate);
    rawCandidates.push({ ticker: t, ...res });
  }

  // Sort valid ones by score descending
  const validOnes = rawCandidates.filter(c => c.status === "VALID").sort((a, b) => b.score - a.score);
  const lastSnapTickers = new Set(rebalanceSnapshots[rebalanceSnapshots.length - 1]?.tickers || []);

  validOnes.forEach((c, idx) => {
    verificationRecords.push({
      Ticker: c.ticker,
      Rank: idx + 1,
      MomentumScore: c.score,
      Selected: lastSnapTickers.has(c.ticker) ? "LONG" : "NO",
      Start_Date: c.startDate,
      Start_Price: c.pStart,
      End_Date: c.endDate,
      End_Price: c.pEnd,
      Status: "VALID",
      Sector: metadata[c.ticker]?.sector,
      SharesOutstanding: metadata[c.ticker]?.sharesOutstanding
    });
  });

  const invalidOnes = rawCandidates.filter(c => c.status !== "VALID");
  invalidOnes.forEach(c => {
    verificationRecords.push({
      Ticker: c.ticker,
      Rank: null,
      MomentumScore: null,
      Selected: "NO",
      Start_Date: c.startDate || null,
      Start_Price: c.pStart || null,
      End_Date: c.endDate || null,
      End_Price: c.pEnd || null,
      Status: c.status as any,
      Sector: metadata[c.ticker]?.sector,
      SharesOutstanding: metadata[c.ticker]?.sharesOutstanding
    });
  });

  // 8. Generate SVG Chart Data URLs
  const chartPoints = portfolioHistory.map((h, i) => ({
    date: h.Date,
    strategy: h["Portfolio Value"],
    benchmark: benchmarkHistory[i]?.["Portfolio Value"]
  }));

  const drawdownPoints = portfolioHistory.map((h, i) => ({
    date: h.Date,
    strategy: drawdownHistory[i] || 0,
    benchmark: spyDrawdownHistory[i] || 0
  }));

  const equitySvg = generateSvgChart("Portfolio Equity Curve vs SPY Benchmark", chartPoints, false);
  const drawdownSvg = generateSvgChart("Drawdown Analysis vs SPY Benchmark", drawdownPoints, true);

  // 9. Write CSV artifacts to disk for user download
  const backtesterDir = path.join(process.cwd(), "backtester");
  if (!fs.existsSync(backtesterDir)) {
    fs.mkdirSync(backtesterDir, { recursive: true });
  }

  const tradesCsv = [
    "Date,Ticker,Action,Price,Shares,Portfolio Value",
    ...tradeLogs.map(t => `${t.Date},${t.Ticker},${t.Action},${t.Price},${t.Shares},${t["Portfolio Value"]}`)
  ].join("\n");
  fs.writeFileSync(path.join(backtesterDir, "trades.csv"), tradesCsv, "utf-8");

  const portCsv = [
    "Date,Portfolio Value,Cash",
    ...portfolioHistory.map(p => `${p.Date},${p["Portfolio Value"]},${p.Cash}`)
  ].join("\n");
  fs.writeFileSync(path.join(backtesterDir, "portfolio.csv"), portCsv, "utf-8");

  const verifCsv = [
    "Ticker,Rank,MomentumScore,Selected,Start_Date,Start_Price,End_Date,End_Price,Status",
    ...verificationRecords.map(v => `${v.Ticker},${v.Rank ?? ""},${v.MomentumScore ?? ""},${v.Selected},${v.Start_Date ?? ""},${v.Start_Price ?? ""},${v.End_Date ?? ""},${v.End_Price ?? ""},${v.Status}`)
  ].join("\n");
  fs.writeFileSync(path.join(backtesterDir, "verification.csv"), verifCsv, "utf-8");

  const result: BacktestResult = {
    metrics: {
      "Starting Capital": startVal,
      "Ending Capital": Math.round(endVal * 100) / 100,
      "Total Return": totalReturn,
      "Annualized Return (CAGR)": cagr,
      "Maximum Drawdown": maxDrawdown,
      "Volatility": annualizedVol,
      "Sharpe Ratio": sharpe,
      "Calmar Ratio": maxDrawdown > 0 ? cagr / maxDrawdown : 0,
      "Number of Trades": tradeLogs.length,
      "Average Holding Period (Days)": Math.round(avgHoldingDays * 10) / 10,
      "Benchmark Ticker": "SPY",
      "Benchmark Total Return": spyTotalReturn,
      "Benchmark CAGR": spyCagr,
      "Benchmark Max Drawdown": spyMaxDd,
      "Benchmark Volatility": spyVol,
      "Benchmark Sharpe Ratio": spySharpe,
      "Alpha vs Benchmark": cagr - spyCagr
    },
    config: {
      START_DATE: startDate,
      END_DATE: endDate,
      INITIAL_CAPITAL: initialCapital,
      POSITIONS: positions,
      LOOKBACK_MONTHS: lookbackMonths,
      SKIP_LAST_MONTH: skipLastMonth,
      INCLUDE_SHORTS: includeShorts,
      REBALANCE_FREQUENCY: rebalanceFreq,
      UNIVERSE_FILE: universe,
      VERIFY_DATE: verifyDate || null
    },
    portfolio_history: portfolioHistory,
    benchmark_history: benchmarkHistory,
    trades: tradeLogs,
    rebalance_snapshots: rebalanceSnapshots,
    verification_records: verificationRecords,
    files: {
      trades_csv: path.join(backtesterDir, "trades.csv"),
      portfolio_csv: path.join(backtesterDir, "portfolio.csv"),
      verification_csv: path.join(backtesterDir, "verification.csv")
    },
    images: {
      equity_curve: equitySvg,
      drawdown: drawdownSvg
    }
  };

  // Write output.json
  fs.writeFileSync(path.join(backtesterDir, "output.json"), JSON.stringify(result, null, 2), "utf-8");

  return result;
}

export function run6WayComparison(): any {
  const scenarios = [
    {
      name: "1. Baseline (All 5 Filters Off)",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 0,
        minAvgDollarVolume: 0,
        minMarketCap: 0,
        rankingMethod: "raw_return",
        regimeFilter: false
      }
    },
    {
      name: "2. Sector Cap Only (Max 3/Sector, Issuer-Deduped)",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 3,
        minAvgDollarVolume: 0,
        minMarketCap: 0,
        rankingMethod: "raw_return",
        regimeFilter: false
      }
    },
    {
      name: "3. Liquidity Floor Only ($30M Vol, $2B MktCap)",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 0,
        minAvgDollarVolume: 30000000,
        minMarketCap: 2000000000,
        rankingMethod: "raw_return",
        regimeFilter: false
      }
    },
    {
      name: "4. Risk-Adjusted Ranking Only (Sharpe Ranking)",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 0,
        minAvgDollarVolume: 0,
        minMarketCap: 0,
        rankingMethod: "risk_adjusted",
        regimeFilter: false
      }
    },
    {
      name: "5. Market Regime Filter Only (SPY 200d SMA)",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 0,
        minAvgDollarVolume: 0,
        minMarketCap: 0,
        rankingMethod: "raw_return",
        regimeFilter: true,
        regimeReducedExposurePct: 0.5
      }
    },
    {
      name: "6. All 5 Filters Combined",
      config: {
        startDate: "2025-07-31",
        endDate: "2026-08-04",
        initialCapital: 30000.0,
        universe: "russell1000.csv",
        positions: 10,
        rebalanceFreq: "monthly",
        skipLastMonth: true,
        lookbackMonths: 12,
        includeShorts: false,
        maxPositionsPerSector: 3,
        minAvgDollarVolume: 30000000,
        minMarketCap: 2000000000,
        rankingMethod: "risk_adjusted",
        regimeFilter: true,
        regimeReducedExposurePct: 0.5
      }
    }
  ];

  const results: any[] = [];
  const rawResults: any[] = [];

  for (const sc of scenarios) {
    const res = runBacktestEngine(sc.config);
    const metrics = res.metrics;
    const totalReturn = metrics["Total Return"] * 100;
    const sharpe = metrics["Sharpe Ratio"];
    const maxDdVal = metrics["Maximum Drawdown"] * 100;

    // Find peak and trough dates
    let peakVal = metrics["Starting Capital"];
    let peakDate = sc.config.startDate;
    let troughDate = sc.config.endDate;
    let currentDdMax = 0;

    for (const h of res.portfolio_history) {
      if (h["Portfolio Value"] > peakVal) {
        peakVal = h["Portfolio Value"];
        peakDate = h.Date;
      }
      const dd = peakVal > 0 ? (peakVal - h["Portfolio Value"]) / peakVal : 0;
      if (dd >= currentDdMax) {
        currentDdMax = dd;
        troughDate = h.Date;
      }
    }

    const ddStr = `-${maxDdVal.toFixed(2)}% (${peakDate} to ${troughDate})`;
    const monthsUnder10 = res.rebalance_snapshots.filter(s => s.count < 10).length;

    rawResults.push({
      scenario: sc.name,
      total_return: totalReturn,
      max_dd_val: maxDdVal,
      sharpe,
      dd_str: ddStr,
      months_under_10: monthsUnder10
    });

    results.push({
      Scenario: sc.name,
      "Total Return (%)": `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`,
      "Max Drawdown (Range)": ddStr,
      "Sharpe Ratio": sharpe.toFixed(2),
      "Months < 10 Pos": monthsUnder10
    });
  }

  const warnings: string[] = [];
  for (let i = 0; i < rawResults.length; i++) {
    for (let j = i + 1; j < rawResults.length; j++) {
      const r1 = rawResults[i];
      const r2 = rawResults[j];
      const retDiff = Math.abs(r1.total_return - r2.total_return);
      if (retDiff > 0.01) {
        const ddIdentical = Math.abs(r1.max_dd_val - r2.max_dd_val) < 0.001 && r1.dd_str === r2.dd_str;
        const sharpeIdentical = Math.abs(r1.sharpe - r2.sharpe) < 0.001;
        if (ddIdentical) {
          warnings.push(
            `Audit Notice: Scenario '${r1.scenario}' (${r1.total_return.toFixed(2)}%) and '${r2.scenario}' (${r2.total_return.toFixed(2)}%) share max drawdown trough date range.`
          );
        }
        if (sharpeIdentical) {
          warnings.push(
            `Notice: Scenario '${r1.scenario}' and '${r2.scenario}' have identical Sharpe ratio.`
          );
        }
      }
    }
  }

  const payload = {
    scenarios: results,
    rawResults,
    warnings,
    sanityCheckPassed: warnings.length === 0,
    timestamp: new Date().toISOString()
  };

  const comparisonJson = path.join(process.cwd(), "comparison.json");
  fs.writeFileSync(comparisonJson, JSON.stringify(payload, null, 2), "utf-8");

  return payload;
}
