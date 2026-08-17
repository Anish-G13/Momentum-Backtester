import fs from "fs";
import path from "path";
import { runBacktestEngine } from "./backtesterEngine";

export function formatPct(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  return `${(val * 100).toFixed(2)}%`;
}

export function formatUsd(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function runAllStrategyTests(): any {
  const testerJsonPath = path.join(process.cwd(), "backtester", "strategy_tester_results.json");

  // Check if already computed and valid
  if (fs.existsSync(testerJsonPath)) {
    try {
      const existing = JSON.parse(fs.readFileSync(testerJsonPath, "utf-8"));
      if (existing && existing.test1_start_dates && existing.test2_top_n_matrix) {
        return existing;
      }
    } catch (e) {
      // Re-run if corrupted
    }
  }

  const allStartDates = [
    "2018-01-01", "2019-01-01", "2020-01-01", "2021-01-01",
    "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"
  ];
  const endDate = "2026-08-04";
  const initialCapital = 30000;

  const defTopN = 10;
  const defRebalance = "monthly";
  const defLookback = 12;
  const defSkip = true;

  const runCache = new Map<string, any>();

  const getRun = (sd: string, topN: number, freq: string, lookback: number, skip: boolean) => {
    const key = `${sd}_${topN}_${freq}_${lookback}_${skip}`;
    if (!runCache.has(key)) {
      const res = runBacktestEngine({
        startDate: sd,
        endDate,
        initialCapital,
        positions: topN,
        lookbackMonths: lookback,
        skipLastMonth: skip,
        includeShorts: false,
        rebalanceFreq: freq,
        universe: "russell1000.csv"
      });

      const metrics = res.metrics;
      const stratRet = metrics["Total Return"];
      const spyRet = metrics["Benchmark Total Return"];
      const beatSpy = stratRet > spyRet ? "Yes" : "No";

      const formatted = {
        start_date: sd,
        top_n: topN,
        rebalance: freq.charAt(0).toUpperCase() + freq.slice(1),
        lookback: `${lookback} Months`,
        skip_month: skip ? "Enabled" : "Disabled",
        final_value_raw: metrics["Ending Capital"],
        final_value: formatUsd(metrics["Ending Capital"]),
        total_return_raw: stratRet,
        total_return: formatPct(stratRet),
        spy_return_raw: spyRet,
        spy_return: formatPct(spyRet),
        beat_spy: beatSpy,
        sharpe_raw: metrics["Sharpe Ratio"],
        sharpe: metrics["Sharpe Ratio"].toFixed(2),
        max_drawdown_raw: metrics["Maximum Drawdown"],
        max_drawdown: formatPct(metrics["Maximum Drawdown"])
      };
      runCache.set(key, formatted);
    }
    return runCache.get(key);
  };

  // TEST 1: Baseline across Start Dates
  const test1_results: any[] = [];
  let beatSpyCount = 0;
  for (const sd of allStartDates) {
    const res = getRun(sd, defTopN, defRebalance, defLookback, defSkip);
    test1_results.push(res);
    if (res.beat_spy === "Yes") beatSpyCount++;
  }

  // TEST 2: Top N Positions
  const top_n_options = [5, 10, 20, 30];
  const test2_matrix: any[] = [];
  const top_n_wins: Record<string, number> = { "Top 5": 0, "Top 10": 0, "Top 20": 0, "Top 30": 0 };

  for (const sd of allStartDates) {
    const yearStr = sd.split("-")[0];
    const rowCols: Record<string, any> = {};
    let bestRet = -999999;
    let bestOpt = "";

    for (const n of top_n_options) {
      const res = getRun(sd, n, defRebalance, defLookback, defSkip);
      const optKey = `Top ${n}`;
      rowCols[optKey] = res;
      if (res.total_return_raw > bestRet) {
        bestRet = res.total_return_raw;
        bestOpt = optKey;
      }
    }

    if (bestOpt) top_n_wins[bestOpt] = (top_n_wins[bestOpt] || 0) + 1;

    test2_matrix.push({
      start_date: yearStr,
      full_start_date: sd,
      options: rowCols,
      winner: bestOpt
    });
  }

  // TEST 3: Rebalance Frequency
  const rebalance_options = ["weekly", "monthly", "quarterly"];
  const test3_matrix: any[] = [];
  const rebalance_wins: Record<string, number> = { Weekly: 0, Monthly: 0, Quarterly: 0 };

  for (const sd of allStartDates) {
    const yearStr = sd.split("-")[0];
    const rowCols: Record<string, any> = {};
    let bestRet = -999999;
    let bestOpt = "";

    for (const freq of rebalance_options) {
      const res = getRun(sd, defTopN, freq, defLookback, defSkip);
      const optKey = freq.charAt(0).toUpperCase() + freq.slice(1);
      rowCols[optKey] = res;
      if (res.total_return_raw > bestRet) {
        bestRet = res.total_return_raw;
        bestOpt = optKey;
      }
    }

    if (bestOpt) rebalance_wins[bestOpt] = (rebalance_wins[bestOpt] || 0) + 1;

    test3_matrix.push({
      start_date: yearStr,
      full_start_date: sd,
      options: rowCols,
      winner: bestOpt
    });
  }

  // TEST 4: Lookback Period
  const lookback_options = [6, 9, 12, 18];
  const test4_matrix: any[] = [];
  const lookback_wins: Record<string, number> = { "6 Months": 0, "9 Months": 0, "12 Months": 0, "18 Months": 0 };

  for (const sd of allStartDates) {
    const yearStr = sd.split("-")[0];
    const rowCols: Record<string, any> = {};
    let bestRet = -999999;
    let bestOpt = "";

    for (const lb of lookback_options) {
      const res = getRun(sd, defTopN, defRebalance, lb, defSkip);
      const optKey = `${lb} Months`;
      rowCols[optKey] = res;
      if (res.total_return_raw > bestRet) {
        bestRet = res.total_return_raw;
        bestOpt = optKey;
      }
    }

    if (bestOpt) lookback_wins[bestOpt] = (lookback_wins[bestOpt] || 0) + 1;

    test4_matrix.push({
      start_date: yearStr,
      full_start_date: sd,
      options: rowCols,
      winner: bestOpt
    });
  }

  // TEST 5: Skip Last Month
  const skip_options = [true, false];
  const test5_matrix: any[] = [];
  const skip_wins: Record<string, number> = { "Skip Enabled": 0, "Skip Disabled": 0 };

  for (const sd of allStartDates) {
    const yearStr = sd.split("-")[0];
    const rowCols: Record<string, any> = {};
    let bestRet = -999999;
    let bestOpt = "";

    for (const skip of skip_options) {
      const res = getRun(sd, defTopN, defRebalance, defLookback, skip);
      const optKey = skip ? "Skip Enabled" : "Skip Disabled";
      rowCols[optKey] = res;
      if (res.total_return_raw > bestRet) {
        bestRet = res.total_return_raw;
        bestOpt = optKey;
      }
    }

    if (bestOpt) skip_wins[bestOpt] = (skip_wins[bestOpt] || 0) + 1;

    test5_matrix.push({
      start_date: yearStr,
      full_start_date: sd,
      options: rowCols,
      winner: bestOpt
    });
  }

  const output = {
    test1_start_dates: test1_results,
    test2_top_n_matrix: {
      rows: test2_matrix,
      wins: top_n_wins
    },
    test3_rebalance_matrix: {
      rows: test3_matrix,
      wins: rebalance_wins
    },
    test4_lookback_matrix: {
      rows: test4_matrix,
      wins: lookback_wins
    },
    test5_skip_matrix: {
      rows: test5_matrix,
      wins: skip_wins
    },
    summary_metrics: {
      total_start_dates: allStartDates.length,
      beat_spy_count: beatSpyCount,
      beat_spy_pct: formatPct(beatSpyCount / (allStartDates.length || 1))
    },
    ready: true
  };

  fs.writeFileSync(testerJsonPath, JSON.stringify(output, null, 2), "utf-8");
  return output;
}
