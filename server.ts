import express, { Request, Response } from "express";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { runBacktestEngine, run6WayComparison } from "./src/server/backtesterEngine";
import { runAllStrategyTests } from "./src/server/strategyTesterEngine";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// API Health Check
app.get("/api/health", (req: Request, res: Response) => {
  res.json({ status: "ok" });
});

const BACKTESTER_DIR = path.join(__dirname, "backtester");
const OUTPUT_JSON_PATH = path.join(BACKTESTER_DIR, "output.json");
const UNIVERSE_CSV_PATH = path.join(BACKTESTER_DIR, "sp500.csv");
const RUNS_LOG_PATH = path.join(BACKTESTER_DIR, "runs_log.json");

// Helper: read runs log from disk
function getRunLogs(): any[] {
  try {
    if (fs.existsSync(RUNS_LOG_PATH)) {
      const data = fs.readFileSync(RUNS_LOG_PATH, "utf-8");
      return JSON.parse(data);
    }
  } catch (e) {
    console.error("Error reading runs_log.json:", e);
  }
  return [];
}

// Helper: save a new run log
function saveRunLog(entry: any) {
  try {
    const logs = getRunLogs();
    logs.unshift(entry); // newest first
    fs.writeFileSync(RUNS_LOG_PATH, JSON.stringify(logs, null, 2), "utf-8");
  } catch (e) {
    console.error("Error writing runs_log.json:", e);
  }
}

// Serve static assets from build if available
const DIST_DIR = path.join(__dirname, "dist");
if (fs.existsSync(DIST_DIR)) {
  app.use(express.static(DIST_DIR));
}

// API: Get current ticker universe
app.get("/api/universe", (req: Request, res: Response) => {
  try {
    const universeParam = (req.query.universe as string) || "sp500.csv";
    const uLow = universeParam.toLowerCase();
    let filename = "sp500.csv";
    if (uLow.includes("custom")) {
      filename = "custom_momentum.csv";
    } else if (uLow.includes("russell")) {
      filename = "russell1000.csv";
    }
    const univPath = path.join(BACKTESTER_DIR, filename);
    if (!fs.existsSync(univPath)) {
      return res.status(404).json({ error: "Universe file not found" });
    }
    const content = fs.readFileSync(univPath, "utf-8");
    const lines = content.split("\n").map(l => l.trim()).filter(l => l && !l.startsWith("#") && l.toLowerCase() !== "ticker");
    return res.json({ tickers: lines, universe: filename });
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

// API: Save updated ticker universe
app.post("/api/universe", (req: Request, res: Response) => {
  try {
    const { tickers, universe = "sp500.csv" } = req.body;
    if (!Array.isArray(tickers) || tickers.length === 0) {
      return res.status(400).json({ error: "Tickers must be a non-empty array of strings" });
    }
    const uLow = String(universe).toLowerCase();
    let filename = "sp500.csv";
    if (uLow.includes("custom")) {
      filename = "custom_momentum.csv";
    } else if (uLow.includes("russell")) {
      filename = "russell1000.csv";
    }
    const targetPath = path.join(BACKTESTER_DIR, filename);
    const cleanTickers = tickers.map(t => String(t).trim().toUpperCase()).filter(Boolean);
    const content = ["Ticker,DateAdded,DateRemoved", ...cleanTickers.map(t => `${t},1900-01-01,9999-12-31`)].join("\n");
    fs.writeFileSync(targetPath, content, "utf-8");
    return res.json({ success: true, count: cleanTickers.length, universe: filename });
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

// API: Run Backtest
app.post("/api/run-backtest", (req: Request, res: Response) => {
  try {
    const {
      startDate = "2020-01-01",
      endDate = "2026-08-04",
      initialCapital = 30000,
      positions = 20,
      lookbackMonths = 12,
      skipLastMonth = true,
      includeShorts = false,
      rebalanceFreq = "monthly",
      universe = "sp500.csv",
      verifyDate,
      customTickers,
      maxPositionsPerSector,
      minAvgDollarVolume,
      minMarketCap,
      rankingMethod,
      regimeFilter,
      regimeReducedExposurePct,
      earningsBlackoutDays,
      strategyMode,
      factorWeights
    } = req.body;

    let universeFile = "sp500.csv";
    const uLow = typeof universe === "string" ? universe.toLowerCase() : "";
    if (uLow.includes("custom")) {
      universeFile = "custom_momentum.csv";
    } else if (uLow.includes("russell")) {
      universeFile = "russell1000.csv";
    } else if (typeof universe === "string" && universe.endsWith(".csv")) {
      universeFile = universe;
    }

    if (Array.isArray(customTickers) && customTickers.length > 0) {
      const customPath = path.join(BACKTESTER_DIR, "custom_universe.csv");
      const cleanCustom = customTickers.map((t: string) => String(t).trim().toUpperCase()).filter(Boolean);
      fs.writeFileSync(customPath, ["Ticker", ...cleanCustom].join("\n"), "utf-8");
      universeFile = "custom_universe.csv";
    }

    const resultData = runBacktestEngine({
      startDate: String(startDate),
      endDate: String(endDate),
      initialCapital: Number(initialCapital),
      positions: Number(positions),
      lookbackMonths: Number(lookbackMonths),
      skipLastMonth: Boolean(skipLastMonth),
      includeShorts: Boolean(includeShorts),
      rebalanceFreq: String(rebalanceFreq),
      universe: universeFile,
      verifyDate: verifyDate ? String(verifyDate) : undefined,
      maxPositionsPerSector: maxPositionsPerSector !== undefined ? Number(maxPositionsPerSector) : 0,
      minAvgDollarVolume: minAvgDollarVolume !== undefined ? Number(minAvgDollarVolume) : 0,
      minMarketCap: minMarketCap !== undefined ? Number(minMarketCap) : 0,
      rankingMethod: rankingMethod ? String(rankingMethod) : "raw_return",
      regimeFilter: Boolean(regimeFilter),
      regimeReducedExposurePct: regimeReducedExposurePct !== undefined ? Number(regimeReducedExposurePct) : 0.5,
      earningsBlackoutDays: earningsBlackoutDays !== undefined ? Number(earningsBlackoutDays) : 0,
      strategyMode: strategyMode ? String(strategyMode) : undefined,
      factorWeights
    });

    // Auto-save settings and results log entry
    const logEntry = {
      id: `run-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      timestamp: new Date().toISOString(),
      settings: {
        startDate,
        endDate,
        initialCapital: Number(initialCapital),
        positions: Number(positions),
        lookbackMonths: Number(lookbackMonths),
        skipLastMonth: Boolean(skipLastMonth),
        includeShorts: Boolean(includeShorts),
        rebalanceFreq: String(rebalanceFreq),
        universe: universeFile
      },
      results: {
        endingCapital: resultData.metrics?.["Ending Capital"] || 0,
        totalReturn: resultData.metrics?.["Total Return"] || 0,
        cagr: resultData.metrics?.["Annualized Return (CAGR)"] || 0,
        maxDrawdown: resultData.metrics?.["Maximum Drawdown"] || 0,
        sharpe: resultData.metrics?.["Sharpe Ratio"] || 0
      },
      spyComparison: {
        spyTotalReturn: resultData.metrics?.["Benchmark Total Return"] || 0,
        spyCagr: resultData.metrics?.["Benchmark CAGR"] || 0,
        alphaVsSpy: resultData.metrics?.["Alpha vs Benchmark"] || 0,
        returnSpreadVsSpy: (resultData.metrics?.["Total Return"] || 0) - (resultData.metrics?.["Benchmark Total Return"] || 0),
        outperformed: (resultData.metrics?.["Total Return"] || 0) >= (resultData.metrics?.["Benchmark Total Return"] || 0)
      }
    };
    saveRunLog(logEntry);
    (resultData as any).logEntry = logEntry;

    return res.json(resultData);
  } catch (error: any) {
    console.error("Backtest execution error:", error);
    return res.status(500).json({
      error: "Backtest execution failed",
      details: error.message || String(error)
    });
  }
});

// API: Run 6-Way Risk Filter Comparison Backtest
app.post("/api/run-comparison", (req: Request, res: Response) => {
  try {
    const data = run6WayComparison();
    return res.json(data);
  } catch (error: any) {
    console.error("Comparison run error:", error);
    return res.status(500).json({
      error: "Comparison run failed",
      details: error.message || String(error)
    });
  }
});

// API: Get Backtest Run Logs
app.get("/api/logs", (req: Request, res: Response) => {
  return res.json({ logs: getRunLogs() });
});

// API: Clear or Delete Backtest Run Logs
app.delete("/api/logs/:id", (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const logs = getRunLogs().filter(l => l.id !== id);
    fs.writeFileSync(RUNS_LOG_PATH, JSON.stringify(logs, null, 2), "utf-8");
    return res.json({ success: true, count: logs.length });
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

app.delete("/api/logs", (req: Request, res: Response) => {
  try {
    fs.writeFileSync(RUNS_LOG_PATH, JSON.stringify([], null, 2), "utf-8");
    return res.json({ success: true, count: 0 });
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

// API: Download output files (trades.csv, portfolio.csv, verification.csv, runs_log.csv, equity_curve.png, drawdown.png)
app.get("/api/download/:filename", (req: Request, res: Response) => {
  const filename = req.params.filename;
  const allowedFiles = ["trades.csv", "portfolio.csv", "verification.csv", "runs_log.csv", "runs_log.json", "equity_curve.png", "drawdown.png"];
  
  if (!allowedFiles.includes(filename)) {
    return res.status(403).json({ error: "Access denied" });
  }

  if (filename === "runs_log.csv") {
    const logs = getRunLogs();
    const headers = [
      "Run ID", "Timestamp", "Start Date", "End Date", "Initial Capital", "Positions", "Lookback Months",
      "Skip Last Month", "Include Shorts", "Rebalance Freq", "Universe",
      "Ending Capital", "Total Return %", "CAGR %", "Max Drawdown %", "Sharpe",
      "SPY Total Return %", "SPY CAGR %", "Alpha Spread %", "Outperformed SPY"
    ];
    const rows = [
      headers.join(","),
      ...logs.map(l => [
        l.id,
        l.timestamp,
        l.settings.startDate,
        l.settings.endDate,
        l.settings.initialCapital,
        l.settings.positions,
        l.settings.lookbackMonths,
        l.settings.skipLastMonth,
        l.settings.includeShorts,
        l.settings.rebalanceFreq,
        l.settings.universe,
        l.results.endingCapital,
        (l.results.totalReturn * 100).toFixed(2) + "%",
        (l.results.cagr * 100).toFixed(2) + "%",
        (l.results.maxDrawdown * 100).toFixed(2) + "%",
        l.results.sharpe.toFixed(2),
        (l.spyComparison.spyTotalReturn * 100).toFixed(2) + "%",
        (l.spyComparison.spyCagr * 100).toFixed(2) + "%",
        (l.spyComparison.alphaVsSpy * 100).toFixed(2) + "%",
        l.spyComparison.outperformed ? "YES" : "NO"
      ].join(","))
    ];
    res.setHeader("Content-Disposition", 'attachment; filename="runs_log.csv"');
    res.setHeader("Content-Type", "text/csv");
    return res.send(rows.join("\n"));
  }

  const filePath = path.join(BACKTESTER_DIR, filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: "File not found" });
  }

  res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
  if (filename.endsWith(".csv")) {
    res.setHeader("Content-Type", "text/csv");
  } else if (filename.endsWith(".png")) {
    res.setHeader("Content-Type", "image/png");
  }

  return res.sendFile(filePath);
});

// API: Run Strategy Tester Suite across parameters
app.post("/api/strategy-tester", (req: Request, res: Response) => {
  try {
    const resultData = runAllStrategyTests();
    return res.json(resultData);
  } catch (error: any) {
    console.error("Strategy tester execution error:", error);
    return res.status(500).json({
      error: "Strategy tester execution failed",
      details: error.message || String(error)
    });
  }
});

// API: Get cached Strategy Tester results if available
app.get("/api/strategy-tester", (req: Request, res: Response) => {
  try {
    const resultData = runAllStrategyTests();
    return res.json(resultData);
  } catch (error: any) {
    return res.json({ ready: false });
  }
});

// Vite integration for development mode
if (process.env.NODE_ENV !== "production") {
  import("vite").then(async ({ createServer }) => {
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
    app.listen(Number(PORT), "0.0.0.0", () => {
      console.log(`Server running in DEV mode at http://0.0.0.0:${PORT}`);
    });
  });
} else {
  // SPA fallback
  app.get("*", (req: Request, res: Response) => {
    const indexPath = path.join(DIST_DIR, "index.html");
    if (fs.existsSync(indexPath)) {
      res.sendFile(indexPath);
    } else {
      res.status(404).send("Build output not found");
    }
  });
  app.listen(Number(PORT), "0.0.0.0", () => {
    console.log(`Server running in PRODUCTION mode on port ${PORT}`);
  });
}
