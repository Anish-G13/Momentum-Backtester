import React, { useState, useEffect } from "react";
import { StrategyTester } from "./components/StrategyTester";
import {
  TrendingUp,
  BarChart3,
  Play,
  Download,
  RefreshCw,
  Sliders,
  Database,
  FileText,
  CheckCircle2,
  DollarSign,
  Calendar,
  ListFilter,
  Info,
  ShieldAlert,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  Layers,
  Code,
  Briefcase,
  Tag,
  ChevronDown,
  ChevronUp,
  Search,
  ArrowRight,
  History,
  Trash2,
  RotateCcw,
  FileSpreadsheet
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from "recharts";

interface ConfigState {
  startDate: string;
  endDate: string;
  initialCapital: number;
  positions: number;
  lookbackMonths: number;
  skipLastMonth: boolean;
  includeShorts: boolean;
  rebalanceFreq: string;
  universe: string;
  maxPositionsPerSector: number;
  minAvgDollarVolume: number;
  minMarketCap: number;
  rankingMethod: string;
  regimeFilter: boolean;
  regimeReducedExposurePct: number;
  earningsBlackoutDays: number;
  strategyMode: "momentum_only" | "multi_factor_composite";
  factorWeights: {
    momentum: number;
    quality: number;
    low_vol: number;
  };
}

interface BacktestMetrics {
  "Starting Capital": number;
  "Ending Capital": number;
  "Total Return": number;
  "Annualized Return (CAGR)": number;
  "Maximum Drawdown": number;
  "Volatility": number;
  "Sharpe Ratio": number;
  "Number of Trades": number;
  "Average Holding Period (Days)": number;
  "Benchmark Ticker"?: string;
  "Benchmark Total Return"?: number;
  "Benchmark CAGR"?: number;
  "Benchmark Max Drawdown"?: number;
  "Benchmark Volatility"?: number;
  "Benchmark Sharpe Ratio"?: number;
  "Alpha vs Benchmark"?: number;
}

interface TradeRecord {
  Date: string;
  Ticker: string;
  Action: string;
  Price: number;
  Shares: number;
  "Portfolio Value": number;
}

interface HistoryRecord {
  Date: string;
  "Portfolio Value": number;
  Cash: number;
}

interface HoldingsDetail {
  ticker: string;
  action: "NEW" | "RETAINED";
  shares: number;
  price: number;
  value: number;
  weight: number;
}

interface RebalanceSnapshot {
  date: string;
  count: number;
  portfolioValue: number;
  tickers: string[];
  details: HoldingsDetail[];
  exitedTickers: string[];
}

interface VerificationRecord {
  Ticker: string;
  Rank: number | null;
  MomentumScore: number | null;
  Selected: "LONG" | "SHORT" | "NO";
  Start_Date: string | null;
  Start_Price: number | null;
  End_Date: string | null;
  End_Price: number | null;
  Status: string;
}

interface RunLogEntry {
  id: string;
  timestamp: string;
  settings: {
    startDate: string;
    endDate: string;
    initialCapital: number;
    positions: number;
    lookbackMonths: number;
    skipLastMonth: boolean;
    includeShorts: boolean;
    rebalanceFreq: string;
    universe: string;
  };
  results: {
    endingCapital: number;
    totalReturn: number;
    cagr: number;
    maxDrawdown: number;
    sharpe: number;
  };
  spyComparison: {
    spyTotalReturn: number;
    spyCagr: number;
    alphaVsSpy: number;
    returnSpreadVsSpy: number;
    outperformed: boolean;
  };
}

interface BacktestResults {
  metrics: BacktestMetrics;
  portfolio_history: HistoryRecord[];
  benchmark_history: HistoryRecord[];
  trades: TradeRecord[];
  rebalance_snapshots?: RebalanceSnapshot[];
  verification_date?: string;
  verification_records?: VerificationRecord[];
  images?: {
    equity_curve?: string;
    drawdown?: string;
  };
  stdout?: string;
  logEntry?: RunLogEntry;
}

export default function App() {
  const [config, setConfig] = useState<ConfigState>({
    startDate: "2020-01-01",
    endDate: "2026-08-04",
    initialCapital: 30000,
    positions: 20,
    lookbackMonths: 12,
    skipLastMonth: true,
    includeShorts: false,
    rebalanceFreq: "monthly",
    universe: "sp500.csv",
    maxPositionsPerSector: 0,
    minAvgDollarVolume: 0,
    minMarketCap: 0,
    rankingMethod: "raw_return",
    regimeFilter: false,
    regimeReducedExposurePct: 0.5,
    earningsBlackoutDays: 0,
    strategyMode: "momentum_only",
    factorWeights: {
      momentum: 0.3333,
      quality: 0.3333,
      low_vol: 0.3333
    }
  });

  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "charts" | "rebalance" | "trades" | "portfolio" | "python" | "verification" | "tester" | "logs" | "comparison">("overview");

  // Comparison State
  const [comparisonLoading, setComparisonLoading] = useState<boolean>(false);
  const [comparisonData, setComparisonData] = useState<any | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  const runComparison = async () => {
    setComparisonLoading(true);
    setComparisonError(null);
    try {
      const res = await fetch("/api/run-comparison", { method: "POST" });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.details || errData.error || "Comparison run failed");
      }
      const data = await res.json();
      setComparisonData(data);
    } catch (err: any) {
      setComparisonError(err.message);
    } finally {
      setComparisonLoading(false);
    }
  };

  // Settings Run Log state
  const [runLogs, setRunLogs] = useState<RunLogEntry[]>([]);
  const [logSearch, setLogSearch] = useState<string>("");
  const [logSort, setLogSort] = useState<"newest" | "highest_value" | "highest_alpha">("newest");

  // Verification mode state
  const [verifyDateInput, setVerifyDateInput] = useState<string>("2025-07-31");
  const [verificationSearch, setVerificationSearch] = useState<string>("");
  const [verificationFilter, setVerificationFilter] = useState<string>("ALL");

  // Ticker universe state
  const [universe, setUniverse] = useState<string[]>([]);
  const [showUniverseModal, setShowUniverseModal] = useState<boolean>(false);
  const [editedUniverseText, setEditedUniverseText] = useState<string>("");
  const [tradeFilter, setTradeFilter] = useState<string>("");
  const [tradeActionFilter, setTradeActionFilter] = useState<string>("ALL");

  // Rebalance holdings state
  const [rebalanceSearch, setRebalanceSearch] = useState<string>("");
  const [rebalanceSort, setRebalanceSort] = useState<"desc" | "asc">("desc");
  const [expandedDates, setExpandedDates] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchUniverse();
    fetchRunLogs();
    runBacktest();
  }, []);

  const fetchRunLogs = async () => {
    try {
      const res = await fetch("/api/logs");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.logs)) {
          setRunLogs(data.logs);
        }
      }
    } catch (err) {
      console.error("Error fetching run logs:", err);
    }
  };

  const handleDeleteLog = async (id: string) => {
    try {
      const res = await fetch(`/api/logs/${id}`, { method: "DELETE" });
      if (res.ok) {
        fetchRunLogs();
      }
    } catch (err) {
      console.error("Error deleting log entry:", err);
    }
  };

  const handleClearLogs = async () => {
    if (!window.confirm("Are you sure you want to clear all logged backtest settings and results?")) return;
    try {
      const res = await fetch("/api/logs", { method: "DELETE" });
      if (res.ok) {
        setRunLogs([]);
      }
    } catch (err) {
      console.error("Error clearing logs:", err);
    }
  };

  const handleLoadLogSettings = (log: RunLogEntry) => {
    const loadedConfig: ConfigState = {
      ...config,
      startDate: log.settings.startDate,
      endDate: log.settings.endDate,
      initialCapital: log.settings.initialCapital,
      positions: log.settings.positions,
      lookbackMonths: log.settings.lookbackMonths,
      skipLastMonth: log.settings.skipLastMonth,
      includeShorts: log.settings.includeShorts,
      rebalanceFreq: log.settings.rebalanceFreq,
      universe: log.settings.universe
    };
    setConfig(loadedConfig);
    fetchUniverse(log.settings.universe);
    runBacktest(loadedConfig);
    setActiveTab("overview");
  };

  const fetchUniverse = async (univFile?: string) => {
    const targetFile = univFile || config.universe;
    try {
      const res = await fetch(`/api/universe?universe=${encodeURIComponent(targetFile)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.tickers) {
          setUniverse(data.tickers);
          setEditedUniverseText(data.tickers.join(", "));
        }
      }
    } catch (err) {
      console.error("Error fetching universe:", err);
    }
  };

  const runBacktest = async (customCfg?: ConfigState, customVerifyDate?: string) => {
    setLoading(true);
    setError(null);
    const targetConfig = customCfg || config;
    const targetVerifyDate = customVerifyDate || verifyDateInput;

    try {
      const res = await fetch("/api/run-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          startDate: targetConfig.startDate,
          endDate: targetConfig.endDate,
          initialCapital: Number(targetConfig.initialCapital),
          positions: Number(targetConfig.positions),
          lookbackMonths: Number(targetConfig.lookbackMonths),
          skipLastMonth: targetConfig.skipLastMonth,
          includeShorts: targetConfig.includeShorts,
          rebalanceFreq: targetConfig.rebalanceFreq,
          universe: targetConfig.universe,
          verifyDate: targetVerifyDate,
          maxPositionsPerSector: Number(targetConfig.maxPositionsPerSector),
          minAvgDollarVolume: Number(targetConfig.minAvgDollarVolume),
          minMarketCap: Number(targetConfig.minMarketCap),
          rankingMethod: targetConfig.rankingMethod,
          regimeFilter: targetConfig.regimeFilter,
          regimeReducedExposurePct: Number(targetConfig.regimeReducedExposurePct),
          earningsBlackoutDays: Number(targetConfig.earningsBlackoutDays),
          strategyMode: targetConfig.strategyMode,
          factorWeights: targetConfig.factorWeights
        })
      });

      const contentType = res.headers.get("content-type") || "";
      let data: any = {};
      if (contentType.includes("application/json")) {
        data = await res.json();
      } else {
        const text = await res.text();
        throw new Error(`Server returned non-JSON response (${res.status}): ${text.slice(0, 150)}`);
      }

      if (!res.ok || data.error) {
        throw new Error(data.details || data.error || "Failed to execute backtest");
      }

      setResults(data);
      fetchRunLogs();
    } catch (err: any) {
      console.error("Backtest error:", err);
      setError(err.message || "Failed to execute python backtester");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadVerification = () => {
    window.open("/api/download/verification.csv", "_blank");
  };

  const handleSaveUniverse = async () => {
    try {
      const rawList = editedUniverseText.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
      const res = await fetch("/api/universe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tickers: rawList, universe: config.universe })
      });
      if (res.ok) {
        setUniverse(rawList);
        setShowUniverseModal(false);
        // Re-run backtest with updated universe
        runBacktest();
      }
    } catch (err) {
      console.error("Failed to save universe:", err);
    }
  };

  const triggerDownload = (content: string | Blob, filename: string, mimeType = "text/csv;charset=utf-8;") => {
    const blob = typeof content === "string" ? new Blob([content], { type: mimeType }) : content;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleDownloadImage = (base64Url: string | undefined, filename: string) => {
    if (!base64Url) return;
    const a = document.createElement("a");
    a.href = base64Url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleDownloadTrades = async () => {
    // In-memory generation guarantees clean CSV without proxy/cookie HTML page
    if (results?.trades && results.trades.length > 0) {
      const headers = ["Date", "Ticker", "Action", "Price", "Shares", "Portfolio Value"];
      const rows = [
        headers.join(","),
        ...results.trades.map(t =>
          [t.Date, t.Ticker, t.Action, t.Price, t.Shares, t["Portfolio Value"]].join(",")
        )
      ];
      triggerDownload(rows.join("\n"), "trades.csv");
      return;
    }

    try {
      const res = await fetch("/api/download/trades.csv");
      const text = await res.text();
      if (res.ok && !text.startsWith("<!DOCTYPE") && !text.includes("<html")) {
        triggerDownload(text, "trades.csv");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDownloadPortfolio = async () => {
    // In-memory generation guarantees clean CSV without proxy/cookie HTML page
    if (results?.portfolio_history && results.portfolio_history.length > 0) {
      const headers = ["Date", "Portfolio Value", "Cash"];
      const rows = [
        headers.join(","),
        ...results.portfolio_history.map(p =>
          [p.Date, p["Portfolio Value"], p.Cash].join(",")
        )
      ];
      triggerDownload(rows.join("\n"), "portfolio.csv");
      return;
    }

    try {
      const res = await fetch("/api/download/portfolio.csv");
      const text = await res.text();
      if (res.ok && !text.startsWith("<!DOCTYPE") && !text.includes("<html")) {
        triggerDownload(text, "portfolio.csv");
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Merge portfolio and benchmark histories for Recharts
  const mergedChartData = React.useMemo(() => {
    if (!results || !results.portfolio_history) return [];

    const bmMap = new Map<string, number>();
    if (results.benchmark_history) {
      results.benchmark_history.forEach(item => {
        bmMap.set(item.Date, item["Portfolio Value"]);
      });
    }

    const peakMap = { strategy: 0 };
    let lastBmVal = config.initialCapital;

    return results.portfolio_history.map(item => {
      const strategyVal = item["Portfolio Value"];
      if (strategyVal > peakMap.strategy) peakMap.strategy = strategyVal;
      const drawdown = peakMap.strategy > 0 ? ((strategyVal - peakMap.strategy) / peakMap.strategy) * 100 : 0;

      const bmVal = bmMap.get(item.Date);
      if (bmVal !== undefined && bmVal > 0) {
        lastBmVal = bmVal;
      }

      return {
        date: item.Date,
        Strategy: Math.round(strategyVal),
        Benchmark: Math.round(lastBmVal),
        Cash: Math.round(item.Cash),
        Drawdown: Number(drawdown.toFixed(2))
      };
    });
  }, [results, config.initialCapital]);

  const filteredTrades = React.useMemo(() => {
    if (!results || !results.trades) return [];
    return results.trades.filter(t => {
      const matchesTicker = !tradeFilter || t.Ticker.toLowerCase().includes(tradeFilter.toLowerCase());
      const matchesAction = tradeActionFilter === "ALL" || t.Action === tradeActionFilter;
      return matchesTicker && matchesAction;
    });
  }, [results, tradeFilter, tradeActionFilter]);

  const rebalanceSnapshots = React.useMemo<RebalanceSnapshot[]>(() => {
    if (results?.rebalance_snapshots && results.rebalance_snapshots.length > 0) {
      return results.rebalance_snapshots;
    }
    return [];
  }, [results]);

  const filteredRebalanceSnapshots = React.useMemo(() => {
    let list = [...rebalanceSnapshots];
    if (rebalanceSearch.trim()) {
      const query = rebalanceSearch.trim().toLowerCase();
      list = list.filter(snap =>
        snap.tickers.some(t => t.toLowerCase().includes(query)) ||
        snap.exitedTickers.some(t => t.toLowerCase().includes(query)) ||
        snap.date.includes(query)
      );
    }

    if (rebalanceSort === "desc") {
      list.sort((a, b) => (a.date < b.date ? 1 : -1));
    } else {
      list.sort((a, b) => (a.date > b.date ? 1 : -1));
    }
    return list;
  }, [rebalanceSnapshots, rebalanceSearch, rebalanceSort]);

  const filteredVerificationRecords = React.useMemo(() => {
    if (!results || !results.verification_records) return [];
    return results.verification_records.filter(rec => {
      if (verificationSearch) {
        const q = verificationSearch.trim().toLowerCase();
        const matchTicker = rec.Ticker.toLowerCase().includes(q);
        const matchStatus = rec.Status.toLowerCase().includes(q);
        const matchDate = (rec.Start_Date || "").includes(q) || (rec.End_Date || "").includes(q);
        if (!matchTicker && !matchStatus && !matchDate) return false;
      }
      if (verificationFilter === "LONG") return rec.Selected === "LONG";
      if (verificationFilter === "SHORT") return rec.Selected === "SHORT";
      if (verificationFilter === "SELECTED") return rec.Selected === "LONG" || rec.Selected === "SHORT";
      if (verificationFilter === "TOP20") return rec.Rank !== null && rec.Rank <= 20;
      if (verificationFilter === "VALID") return rec.Status === "VALID";
      if (verificationFilter === "SKIPPED") return rec.Status !== "VALID";
      return true;
    }
  )}, [results, verificationSearch, verificationFilter]);

  const filteredRunLogs = React.useMemo(() => {
    let list = [...runLogs];
    if (logSearch.trim()) {
      const q = logSearch.trim().toLowerCase();
      list = list.filter(l =>
        l.id.toLowerCase().includes(q) ||
        l.settings.universe.toLowerCase().includes(q) ||
        l.settings.startDate.includes(q) ||
        l.settings.endDate.includes(q) ||
        l.settings.rebalanceFreq.toLowerCase().includes(q)
      );
    }

    if (logSort === "highest_value") {
      list.sort((a, b) => b.results.endingCapital - a.results.endingCapital);
    } else if (logSort === "highest_alpha") {
      list.sort((a, b) => b.spyComparison.alphaVsSpy - a.spyComparison.alphaVsSpy);
    } else {
      list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    }
    return list;
  }, [runLogs, logSearch, logSort]);

  const handleDownloadHoldings = () => {
    if (!rebalanceSnapshots || rebalanceSnapshots.length === 0) return;
    const headers = ["Rebalance Date", "Ticker", "Status", "Shares", "Price", "Position Value", "Weight %"];
    const rows = [headers.join(",")];

    rebalanceSnapshots.forEach(snap => {
      snap.details.forEach(d => {
        rows.push([
          snap.date,
          d.ticker,
          d.action,
          d.shares.toFixed(2),
          d.price.toFixed(2),
          d.value.toFixed(2),
          `${d.weight.toFixed(2)}%`
        ].join(","));
      });
    });

    triggerDownload(rows.join("\n"), "rebalance_holdings.csv");
  };

  const formatUsd = (val?: number) => {
    if (val === undefined || val === null) return "$0";
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(val);
  };

  const formatPct = (val?: number) => {
    if (val === undefined || val === null) return "0.0%";
    return `${(val * 100).toFixed(1)}%`;
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-emerald-500 selection:text-zinc-950">
      {/* Top Header */}
      <header className="border-b border-zinc-800/80 bg-zinc-900/60 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-lg text-zinc-100 tracking-tight flex items-center gap-2">
                Python Stock Momentum Backtester
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono font-medium">
                  Academic Momentum Engine
                </span>
              </h1>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => setActiveTab("logs")}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition flex items-center gap-1.5 cursor-pointer"
            >
              <History className="w-3.5 h-3.5 text-emerald-400" />
              Settings Log ({runLogs.length})
            </button>
            <button
              onClick={() => setShowUniverseModal(true)}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition flex items-center gap-1.5"
            >
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              Universe ({universe.length} Stocks)
            </button>
            <button
              onClick={handleDownloadTrades}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600/90 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-emerald-950/20 cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              trades.csv
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Answer Question Banner */}
        <section id="question-banner" className="p-6 rounded-2xl bg-gradient-to-r from-zinc-900 via-zinc-900/90 to-zinc-900 border border-zinc-800 shadow-xl relative overflow-hidden">
          <div className="absolute -right-12 -bottom-12 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 space-y-3">
            <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400 uppercase tracking-wider">
              <Info className="w-4 h-4" />
              <span>Core Backtest Question</span>
            </div>
            <p className="text-xl sm:text-2xl font-serif text-zinc-100 leading-snug">
              &ldquo;If I had invested <span className="text-emerald-400 font-sans font-bold">{formatUsd(config.initialCapital)}</span> on{" "}
              <span className="text-zinc-200 font-sans font-semibold">{config.startDate}</span> using this momentum strategy and rebalanced {config.rebalanceFreq}, what would my portfolio be worth today?&rdquo;
            </p>

            {results && results.metrics && (
              <div className="pt-2 flex flex-wrap items-center gap-4 text-sm">
                <div className="px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-semibold flex items-center gap-2">
                  <span>Today&apos;s Portfolio Value:</span>
                  <span className="text-lg font-bold text-white">{formatUsd(results.metrics["Ending Capital"])}</span>
                </div>
                <div className="px-4 py-2 rounded-xl bg-zinc-800/80 border border-zinc-700 text-zinc-300 flex items-center gap-2">
                  <span>Total Return:</span>
                  <span className="font-bold text-emerald-400">{formatPct(results.metrics["Total Return"])}</span>
                  {results.metrics["Benchmark Total Return"] !== undefined && (
                    <span className="text-xs text-zinc-400">
                      (vs SPY {formatPct(results.metrics["Benchmark Total Return"])})
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Strategy Configuration Form */}
        <section id="config-panel" className="p-6 rounded-2xl bg-zinc-900/80 border border-zinc-800/80 shadow-lg space-y-6">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
            <div className="flex items-center space-x-2">
              <Sliders className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-zinc-100">Backtest Strategy Parameters</h2>
            </div>
            {/* Presets */}
            <div className="flex items-center space-x-2">
              <span className="text-xs text-zinc-400 mr-1">Presets:</span>
              <button
                onClick={() => {
                  const newCfg = { ...config, startDate: "2020-01-01" };
                  setConfig(newCfg);
                  runBacktest(newCfg);
                }}
                className="px-2.5 py-1 rounded-md text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700"
              >
                2020-Present
              </button>
              <button
                onClick={() => {
                  const newCfg = { ...config, startDate: "2023-01-01" };
                  setConfig(newCfg);
                  runBacktest(newCfg);
                }}
                className="px-2.5 py-1 rounded-md text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700"
              >
                3 Years
              </button>
            </div>
          </div>

          {/* Strategy Execution Mode Toggle Switch */}
          <div className="p-4 rounded-xl bg-zinc-950 border border-emerald-500/30 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center space-x-2">
                <PieChart className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-zinc-100 uppercase tracking-wider">Strategy Execution Mode</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => setConfig({ ...config, strategyMode: "momentum_only" })}
                  className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 cursor-pointer ${
                    config.strategyMode === "momentum_only"
                      ? "bg-emerald-500 text-zinc-950 font-bold shadow-md shadow-emerald-500/20"
                      : "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700"
                  }`}
                >
                  <TrendingUp className="w-3.5 h-3.5" />
                  Momentum-Only Strategy
                </button>
                <button
                  type="button"
                  onClick={() => setConfig({ ...config, strategyMode: "multi_factor_composite" })}
                  className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 cursor-pointer ${
                    config.strategyMode === "multi_factor_composite"
                      ? "bg-emerald-500 text-zinc-950 font-bold shadow-md shadow-emerald-500/20"
                      : "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700"
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  Multi-Factor Composite Strategy
                </button>
              </div>
            </div>

            {config.strategyMode === "momentum_only" ? (
              <p className="text-xs text-zinc-400">
                <strong className="text-emerald-400">Pure Momentum Mode:</strong> Ranks stocks strictly by 12-1 month cross-sectional trailing return.
              </p>
            ) : (
              <div className="space-y-3 pt-2 border-t border-zinc-800">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-zinc-300">Factor Weights (Normalized Cross-Sectional Z-Score Combination):</span>
                  <button
                    type="button"
                    onClick={() => setConfig({ ...config, factorWeights: { momentum: 0.3333, quality: 0.3333, low_vol: 0.3333 } })}
                    className="text-[11px] text-emerald-400 hover:underline font-mono"
                  >
                    Reset Equal Weights (33/33/33)
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs text-zinc-400 flex justify-between">
                      <span>Momentum Weight:</span>
                      <span className="font-mono text-emerald-400 font-bold">{(config.factorWeights.momentum * 100).toFixed(0)}%</span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={Math.round(config.factorWeights.momentum * 100)}
                      onChange={e => {
                        const val = Number(e.target.value) / 100;
                        setConfig({
                          ...config,
                          factorWeights: { ...config.factorWeights, momentum: val }
                        });
                      }}
                      className="w-full accent-emerald-500"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-zinc-400 flex justify-between">
                      <span>Quality Weight (ROIC/ROE):</span>
                      <span className="font-mono text-emerald-400 font-bold">{(config.factorWeights.quality * 100).toFixed(0)}%</span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={Math.round(config.factorWeights.quality * 100)}
                      onChange={e => {
                        const val = Number(e.target.value) / 100;
                        setConfig({
                          ...config,
                          factorWeights: { ...config.factorWeights, quality: val }
                        });
                      }}
                      className="w-full accent-emerald-500"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-zinc-400 flex justify-between">
                      <span>Low Volatility Weight (1/Vol):</span>
                      <span className="font-mono text-emerald-400 font-bold">{(config.factorWeights.low_vol * 100).toFixed(0)}%</span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={Math.round(config.factorWeights.low_vol * 100)}
                      onChange={e => {
                        const val = Number(e.target.value) / 100;
                        setConfig({
                          ...config,
                          factorWeights: { ...config.factorWeights, low_vol: val }
                        });
                      }}
                      className="w-full accent-emerald-500"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {/* Start & End Date */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-zinc-400" />
                Start Date
              </label>
              <input
                type="date"
                value={config.startDate}
                onChange={e => setConfig({ ...config, startDate: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-zinc-400" />
                End Date
              </label>
              <input
                type="date"
                value={config.endDate}
                onChange={e => setConfig({ ...config, endDate: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Initial Capital */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5 text-zinc-400" />
                Initial Capital ($)
              </label>
              <input
                type="number"
                value={config.initialCapital}
                onChange={e => setConfig({ ...config, initialCapital: Number(e.target.value) })}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Top N Positions */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400 flex items-center justify-between">
                <span>Top N Positions ({config.positions})</span>
                <span className="text-[10px] text-zinc-500">Equal Weighted</span>
              </label>
              <input
                type="range"
                min={5}
                max={50}
                value={config.positions}
                onChange={e => setConfig({ ...config, positions: Number(e.target.value) })}
                className="w-full accent-emerald-500"
              />
            </div>

            {/* Lookback Months */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">
                Lookback Months: {config.lookbackMonths}m
              </label>
              <select
                value={config.lookbackMonths}
                onChange={e => setConfig({ ...config, lookbackMonths: Number(e.target.value) })}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              >
                <option value={3}>3 Months</option>
                <option value={6}>6 Months</option>
                <option value={12}>12 Months (Academic Default)</option>
                <option value={18}>18 Months</option>
                <option value={24}>24 Months</option>
              </select>
            </div>

            {/* Rebalance Frequency */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Rebalance Frequency</label>
              <select
                value={config.rebalanceFreq}
                onChange={e => setConfig({ ...config, rebalanceFreq: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              >
                <option value="monthly">Monthly (Last Trading Day)</option>
                <option value="quarterly">Quarterly</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>

            {/* Universe Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-zinc-400" />
                Ticker Universe
              </label>
              <select
                value={config.universe}
                onChange={e => {
                  const newUniv = e.target.value;
                  const newCfg = { ...config, universe: newUniv };
                  setConfig(newCfg);
                  fetchUniverse(newUniv);
                  runBacktest(newCfg);
                }}
                className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
              >
                <option value="sp500.csv">S&P 500 (~500 Stocks)</option>
                <option value="custom_momentum.csv">Custom Momentum Universe (Institutional Quality)</option>
                <option value="russell1000.csv">Russell 1000 (~1,000 Stocks)</option>
              </select>
            </div>

            {/* Skip Last Month Checkbox */}
            <div className="space-y-1.5 flex items-center justify-between pt-4 px-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
              <div>
                <span className="text-xs font-medium text-zinc-200 block">Skip Last Month</span>
                <span className="text-[10px] text-zinc-500 block">Filter 1m mean-reversion (12-1)</span>
              </div>
              <input
                type="checkbox"
                checked={config.skipLastMonth}
                onChange={e => setConfig({ ...config, skipLastMonth: e.target.checked })}
                className="w-4 h-4 rounded accent-emerald-500"
              />
            </div>

            {/* Include Short Leg Checkbox */}
            <div className="space-y-1.5 flex items-center justify-between pt-4 px-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
              <div>
                <span className="text-xs font-medium text-zinc-200 block">Include Short Leg</span>
                <span className="text-[10px] text-zinc-500 block">Long-Short dollar-neutral</span>
              </div>
              <input
                type="checkbox"
                checked={config.includeShorts}
                onChange={e => setConfig({ ...config, includeShorts: e.target.checked })}
                className="w-4 h-4 rounded accent-emerald-500"
              />
            </div>
          </div>

          {/* Institutional Risk Management & Quantitative Filters */}
          <div className="mt-5 pt-4 border-t border-zinc-800/80">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <ListFilter className="w-3.5 h-3.5 text-emerald-400" />
                Institutional Risk Management & Filters
              </span>
              <span className="text-[10px] text-zinc-500">Configure multi-layered risk controls</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {/* Sector Cap */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  Sector Cap: {config.maxPositionsPerSector > 0 ? `Max ${config.maxPositionsPerSector}/Sector` : "Disabled"}
                </label>
                <select
                  value={config.maxPositionsPerSector}
                  onChange={e => setConfig({ ...config, maxPositionsPerSector: Number(e.target.value) })}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value={0}>Disabled (No Sector Cap)</option>
                  <option value={2}>Max 2 per Sector</option>
                  <option value={3}>Max 3 per Sector</option>
                  <option value={4}>Max 4 per Sector</option>
                  <option value={5}>Max 5 per Sector</option>
                </select>
              </div>

              {/* Min Avg Dollar Volume */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  Min Dollar Vol ($M)
                </label>
                <select
                  value={config.minAvgDollarVolume}
                  onChange={e => setConfig({ ...config, minAvgDollarVolume: Number(e.target.value) })}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value={0}>Disabled ($0 Floor)</option>
                  <option value={10000000}>$10M / day</option>
                  <option value={20000000}>$20M / day</option>
                  <option value={30000000}>$30M / day (Default)</option>
                  <option value={50000000}>$50M / day</option>
                  <option value={100000000}>$100M / day</option>
                </select>
              </div>

              {/* Min Market Cap */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  Min Market Cap ($B)
                </label>
                <select
                  value={config.minMarketCap}
                  onChange={e => setConfig({ ...config, minMarketCap: Number(e.target.value) })}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value={0}>Disabled ($0 Floor)</option>
                  <option value={1000000000}>$1 Billion</option>
                  <option value={2000000000}>$2 Billion (Large Cap)</option>
                  <option value={5000000000}>$5 Billion</option>
                  <option value={10000000000}>$10 Billion (Mega Cap)</option>
                </select>
              </div>

              {/* Ranking Method */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  Ranking Metric
                </label>
                <select
                  value={config.rankingMethod}
                  onChange={e => setConfig({ ...config, rankingMethod: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value="raw_return">Raw Return % (Standard)</option>
                  <option value="risk_adjusted">Risk-Adjusted (Return / Volatility)</option>
                </select>
              </div>

              {/* Market Regime Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  SPY 200d SMA Regime
                </label>
                <select
                  value={config.regimeFilter ? String(config.regimeReducedExposurePct) : "false"}
                  onChange={e => {
                    const val = e.target.value;
                    if (val === "false") {
                      setConfig({ ...config, regimeFilter: false });
                    } else {
                      setConfig({ ...config, regimeFilter: true, regimeReducedExposurePct: Number(val) });
                    }
                  }}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value="false">Disabled (100% Invested Always)</option>
                  <option value="0">100% Cash when SPY &lt; 200 SMA</option>
                  <option value="0.25">25% Exposure when SPY &lt; 200 SMA</option>
                  <option value="0.5">50% Exposure when SPY &lt; 200 SMA</option>
                </select>
              </div>

              {/* Earnings Blackout Window */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400 block">
                  Earnings Blackout
                </label>
                <select
                  value={config.earningsBlackoutDays}
                  onChange={e => setConfig({ ...config, earningsBlackoutDays: Number(e.target.value) })}
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value={0}>Disabled</option>
                  <option value={3}>3 Days Around Earnings</option>
                  <option value={5}>5 Days Around Earnings</option>
                  <option value={7}>7 Days Around Earnings</option>
                </select>
              </div>
            </div>
          </div>

          {/* Execute Button Bar */}
          <div className="mt-5 pt-3 border-t border-zinc-800/80 flex items-center justify-end">
              <button
                onClick={() => runBacktest()}
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-sm transition flex items-center justify-center space-x-2 shadow-lg shadow-emerald-500/10 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Executing Python Engine...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    <span>Run Backtest Engine</span>
                  </>
                )}
              </button>
            </div>
        </section>

        {/* Error Notification */}
        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 flex items-start space-x-3 text-sm">
            <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Backtest Execution Error</p>
              <p className="text-xs opacity-90 mt-1 font-mono">{error}</p>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="border-b border-zinc-800 flex flex-wrap items-center gap-6 text-sm font-medium">
          <button
            onClick={() => setActiveTab("overview")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "overview"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Performance Overview
          </button>
          <button
            onClick={() => {
              setActiveTab("comparison");
              if (!comparisonData && !comparisonLoading) {
                runComparison();
              }
            }}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "comparison"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Layers className="w-4 h-4 text-emerald-400" />
            6-Way Risk Comparison
          </button>
          <button
            onClick={() => setActiveTab("rebalance")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "rebalance"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Briefcase className="w-4 h-4" />
            Holdings per Rebalance ({rebalanceSnapshots.length})
          </button>
          <button
            onClick={() => setActiveTab("charts")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "charts"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            Equity & Drawdown Charts
          </button>
          <button
            onClick={() => setActiveTab("trades")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "trades"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <ListFilter className="w-4 h-4" />
            Trade Logs ({results?.trades?.length || 0})
          </button>
          <button
            onClick={() => setActiveTab("portfolio")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "portfolio"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Layers className="w-4 h-4" />
            Portfolio History
          </button>
          <button
            onClick={() => setActiveTab("verification")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "verification"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            Verification Mode ({results?.verification_records?.length || 0})
          </button>
          <button
            onClick={() => setActiveTab("logs")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "logs"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <History className="w-4 h-4 text-emerald-400" />
            Settings Log ({runLogs.length})
          </button>
          <button
            onClick={() => setActiveTab("tester")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "tester"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Sliders className="w-4 h-4 text-indigo-400" />
            Strategy Tester
          </button>
          <button
            onClick={() => setActiveTab("python")}
            className={`pb-3 transition flex items-center gap-2 border-b-2 ${
              activeTab === "python"
                ? "border-emerald-500 text-emerald-400 font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Code className="w-4 h-4" />
            Python Architecture
          </button>
        </div>

        {/* TAB: STRATEGY TESTER */}
        {activeTab === "tester" && <StrategyTester />}

        {/* TAB: 6-WAY RISK FILTER COMPARISON */}
        {activeTab === "comparison" && (
          <div className="space-y-6">
            {/* Header Banner */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                    <Layers className="w-5 h-5 text-emerald-400" />
                    Six-Way Risk Filter Comparison Dashboard
                  </h3>
                  <p className="text-xs text-zinc-400 mt-1">
                    Evaluates all 6 risk filter configurations across identical initial capital ($30,000), date window, top 10 positions, monthly rebalancing, and universe.
                  </p>
                </div>

                <button
                  onClick={runComparison}
                  disabled={comparisonLoading}
                  className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs flex items-center gap-2 transition shadow-lg shadow-emerald-500/10 disabled:opacity-50 cursor-pointer"
                >
                  {comparisonLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Executing 6 Backtests...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-current" />
                      <span>Run 6-Way Comparison</span>
                    </>
                  )}
                </button>
              </div>

              {/* Sanity Check Audit Badge */}
              {comparisonData && (
                <div className="mt-4 pt-4 border-t border-zinc-800">
                  {comparisonData.sanityCheckPassed ? (
                    <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-400" />
                      <div>
                        <span className="font-semibold">Sanity Check Audit Passed: </span>
                        <span>All 6 scenario risk metrics independently calculated with zero cross-scenario state leak or caching artifacts.</span>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs space-y-1">
                      <div className="flex items-center gap-2 font-semibold">
                        <ShieldAlert className="w-4 h-4 flex-shrink-0 text-amber-400" />
                        <span>Sanity Check Flag / Red Flag Audit Notice:</span>
                      </div>
                      {comparisonData.warnings.map((w: string, idx: number) => (
                        <p key={idx} className="font-mono text-[11px] opacity-90 pl-6">• {w}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Error Message */}
            {comparisonError && (
              <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 flex items-start gap-3 text-sm">
                <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Comparison Execution Error</p>
                  <p className="text-xs opacity-90 mt-1 font-mono">{comparisonError}</p>
                </div>
              </div>
            )}

            {/* Comparison Table */}
            {comparisonData && comparisonData.scenarios && (
              <div className="rounded-2xl bg-zinc-900 border border-zinc-800 overflow-hidden shadow-xl">
                <div className="p-4 border-b border-zinc-800 bg-zinc-900/50 flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                    Six-Way Risk Filters Comparative Matrix
                  </h4>
                  <span className="text-xs text-zinc-500 font-mono">
                    Universe: Russell 1000 | $30k Start Capital | Top 10 Positions
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-zinc-950 text-zinc-400 uppercase text-[10px] tracking-wider border-b border-zinc-800">
                      <tr>
                        <th className="py-3.5 px-4 font-semibold">Scenario # & Filter Configuration</th>
                        <th className="py-3.5 px-4 font-semibold text-right">Total Return (%)</th>
                        <th className="py-3.5 px-4 font-semibold text-center">Max Drawdown (Peak to Trough Date Range)</th>
                        <th className="py-3.5 px-4 font-semibold text-right">Sharpe Ratio</th>
                        <th className="py-3.5 px-4 font-semibold text-center">Months &lt; 10 Pos</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/60">
                      {comparisonData.scenarios.map((row: any, idx: number) => {
                        const isBaseline = idx === 0;
                        const isAllCombined = idx === 5;
                        return (
                          <tr
                            key={idx}
                            className={`hover:bg-zinc-800/40 transition-colors ${
                              isBaseline ? "bg-zinc-900/40" : isAllCombined ? "bg-emerald-950/10" : ""
                            }`}
                          >
                            <td className="py-3.5 px-4 font-sans font-medium text-zinc-200 flex items-center gap-2">
                              {isBaseline && <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">Baseline</span>}
                              {isAllCombined && <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Combined</span>}
                              <span>{row.Scenario}</span>
                            </td>
                            <td className="py-3.5 px-4 text-right font-bold text-emerald-400">
                              {row["Total Return (%)"]}
                            </td>
                            <td className="py-3.5 px-4 text-center text-rose-400 font-mono text-[11px]">
                              {row["Max Drawdown (Range)"]}
                            </td>
                            <td className="py-3.5 px-4 text-right font-semibold text-zinc-200">
                              {row["Sharpe Ratio"]}
                            </td>
                            <td className="py-3.5 px-4 text-center text-zinc-400">
                              {row["Months < 10 Pos"]}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB: BACKTEST SETTINGS & PERFORMANCE LOG */}
        {activeTab === "logs" && (
          <div className="space-y-6">
            {/* Top Summary Banner */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                    <History className="w-5 h-5 text-emerald-400" />
                    Backtest Settings & Portfolio Performance Log
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Automatically records every tested configuration, resulting portfolio value, and percentage return vs SPY benchmark.
                  </p>
                </div>

                <div className="flex items-center space-x-3">
                  <a
                    href="/api/download/runs_log.csv"
                    download="runs_log.csv"
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-emerald-950/20 transition cursor-pointer"
                  >
                    <Download className="w-4 h-4" />
                    Download runs_log.csv
                  </a>
                  {runLogs.length > 0 && (
                    <button
                      onClick={handleClearLogs}
                      className="px-3 py-2 rounded-xl bg-zinc-800 hover:bg-red-950/40 hover:text-red-400 text-zinc-400 text-xs font-medium border border-zinc-700 transition flex items-center gap-1.5 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Clear History
                    </button>
                  )}
                </div>
              </div>

              {/* Summary Metrics Pills */}
              {runLogs.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                  <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                    <span className="text-[11px] text-zinc-400 block">Total Logged Runs</span>
                    <span className="text-base font-bold text-emerald-400 font-mono">{runLogs.length} Executions</span>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                    <span className="text-[11px] text-zinc-400 block">Peak Portfolio Value</span>
                    <span className="text-base font-bold text-zinc-100 font-mono">
                      {formatUsd(Math.max(...runLogs.map(l => l.results?.endingCapital || 0)))}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                    <span className="text-[11px] text-zinc-400 block">Highest Strategy Return</span>
                    <span className="text-base font-bold text-emerald-400 font-mono">
                      +{formatPct(Math.max(...runLogs.map(l => l.results?.totalReturn || 0)))}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                    <span className="text-[11px] text-zinc-400 block">Best Alpha Spread vs SPY</span>
                    <span className="text-base font-bold text-sky-400 font-mono">
                      +{formatPct(Math.max(...runLogs.map(l => l.spyComparison?.alphaVsSpy || 0)))}
                    </span>
                  </div>
                </div>
              )}

              {/* Search and Sort Filter Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-zinc-800">
                <div className="relative flex-1 min-w-[240px]">
                  <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search by universe, date range, frequency..."
                    value={logSearch}
                    onChange={e => setLogSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="flex items-center space-x-2">
                  <span className="text-xs text-zinc-400">Sort by:</span>
                  <button
                    onClick={() => setLogSort("newest")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-xl border transition cursor-pointer ${
                      logSort === "newest"
                        ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 font-semibold"
                        : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    Newest First
                  </button>
                  <button
                    onClick={() => setLogSort("highest_value")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-xl border transition cursor-pointer ${
                      logSort === "highest_value"
                        ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 font-semibold"
                        : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    Highest Value
                  </button>
                  <button
                    onClick={() => setLogSort("highest_alpha")}
                    className={`px-3 py-1.5 text-xs font-medium rounded-xl border transition cursor-pointer ${
                      logSort === "highest_alpha"
                        ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 font-semibold"
                        : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    Highest Alpha
                  </button>
                </div>
              </div>
            </div>

            {/* Log Cards List */}
            {filteredRunLogs.length === 0 ? (
              <div className="p-12 text-center rounded-2xl bg-zinc-900 border border-zinc-800 space-y-3">
                <History className="w-10 h-10 text-zinc-600 mx-auto" />
                <p className="text-sm font-semibold text-zinc-300">No backtest run logs found</p>
                <p className="text-xs text-zinc-500 max-w-md mx-auto">
                  Run a backtest using any strategy settings above. Every execution automatically records chosen settings, portfolio value, and SPY returns here.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredRunLogs.map(log => {
                  const dateStr = new Date(log.timestamp).toLocaleString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: "numeric",
                    minute: "2-digit"
                  });
                  const isOutperformed = log.spyComparison?.outperformed;

                  return (
                    <div
                      key={log.id}
                      className="p-5 rounded-2xl bg-zinc-900/90 border border-zinc-800 hover:border-zinc-700 transition space-y-4 shadow-xl"
                    >
                      {/* Card Header */}
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
                        <div className="flex items-center space-x-3">
                          <span className="text-xs font-mono text-zinc-400 flex items-center gap-1.5">
                            <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                            {dateStr}
                          </span>
                          <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1 ${
                            isOutperformed
                              ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400"
                              : "bg-amber-500/10 border border-amber-500/30 text-amber-400"
                          }`}>
                            {isOutperformed ? (
                              <>
                                <ArrowUpRight className="w-3 h-3" />
                                Outperformed SPY (+{formatPct(log.spyComparison?.alphaVsSpy)} Alpha)
                              </>
                            ) : (
                              <>
                                <ArrowDownRight className="w-3 h-3" />
                                Underperformed SPY
                              </>
                            )}
                          </span>
                        </div>

                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => handleLoadLogSettings(log)}
                            className="px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-emerald-500/10 cursor-pointer"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>Load Settings & Rerun</span>
                          </button>
                          <button
                            onClick={() => handleDeleteLog(log.id)}
                            className="p-1.5 rounded-lg bg-zinc-800 hover:bg-red-950/50 text-zinc-400 hover:text-red-400 transition cursor-pointer"
                            title="Delete log entry"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      {/* Main Grid: Settings vs Performance */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-1">
                        {/* Chosen Settings Column */}
                        <div className="space-y-3 bg-zinc-950/60 p-4 rounded-xl border border-zinc-800/60">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                            <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                            Chosen Strategy Settings
                          </h4>

                          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Ticker Universe</span>
                              <span className="font-bold text-emerald-400">{log.settings?.universe}</span>
                            </div>
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Start & End Date</span>
                              <span className="text-zinc-200">{log.settings?.startDate} → {log.settings?.endDate}</span>
                            </div>
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Initial Capital</span>
                              <span className="font-bold text-zinc-100">{formatUsd(log.settings?.initialCapital)}</span>
                            </div>
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Top N Positions</span>
                              <span className="text-zinc-200">{log.settings?.positions} Stocks</span>
                            </div>
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Lookback & Skip</span>
                              <span className="text-zinc-200">{log.settings?.lookbackMonths}-1m {log.settings?.skipLastMonth ? "(Skip t-1)" : "(No Skip)"}</span>
                            </div>
                            <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800/60">
                              <span className="text-[10px] text-zinc-500 block font-sans">Rebalance & Type</span>
                              <span className="text-zinc-200 capitalize">{log.settings?.rebalanceFreq} {log.settings?.includeShorts ? "(L/S)" : "(Long Only)"}</span>
                            </div>
                          </div>
                        </div>

                        {/* Resulting Portfolio Value & SPY Comparison Column */}
                        <div className="space-y-3 bg-zinc-950/60 p-4 rounded-xl border border-zinc-800/60">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                            Portfolio Value & Returns vs SPY
                          </h4>

                          <div className="space-y-2">
                            {/* Final Value Banner */}
                            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between">
                              <div>
                                <span className="text-[11px] text-emerald-400/90 block font-medium">Resulting Portfolio Value</span>
                                <span className="text-xl font-extrabold text-white font-mono">{formatUsd(log.results?.endingCapital)}</span>
                              </div>
                              <div className="text-right">
                                <span className="text-[11px] text-zinc-400 block">Total Strategy Return</span>
                                <span className="text-lg font-bold text-emerald-400 font-mono">+{formatPct(log.results?.totalReturn)}</span>
                              </div>
                            </div>

                            {/* Side-by-side performance grid */}
                            <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono pt-1">
                              <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                                <span className="text-[10px] text-zinc-500 block font-sans">Strategy CAGR</span>
                                <span className="font-bold text-emerald-400">{formatPct(log.results?.cagr)}</span>
                              </div>
                              <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                                <span className="text-[10px] text-zinc-500 block font-sans">SPY Return</span>
                                <span className="font-bold text-zinc-300">+{formatPct(log.spyComparison?.spyTotalReturn)}</span>
                              </div>
                              <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                                <span className="text-[10px] text-zinc-500 block font-sans">Net Spread vs SPY</span>
                                <span className="font-bold text-emerald-400">
                                  +{formatPct(log.spyComparison?.returnSpreadVsSpy)}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 1: OVERVIEW */}
        {activeTab === "overview" && results && (
          <div className="space-y-8">
            {/* Key Metrics Cards Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">Starting Capital</span>
                <span className="text-lg font-bold text-zinc-100">{formatUsd(results.metrics["Starting Capital"])}</span>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">Ending Capital</span>
                <span className="text-lg font-bold text-emerald-400">{formatUsd(results.metrics["Ending Capital"])}</span>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">Total Return</span>
                <span className="text-lg font-bold text-emerald-400">{formatPct(results.metrics["Total Return"])}</span>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">CAGR (Ann. Return)</span>
                <span className="text-lg font-bold text-zinc-100">{formatPct(results.metrics["Annualized Return (CAGR)"])}</span>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">Max Drawdown</span>
                <span className="text-lg font-bold text-red-400">-{formatPct(results.metrics["Maximum Drawdown"])}</span>
              </div>

              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1">
                <span className="text-xs text-zinc-400 block">Sharpe Ratio</span>
                <span className="text-lg font-bold text-sky-400">{results.metrics["Sharpe Ratio"]?.toFixed(2)}</span>
              </div>
            </div>

            {/* Benchmark Side-by-Side Comparison Table */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-zinc-100 flex items-center gap-2">
                  <PieChart className="w-5 h-5 text-emerald-400" />
                  Momentum Strategy vs SPY Benchmark Comparison
                </h3>
                {results.metrics["Alpha vs Benchmark"] !== undefined && (
                  <span className="text-xs px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold">
                    Alpha Spread: +{formatPct(results.metrics["Alpha vs Benchmark"])}
                  </span>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-zinc-300">
                  <thead className="bg-zinc-950 text-zinc-400 text-xs uppercase tracking-wider border-b border-zinc-800">
                    <tr>
                      <th className="py-3 px-4">Performance Metric</th>
                      <th className="py-3 px-4 text-emerald-400 font-bold">Momentum Strategy</th>
                      <th className="py-3 px-4 text-zinc-400">SPY Benchmark</th>
                      <th className="py-3 px-4 text-right">Spread / Difference</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 font-mono">
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Total Return</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">{formatPct(results.metrics["Total Return"])}</td>
                      <td className="py-3 px-4">{formatPct(results.metrics["Benchmark Total Return"])}</td>
                      <td className="py-3 px-4 text-right text-emerald-400 font-bold">
                        +{formatPct((results.metrics["Total Return"] || 0) - (results.metrics["Benchmark Total Return"] || 0))}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Annualized Return (CAGR)</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">{formatPct(results.metrics["Annualized Return (CAGR)"])}</td>
                      <td className="py-3 px-4">{formatPct(results.metrics["Benchmark CAGR"])}</td>
                      <td className="py-3 px-4 text-right text-emerald-400">
                        +{formatPct((results.metrics["Annualized Return (CAGR)"] || 0) - (results.metrics["Benchmark CAGR"] || 0))}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Maximum Drawdown</td>
                      <td className="py-3 px-4 text-red-400 font-bold">-{formatPct(results.metrics["Maximum Drawdown"])}</td>
                      <td className="py-3 px-4 text-zinc-400">-{formatPct(results.metrics["Benchmark Max Drawdown"])}</td>
                      <td className="py-3 px-4 text-right text-zinc-400">
                        {formatPct((results.metrics["Benchmark Max Drawdown"] || 0) - (results.metrics["Maximum Drawdown"] || 0))}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Annualized Volatility</td>
                      <td className="py-3 px-4">{formatPct(results.metrics["Volatility"])}</td>
                      <td className="py-3 px-4">{formatPct(results.metrics["Benchmark Volatility"])}</td>
                      <td className="py-3 px-4 text-right text-zinc-400">
                        {formatPct((results.metrics["Volatility"] || 0) - (results.metrics["Benchmark Volatility"] || 0))}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Sharpe Ratio</td>
                      <td className="py-3 px-4 text-sky-400 font-bold">{results.metrics["Sharpe Ratio"]?.toFixed(2)}</td>
                      <td className="py-3 px-4">{results.metrics["Benchmark Sharpe Ratio"]?.toFixed(2)}</td>
                      <td className="py-3 px-4 text-right text-sky-400">
                        +{(results.metrics["Sharpe Ratio"]! - (results.metrics["Benchmark Sharpe Ratio"] || 0)).toFixed(2)}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 font-sans text-zinc-200">Total Trades Executed</td>
                      <td className="py-3 px-4">{results.metrics["Number of Trades"]} trades</td>
                      <td className="py-3 px-4 text-zinc-500">1 (Buy & Hold)</td>
                      <td className="py-3 px-4 text-right text-zinc-400">
                        Avg Hold: {results.metrics["Average Holding Period (Days)"]?.toFixed(1)} days
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recharts Quick Curve Preview */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <h3 className="text-base font-semibold text-zinc-100 flex items-center justify-between">
                <span>Interactive Equity Curve Growth ($)</span>
                <span className="text-xs text-zinc-400 font-mono">Daily Adjusted Close Rebalanced {config.rebalanceFreq}</span>
              </h3>
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mergedChartData} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="date" stroke="#71717a" fontSize={11} tickLine={false} />
                    <YAxis
                      stroke="#71717a"
                      fontSize={11}
                      tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                      domain={['auto', 'auto']}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46", borderRadius: "0.75rem" }}
                      formatter={(value: any) => [formatUsd(Number(value)), "Value"]}
                    />
                    <Legend wrapperStyle={{ paddingTop: "10px" }} />
                    <Line type="monotone" dataKey="Strategy" stroke="#10b981" strokeWidth={2.5} dot={false} name="Momentum Strategy" />
                    <Line type="monotone" dataKey="Benchmark" stroke="#71717a" strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="SPY Benchmark" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Latest Rebalance Snapshot Card in Overview */}
            {rebalanceSnapshots.length > 0 && (
              <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
                  <div>
                    <h3 className="text-base font-semibold text-zinc-100 flex items-center gap-2">
                      <Briefcase className="w-5 h-5 text-emerald-400" />
                      Latest Rebalance Holdings Snapshot ({rebalanceSnapshots[rebalanceSnapshots.length - 1].date})
                    </h3>
                    <p className="text-xs text-zinc-400 mt-0.5">
                      Showing {rebalanceSnapshots[rebalanceSnapshots.length - 1].count} active positions held after the most recent rebalance
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveTab("rebalance")}
                    className="px-3.5 py-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 border border-zinc-700 transition flex items-center gap-1.5 font-medium cursor-pointer"
                  >
                    <span>View All {rebalanceSnapshots.length} Rebalance Periods</span>
                    <ArrowRight className="w-3.5 h-3.5 text-emerald-400" />
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 pt-1">
                  {rebalanceSnapshots[rebalanceSnapshots.length - 1].details.map(d => (
                    <div key={d.ticker} className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold text-sm text-zinc-100">{d.ticker}</span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold ${
                          d.action === "NEW" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800 text-zinc-400"
                        }`}>
                          {d.action}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-zinc-400 font-mono">
                        <span>{d.shares.toFixed(1)} sh</span>
                        <span>{formatUsd(d.price)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB: REBALANCE HOLDINGS */}
        {activeTab === "rebalance" && (
          <div className="space-y-6">
            {/* Top Summary Header */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                    <Briefcase className="w-5 h-5 text-emerald-400" />
                    Holdings Currently Held After Every Rebalancing Period
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Track the exact set of stock ticker names held in your portfolio following each scheduled rebalance.
                  </p>
                </div>

                <div className="flex items-center space-x-3">
                  <button
                    onClick={handleDownloadHoldings}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-emerald-950/20 transition cursor-pointer"
                  >
                    <Download className="w-4 h-4" />
                    Download rebalance_holdings.csv
                  </button>
                </div>
              </div>

              {/* Metrics Pills */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                  <span className="text-[11px] text-zinc-400 block">Total Rebalance Periods</span>
                  <span className="text-base font-bold text-emerald-400 font-mono">{rebalanceSnapshots.length} Dates</span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                  <span className="text-[11px] text-zinc-400 block">Target Portfolio Size</span>
                  <span className="text-base font-bold text-zinc-100 font-mono">{config.positions} Positions</span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                  <span className="text-[11px] text-zinc-400 block">Unique Tickers Held</span>
                  <span className="text-base font-bold text-sky-400 font-mono">
                    {Array.from(new Set(rebalanceSnapshots.flatMap(s => s.tickers))).length} Stocks
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-zinc-950 border border-zinc-800/80">
                  <span className="text-[11px] text-zinc-400 block">Rebalance Frequency</span>
                  <span className="text-base font-bold text-amber-400 font-mono capitalize">{config.rebalanceFreq}</span>
                </div>
              </div>

              {/* Search and Sort Filter Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-zinc-800">
                <div className="relative flex-1 min-w-[240px]">
                  <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search ticker symbol (e.g. NVDA, PLTR, AAPL)..."
                    value={rebalanceSearch}
                    onChange={e => setRebalanceSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="flex items-center space-x-2">
                  <span className="text-xs text-zinc-400">Order:</span>
                  <button
                    onClick={() => setRebalanceSort(rebalanceSort === "desc" ? "asc" : "desc")}
                    className="px-3 py-2 text-xs font-mono font-medium rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-300 hover:border-zinc-700 transition flex items-center gap-1.5"
                  >
                    <span>{rebalanceSort === "desc" ? "Newest First" : "Oldest First"}</span>
                    {rebalanceSort === "desc" ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
            </div>

            {/* Rebalance Periods List */}
            {filteredRebalanceSnapshots.length === 0 ? (
              <div className="p-12 text-center rounded-2xl bg-zinc-900 border border-zinc-800 space-y-2">
                <Briefcase className="w-8 h-8 text-zinc-600 mx-auto" />
                <p className="text-sm font-semibold text-zinc-300">No rebalance periods matched your query</p>
                <p className="text-xs text-zinc-500">Try searching for a different ticker symbol or clearing your filter.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredRebalanceSnapshots.map((snap) => {
                  const isExpanded = !!expandedDates[snap.date];
                  const newCount = snap.details.filter(d => d.action === "NEW").length;
                  const retainedCount = snap.details.filter(d => d.action === "RETAINED").length;

                  return (
                    <div key={snap.date} className="p-5 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4 hover:border-zinc-700/80 transition shadow-lg">
                      {/* Period Header */}
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
                        <div className="flex items-center space-x-3">
                          <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-xs font-bold">
                            <Calendar className="w-4 h-4 inline mr-1.5" />
                            {snap.date}
                          </div>
                          <div>
                            <span className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                              {snap.count} Positions Held
                              <span className="text-xs font-normal text-zinc-400">
                                ({newCount} New, {retainedCount} Retained
                                {snap.exitedTickers.length > 0 && `, ${snap.exitedTickers.length} Exited`})
                              </span>
                            </span>
                            <span className="text-xs text-zinc-400 font-mono block">
                              Total Value: {formatUsd(snap.portfolioValue)}
                            </span>
                          </div>
                        </div>

                        <button
                          onClick={() => setExpandedDates(prev => ({ ...prev, [snap.date]: !prev[snap.date] }))}
                          className="px-3 py-1.5 text-xs font-medium rounded-xl bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition flex items-center gap-1.5 cursor-pointer"
                        >
                          <span>{isExpanded ? "Hide Details Table" : "View Details Table"}</span>
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                      </div>

                      {/* Active Tickers Chips Section */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs text-zinc-400 font-medium">
                          <span>Currently Held Stock Names ({snap.tickers.length}):</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {snap.details.map((d) => (
                            <div
                              key={d.ticker}
                              className={`px-3 py-2 rounded-xl border flex items-center space-x-2 transition ${
                                rebalanceSearch && d.ticker.toLowerCase().includes(rebalanceSearch.toLowerCase())
                                  ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 ring-2 ring-emerald-500/40"
                                  : "bg-zinc-950 border-zinc-800 text-zinc-200 hover:border-zinc-700"
                              }`}
                            >
                              <span className="font-mono font-bold text-sm tracking-wide text-zinc-100">{d.ticker}</span>
                              <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold ${
                                d.action === "NEW"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                              }`}>
                                {d.action}
                              </span>
                              <span className="text-[10px] text-zinc-400 font-mono">
                                {d.shares.toFixed(1)} sh
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Exited Positions (if any) */}
                      {snap.exitedTickers.length > 0 && (
                        <div className="flex items-center space-x-2 pt-1 text-xs">
                          <span className="text-zinc-500 font-medium">Exited this period:</span>
                          <div className="flex flex-wrap gap-1.5">
                            {snap.exitedTickers.map(t => (
                              <span key={t} className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                                - {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Expandable Table Details */}
                      {isExpanded && (
                        <div className="pt-3 border-t border-zinc-800/80">
                          <div className="overflow-x-auto rounded-xl border border-zinc-800">
                            <table className="w-full text-left text-xs text-zinc-300">
                              <thead className="bg-zinc-950 text-zinc-400 uppercase tracking-wider border-b border-zinc-800">
                                <tr>
                                  <th className="py-2.5 px-4">Ticker</th>
                                  <th className="py-2.5 px-4">Status</th>
                                  <th className="py-2.5 px-4">Shares</th>
                                  <th className="py-2.5 px-4">Rebalance Price</th>
                                  <th className="py-2.5 px-4">Position Value</th>
                                  <th className="py-2.5 px-4 text-right">Est. Weight %</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-zinc-800/50 font-mono">
                                {snap.details.map((d) => (
                                  <tr key={d.ticker} className="hover:bg-zinc-800/40">
                                    <td className="py-2 px-4 font-bold text-zinc-100">{d.ticker}</td>
                                    <td className="py-2 px-4">
                                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                        d.action === "NEW" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800 text-zinc-400"
                                      }`}>
                                        {d.action}
                                      </span>
                                    </td>
                                    <td className="py-2 px-4">{d.shares.toFixed(2)}</td>
                                    <td className="py-2 px-4">{formatUsd(d.price)}</td>
                                    <td className="py-2 px-4 text-emerald-400 font-bold">{formatUsd(d.value)}</td>
                                    <td className="py-2 px-4 text-right text-zinc-300">{d.weight.toFixed(1)}%</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: CHARTS */}
        {activeTab === "charts" && (
          <div className="space-y-8">
            {/* Interactive Recharts Area */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-6">
              <h3 className="text-lg font-bold text-zinc-100">Interactive Performance Visualizations</h3>

              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-emerald-400">1. Portfolio Value vs SPY Benchmark</h4>
                <div className="h-80 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={mergedChartData}>
                      <defs>
                        <linearGradient id="stratGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#71717a" fontSize={11} />
                      <YAxis stroke="#71717a" fontSize={11} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46" }}
                        formatter={(value: any) => [formatUsd(Number(value)), ""]}
                      />
                      <Area type="monotone" dataKey="Strategy" stroke="#10b981" fillOpacity={1} fill="url(#stratGrad)" strokeWidth={2} name="Momentum Strategy" />
                      <Line type="monotone" dataKey="Benchmark" stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="3 3" name="SPY Benchmark" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="space-y-3 pt-6 border-t border-zinc-800">
                <h4 className="text-sm font-semibold text-red-400">2. Portfolio Drawdown % (Underwater Chart)</h4>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={mergedChartData}>
                      <defs>
                        <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#71717a" fontSize={11} />
                      <YAxis stroke="#71717a" fontSize={11} tickFormatter={v => `${v}%`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46" }}
                        formatter={(value: any) => [`${value}%`, "Drawdown"]}
                      />
                      <Area type="monotone" dataKey="Drawdown" stroke="#ef4444" fillOpacity={1} fill="url(#ddGrad)" strokeWidth={1.5} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Generated Matplotlib PNG Charts */}
            {results?.images && (
              <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-emerald-400" />
                    Generated Matplotlib PNG Artifacts
                  </h3>
                  <div className="flex items-center space-x-3">
                    <button
                      onClick={() => handleDownloadImage(results?.images?.equity_curve, "equity_curve.png")}
                      className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 border border-zinc-700 flex items-center gap-1.5 cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      equity_curve.png
                    </button>
                    <button
                      onClick={() => handleDownloadImage(results?.images?.drawdown, "drawdown.png")}
                      className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 border border-zinc-700 flex items-center gap-1.5 cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      drawdown.png
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {results.images.equity_curve && (
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-zinc-400">equity_curve.png</p>
                      <img
                        src={results.images.equity_curve}
                        alt="Equity Curve"
                        className="w-full rounded-xl border border-zinc-800 bg-zinc-950"
                      />
                    </div>
                  )}
                  {results.images.drawdown && (
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-zinc-400">drawdown.png</p>
                      <img
                        src={results.images.drawdown}
                        alt="Drawdown"
                        className="w-full rounded-xl border border-zinc-800 bg-zinc-950"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: TRADES LOG */}
        {activeTab === "trades" && (
          <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-zinc-100">Trade Execution Log (trades.csv)</h3>
                <p className="text-xs text-zinc-400">
                  Showing {filteredTrades.length} of {results?.trades?.length || 0} executed rebalance transactions
                </p>
              </div>

              <div className="flex items-center space-x-3">
                <input
                  type="text"
                  placeholder="Filter ticker (e.g. NVDA)..."
                  value={tradeFilter}
                  onChange={e => setTradeFilter(e.target.value)}
                  className="px-3 py-1.5 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500"
                />
                <select
                  value={tradeActionFilter}
                  onChange={e => setTradeActionFilter(e.target.value)}
                  className="px-3 py-1.5 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500"
                >
                  <option value="ALL">All Actions</option>
                  <option value="BUY">BUY Only</option>
                  <option value="SELL">SELL Only</option>
                  <option value="SHORT">SHORT Only</option>
                  <option value="COVER">COVER Only</option>
                </select>

                <button
                  onClick={handleDownloadTrades}
                  className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 transition cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download trades.csv
                </button>
              </div>
            </div>

            <div className="overflow-x-auto max-h-[500px] border border-zinc-800 rounded-xl">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-zinc-400 uppercase tracking-wider sticky top-0 z-10 border-b border-zinc-800">
                  <tr>
                    <th className="py-2.5 px-4">Date</th>
                    <th className="py-2.5 px-4">Ticker</th>
                    <th className="py-2.5 px-4">Action</th>
                    <th className="py-2.5 px-4">Price</th>
                    <th className="py-2.5 px-4">Shares</th>
                    <th className="py-2.5 px-4 text-right">Portfolio Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50 font-mono">
                  {filteredTrades.map((t, idx) => (
                    <tr key={idx} className="hover:bg-zinc-800/40">
                      <td className="py-2 px-4 text-zinc-400">{t.Date}</td>
                      <td className="py-2 px-4 font-bold text-zinc-100">{t.Ticker}</td>
                      <td className="py-2 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            t.Action === "BUY"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : t.Action === "SELL"
                              ? "bg-red-500/10 text-red-400 border border-red-500/20"
                              : t.Action === "SHORT"
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              : "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                          }`}
                        >
                          {t.Action}
                        </span>
                      </td>
                      <td className="py-2 px-4">{formatUsd(t.Price)}</td>
                      <td className="py-2 px-4">{t.Shares.toFixed(2)}</td>
                      <td className="py-2 px-4 text-right font-bold text-zinc-200">{formatUsd(t["Portfolio Value"])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: PORTFOLIO HISTORY */}
        {activeTab === "portfolio" && (
          <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-zinc-100">Daily Portfolio Valuation History (portfolio.csv)</h3>
                <p className="text-xs text-zinc-400">
                  Total {results?.portfolio_history?.length || 0} trading days recorded
                </p>
              </div>

              <button
                onClick={handleDownloadPortfolio}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 transition cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                Download portfolio.csv
              </button>
            </div>

            <div className="overflow-x-auto max-h-[500px] border border-zinc-800 rounded-xl">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-zinc-400 uppercase tracking-wider sticky top-0 z-10 border-b border-zinc-800">
                  <tr>
                    <th className="py-2.5 px-4">Date</th>
                    <th className="py-2.5 px-4">Portfolio Value ($)</th>
                    <th className="py-2.5 px-4">Cash Balance ($)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50 font-mono">
                  {results?.portfolio_history?.map((row, idx) => (
                    <tr key={idx} className="hover:bg-zinc-800/40">
                      <td className="py-2 px-4 text-zinc-400">{row.Date}</td>
                      <td className="py-2 px-4 font-bold text-emerald-400">{formatUsd(row["Portfolio Value"])}</td>
                      <td className="py-2 px-4 text-zinc-300">{formatUsd(row.Cash)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 5: VERIFICATION MODE */}
        {activeTab === "verification" && (
          <div className="space-y-6">
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
                <div>
                  <h3 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    Momentum Calculation Verification Mode (verification.csv)
                  </h3>
                  <p className="text-xs text-zinc-400 mt-1">
                    Choose any rebalance date to inspect every stock evaluated, exact dates used (t-12 to t-2), exact start/end prices, momentum scores, rank, and selection status for manual verification against Yahoo Finance.
                  </p>
                </div>

                <div className="flex items-center space-x-3">
                  <button
                    onClick={handleDownloadVerification}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-2 transition cursor-pointer shadow-lg shadow-emerald-950/20"
                  >
                    <Download className="w-4 h-4" />
                    Export verification.csv
                  </button>
                </div>
              </div>

              {/* Rebalance Date Selection Controls */}
              <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center space-x-3 flex-wrap gap-y-2">
                  <label className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
                    <Calendar className="w-4 h-4 text-emerald-400" />
                    Select Rebalance Date to Verify:
                  </label>
                  <input
                    type="date"
                    value={verifyDateInput}
                    onChange={e => setVerifyDateInput(e.target.value)}
                    className="px-3 py-1.5 rounded-xl bg-zinc-900 border border-zinc-700 text-xs font-mono text-zinc-100 focus:outline-none focus:border-emerald-500"
                  />
                  <button
                    onClick={() => runBacktest(config, verifyDateInput)}
                    disabled={loading}
                    className="px-4 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-bold transition flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {loading ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5 fill-current" />
                    )}
                    Verify Rebalance Date
                  </button>
                </div>

                {results?.verification_date && (
                  <div className="text-xs text-zinc-400 font-mono flex items-center gap-2">
                    <span>Active Verification Date:</span>
                    <span className="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-bold">
                      {results.verification_date}
                    </span>
                  </div>
                )}
              </div>

              {/* Stat Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1">
                  <span className="text-xs text-zinc-400 block">Total Stocks Evaluated</span>
                  <span className="text-lg font-bold text-zinc-100">
                    {results?.verification_records?.length || 0}
                  </span>
                </div>
                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1">
                  <span className="text-xs text-zinc-400 block">Valid Momentum Scores</span>
                  <span className="text-lg font-bold text-emerald-400">
                    {results?.verification_records?.filter(r => r.Status === "VALID").length || 0}
                  </span>
                </div>
                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1">
                  <span className="text-xs text-zinc-400 block">Selected Long Leg</span>
                  <span className="text-lg font-bold text-emerald-400">
                    {results?.verification_records?.filter(r => r.Selected === "LONG").length || 0}
                  </span>
                </div>
                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1">
                  <span className="text-xs text-zinc-400 block">Skipped / Stale / Missing</span>
                  <span className="text-lg font-bold text-amber-400">
                    {results?.verification_records?.filter(r => r.Status !== "VALID").length || 0}
                  </span>
                </div>
              </div>

              {/* Search & Filters */}
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center space-x-3 flex-wrap gap-y-2">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search ticker (e.g. APP, PLTR)..."
                      value={verificationSearch}
                      onChange={e => setVerificationSearch(e.target.value)}
                      className="pl-9 pr-3 py-1.5 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500 w-64"
                    />
                  </div>

                  <select
                    value={verificationFilter}
                    onChange={e => setVerificationFilter(e.target.value)}
                    className="px-3 py-1.5 text-xs rounded-xl bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="ALL">All Evaluated Stocks ({results?.verification_records?.length || 0})</option>
                    <option value="TOP20">Top 20 Ranked Stocks</option>
                    <option value="LONG">Selected LONG Leg Only</option>
                    <option value="SHORT">Selected SHORT Leg Only</option>
                    <option value="SELECTED">All Selected (Long & Short)</option>
                    <option value="VALID">Valid Momentum Scores</option>
                    <option value="SKIPPED">Skipped / Missing Data</option>
                  </select>
                </div>

                <div className="text-xs text-zinc-400 font-mono">
                  Showing {filteredVerificationRecords.length} records
                </div>
              </div>

              {/* Table of Verification Records */}
              <div className="overflow-x-auto max-h-[600px] border border-zinc-800 rounded-xl">
                <table className="w-full text-left text-xs text-zinc-300">
                  <thead className="bg-zinc-950 text-zinc-400 uppercase tracking-wider sticky top-0 z-10 border-b border-zinc-800">
                    <tr>
                      <th className="py-2.5 px-4 w-16">Rank</th>
                      <th className="py-2.5 px-4">Ticker</th>
                      <th className="py-2.5 px-4">Momentum Score</th>
                      <th className="py-2.5 px-4">Selected</th>
                      <th className="py-2.5 px-4">Start Date (t-12)</th>
                      <th className="py-2.5 px-4">Start Price</th>
                      <th className="py-2.5 px-4">End Date (t-2)</th>
                      <th className="py-2.5 px-4">End Price</th>
                      <th className="py-2.5 px-4">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/50 font-mono">
                    {filteredVerificationRecords.map((r, idx) => (
                      <tr key={idx} className={`hover:bg-zinc-800/40 ${r.Rank && r.Rank <= 20 ? "bg-emerald-500/5" : ""}`}>
                        <td className="py-2 px-4 font-bold text-zinc-400">
                          {r.Rank ? `#${r.Rank}` : "-"}
                        </td>
                        <td className="py-2 px-4 font-bold text-zinc-100 flex items-center gap-1.5">
                          {r.Ticker}
                          {r.Rank && r.Rank <= 20 && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                              TOP 20
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4 font-bold">
                          {r.MomentumScore !== null && r.MomentumScore !== undefined ? (
                            <span className={r.MomentumScore >= 0 ? "text-emerald-400" : "text-red-400"}>
                              {r.MomentumScore >= 0 ? "+" : ""}
                              {(r.MomentumScore * 100).toFixed(2)}%
                            </span>
                          ) : (
                            <span className="text-zinc-600">N/A</span>
                          )}
                        </td>
                        <td className="py-2 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              r.Selected === "LONG"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : r.Selected === "SHORT"
                                ? "bg-red-500/20 text-red-300 border border-red-500/30"
                                : "bg-zinc-800/60 text-zinc-500 border border-zinc-700/50"
                            }`}
                          >
                            {r.Selected}
                          </span>
                        </td>
                        <td className="py-2 px-4 text-zinc-400">{r.Start_Date || "-"}</td>
                        <td className="py-2 px-4 text-zinc-200">
                          {r.Start_Price !== null && r.Start_Price !== undefined ? formatUsd(r.Start_Price) : "-"}
                        </td>
                        <td className="py-2 px-4 text-zinc-400">{r.End_Date || "-"}</td>
                        <td className="py-2 px-4 text-zinc-200">
                          {r.End_Price !== null && r.End_Price !== undefined ? formatUsd(r.End_Price) : "-"}
                        </td>
                        <td className="py-2 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                              r.Status === "VALID"
                                ? "text-emerald-400"
                                : "text-amber-400"
                            }`}
                          >
                            {r.Status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: PYTHON ARCHITECTURE & CLI GUIDE */}
        {activeTab === "python" && (
          <div className="space-y-6">
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-4">
              <h3 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                <Code className="w-5 h-5 text-emerald-400" />
                Python Module Architecture (/backtester)
              </h3>
              <p className="text-xs text-zinc-400">
                Clean, modular, object-oriented Python 3.12 codebase designed for strategy extensions without modifying the backtest engine.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2">
                  <span className="text-emerald-400 font-bold block">📁 /backtester Structure</span>
                  <ul className="space-y-1 text-zinc-300">
                    <li>📄 main.py - CLI orchestrator & JSON builder</li>
                    <li>📄 config.py - Default backtest & strategy parameters</li>
                    <li>📄 strategy.py - BaseStrategy & CrossSectionalMomentum</li>
                    <li>📄 portfolio.py - BacktestEngine & position tracker</li>
                    <li>📄 data.py - yfinance loader with local caching</li>
                    <li>📄 metrics.py - CAGR, Drawdown, Sharpe, Volatility</li>
                    <li>📄 report.py - ASCII report & Matplotlib generator</li>
                    <li>📄 utils.py - Ticker universe CSV loader</li>
                    <li>📄 sp500.csv - Default ticker universe file</li>
                    <li>📁 cache/ - Local price cache directory</li>
                  </ul>
                </div>

                <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-2">
                  <span className="text-emerald-400 font-bold block">💻 Terminal Execution Command</span>
                  <p className="text-zinc-400 font-sans text-xs">Run directly in terminal or CLI:</p>
                  <pre className="p-3 rounded-lg bg-zinc-900 text-zinc-200 overflow-x-auto text-[11px]">
                    {`# Run default backtest
python main.py

# Run custom parameter backtest
python main.py \\
  --start "2020-01-01" \\
  --end "2026-08-04" \\
  --capital 30000 \\
  --positions 20 \\
  --lookback 12 \\
  --skip-last "True" \\
  --rebalance-freq "monthly" \\
  --json-out output.json`}
                  </pre>
                </div>
              </div>
            </div>

            {/* Python Strategy Code Preview */}
            <div className="p-6 rounded-2xl bg-zinc-900 border border-zinc-800 space-y-3">
              <h4 className="text-sm font-semibold text-zinc-100">Extending Strategy (strategy.py)</h4>
              <pre className="p-4 rounded-xl bg-zinc-950 text-emerald-300 font-mono text-xs overflow-x-auto border border-zinc-800/80">
{`class BaseStrategy(ABC):
    @abstractmethod
    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> Dict[str, float]:
        """Returns map of ticker -> target weight (e.g. {'AAPL': 0.05})"""
        pass`}
              </pre>
            </div>
          </div>
        )}
      </main>

      {/* Universe Modal */}
      {showUniverseModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-lg w-full space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-zinc-100 flex items-center gap-2">
              <Database className="w-5 h-5 text-emerald-400" />
              Edit Ticker Universe ({config.universe})
            </h3>
            <p className="text-xs text-zinc-400">
              Enter stock tickers separated by commas or line breaks. Yahoo Finance symbols supported (e.g., AAPL, MSFT, NVDA, BRK-B).
            </p>

            <textarea
              rows={8}
              value={editedUniverseText}
              onChange={e => setEditedUniverseText(e.target.value)}
              className="w-full p-3 rounded-xl bg-zinc-950 border border-zinc-800 font-mono text-xs text-zinc-100 focus:outline-none focus:border-emerald-500"
            />

            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                onClick={() => setShowUniverseModal(false)}
                className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveUniverse}
                className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs"
              >
                Save Universe & Rerun
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
