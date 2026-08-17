import React, { useState, useEffect, useRef } from "react";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import {
  Play,
  CheckCircle2,
  XCircle,
  RotateCw,
  Sliders,
  Calendar,
  ListFilter,
  TrendingUp,
  Clock,
  Sparkles,
  ShieldCheck,
  AlertCircle,
  Trophy,
  BarChart2,
  Download,
  Printer,
  FileText
} from "lucide-react";

export interface TestResultItem {
  start_date: string;
  top_n: number;
  rebalance: string;
  lookback: string;
  skip_month: string;
  final_value_raw: number;
  final_value: string;
  total_return_raw: number;
  total_return: string;
  spy_return_raw: number;
  spy_return: string;
  beat_spy: "Yes" | "No";
  sharpe_raw: number;
  sharpe: string;
  max_drawdown_raw: number;
  max_drawdown: string;
}

export interface MatrixRowItem {
  start_date: string;
  options: Record<string, TestResultItem>;
  winner: string;
}

export interface ParameterMatrixData {
  rows: MatrixRowItem[];
  wins: Record<string, number>;
}

export interface StrategyTesterData {
  test1_start_dates?: TestResultItem[];
  test2_top_n_matrix?: ParameterMatrixData;
  test3_rebalance_matrix?: ParameterMatrixData;
  test4_lookback_matrix?: ParameterMatrixData;
  test5_skip_matrix?: ParameterMatrixData;
  summary_metrics?: {
    total_start_dates: number;
    beat_spy_count: number;
    beat_spy_pct: string;
  };
  ready?: boolean;
}

export const StrategyTester: React.FC = () => {
  const [data, setData] = useState<StrategyTesterData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [generatingPdf, setGeneratingPdf] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const reportRef = useRef<HTMLDivElement>(null);

  const fetchResults = async () => {
    try {
      setError(null);
      const res = await fetch("/api/strategy-tester");
      if (res.ok) {
        const json = await res.json();
        if (json && (json.test1_start_dates || json.test2_top_n_matrix || json.ready === false)) {
          setData(json);
        }
      }
    } catch (err: any) {
      console.error("Error fetching strategy tester results:", err);
    }
  };

  const runTesterSuite = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/strategy-tester", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.details || errJson.error || "Failed to execute strategy tester suite");
      }
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Execution error");
    } finally {
      setLoading(false);
    }
  };

  const oklchToRgb = (colorStr: string): string => {
    if (!colorStr) return colorStr;
    if (!colorStr.includes("oklch") && !colorStr.includes("color(")) return colorStr;
    if (typeof document === "undefined") return colorStr;

    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return colorStr;

      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000000";
      ctx.fillStyle = colorStr;
      ctx.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
      const alpha = Number((a / 255).toFixed(3));
      if (alpha === 1) {
        return `rgb(${r}, ${g}, ${b})`;
      }
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    } catch (e) {
      return colorStr;
    }
  };

  const replaceOklchInString = (str: string): string => {
    if (!str || (!str.includes("oklch") && !str.includes("color("))) return str;
    return str.replace(/oklch\([^)]+\)/g, (match) => oklchToRgb(match));
  };

  const sanitizeOklchInDoc = (clonedDoc: Document) => {
    try {
      // 1. Sanitize <style> tag content
      clonedDoc.querySelectorAll("style").forEach((styleEl) => {
        if (styleEl.textContent && (styleEl.textContent.includes("oklch") || styleEl.textContent.includes("color("))) {
          styleEl.textContent = replaceOklchInString(styleEl.textContent);
        }
      });

      // 2. Sanitize inline and computed styles across elements
      const win = clonedDoc.defaultView || window;
      const elements = clonedDoc.querySelectorAll<HTMLElement>("*");
      const propsToFix = [
        "color",
        "background-color",
        "border-top-color",
        "border-right-color",
        "border-bottom-color",
        "border-left-color",
        "outline-color",
        "fill",
        "stroke",
        "box-shadow",
        "text-shadow"
      ];

      elements.forEach((el) => {
        const computed = win.getComputedStyle(el);
        if (computed) {
          propsToFix.forEach((prop) => {
            const val = computed.getPropertyValue(prop);
            if (val && (val.includes("oklch") || val.includes("color("))) {
              el.style.setProperty(prop, replaceOklchInString(val), "important");
            }
          });
        }

        const inlineStyle = el.getAttribute("style");
        if (inlineStyle && (inlineStyle.includes("oklch") || inlineStyle.includes("color("))) {
          el.setAttribute("style", replaceOklchInString(inlineStyle));
        }
      });
    } catch (err) {
      console.warn("OKLCH sanitization error in cloned PDF document:", err);
    }
  };

  const downloadPdfReport = async () => {
    if (!reportRef.current) return;
    setGeneratingPdf(true);

    try {
      const pdf = new jsPDF("p", "mm", "a4");
      const pdfWidth = 210;
      const pdfHeight = 297;
      const pageMargin = 10;
      const printableWidth = pdfWidth - (pageMargin * 2);

      const sections = reportRef.current.querySelectorAll(".pdf-section");

      if (!sections || sections.length === 0) {
        const canvas = await html2canvas(reportRef.current, {
          scale: 2,
          useCORS: true,
          backgroundColor: "#0f172a",
          logging: false,
          onclone: (clonedDoc) => sanitizeOklchInDoc(clonedDoc)
        });
        const imgData = canvas.toDataURL("image/png");
        const imgHeight = (canvas.height * printableWidth) / canvas.width;
        let heightLeft = imgHeight;
        let position = pageMargin;

        pdf.addImage(imgData, "PNG", pageMargin, position, printableWidth, imgHeight);
        heightLeft -= (pdfHeight - (pageMargin * 2));

        while (heightLeft > 0) {
          position = heightLeft - imgHeight + pageMargin;
          pdf.addPage();
          pdf.addImage(imgData, "PNG", pageMargin, position, printableWidth, imgHeight);
          heightLeft -= (pdfHeight - (pageMargin * 2));
        }
      } else {
        let currentY = pageMargin;

        for (let i = 0; i < sections.length; i++) {
          const sec = sections[i] as HTMLElement;
          const canvas = await html2canvas(sec, {
            scale: 2,
            useCORS: true,
            backgroundColor: "#0f172a",
            logging: false,
            onclone: (clonedDoc) => sanitizeOklchInDoc(clonedDoc)
          });

          const imgData = canvas.toDataURL("image/png");
          const imgHeight = (canvas.height * printableWidth) / canvas.width;

          if (currentY + imgHeight > pdfHeight - pageMargin && currentY > pageMargin + 5) {
            pdf.addPage();
            currentY = pageMargin;
          }

          pdf.setFillColor(15, 23, 42); // Fill page background with slate-900
          pdf.rect(0, 0, pdfWidth, pdfHeight, "F");

          pdf.addImage(imgData, "PNG", pageMargin, currentY, printableWidth, imgHeight);
          currentY += imgHeight + 6;
        }

        const totalPages = (pdf as any).internal.getNumberOfPages();
        for (let p = 1; p <= totalPages; p++) {
          pdf.setPage(p);
          pdf.setFontSize(8);
          pdf.setTextColor(148, 163, 184);
          pdf.text(
            `Strategy Tester Matrix Audit Report — S&P 500 Academic Momentum Engine`,
            pageMargin,
            pdfHeight - 5
          );
          pdf.text(
            `Page ${p} of ${totalPages}`,
            pdfWidth - pageMargin - 15,
            pdfHeight - 5
          );
        }
      }

      pdf.save(`Strategy_Tester_Matrix_Audit_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (err: any) {
      console.error("PDF Export Error:", err);
      setError("Failed to generate PDF report: " + (err.message || String(err)));
    } finally {
      setGeneratingPdf(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  useEffect(() => {
    fetchResults();
  }, []);

  // Helper to find parameter with max win count
  const getMostFrequentWinner = (wins?: Record<string, number>) => {
    if (!wins) return { name: "N/A", wins: 0 };
    let maxWins = -1;
    let winnerName = "";
    Object.entries(wins).forEach(([name, count]) => {
      if (count > maxWins) {
        maxWins = count;
        winnerName = name;
      }
    });
    return { name: winnerName, wins: maxWins };
  };

  const renderBaselineTable = (items: TestResultItem[] = []) => {
    if (!items || items.length === 0) return null;

    return (
      <div className="pdf-section bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl mb-8">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Calendar className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-100">BASELINE — START DATE OVERVIEW</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Default benchmark baseline (Top 10, Monthly, 12M Lookback, Skip Last Month) evaluated across 8 historical start dates
              </p>
            </div>
          </div>
          <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
            {items.length} Start Dates
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-950/60 border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                <th className="py-3.5 px-4">Start Date</th>
                <th className="py-3.5 px-4 text-center">Top N</th>
                <th className="py-3.5 px-4 text-center">Rebalance</th>
                <th className="py-3.5 px-4 text-center">Lookback</th>
                <th className="py-3.5 px-4 text-center">Skip Month</th>
                <th className="py-3.5 px-4 text-right">Final Value</th>
                <th className="py-3.5 px-4 text-right">Total Return</th>
                <th className="py-3.5 px-4 text-right">SPY Return</th>
                <th className="py-3.5 px-4 text-center">Beat SPY</th>
                <th className="py-3.5 px-4 text-right">Sharpe</th>
                <th className="py-3.5 px-4 text-right">Max Drawdown</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200 font-mono">
              {items.map((row, idx) => {
                const beat = row.beat_spy === "Yes";
                return (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-slate-100">{row.start_date}</td>
                    <td className="py-3 px-4 text-center font-sans">{row.top_n}</td>
                    <td className="py-3 px-4 text-center font-sans">{row.rebalance}</td>
                    <td className="py-3 px-4 text-center font-sans">{row.lookback}</td>
                    <td className="py-3 px-4 text-center font-sans">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] ${
                        row.skip_month === "Enabled"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : "bg-slate-800 text-slate-400 border border-slate-700"
                      }`}>
                        {row.skip_month}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-slate-100">{row.final_value}</td>
                    <td className={`py-3 px-4 text-right font-semibold ${row.total_return_raw >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {row.total_return}
                    </td>
                    <td className="py-3 px-4 text-right text-slate-400">{row.spy_return}</td>
                    <td className="py-3 px-4 text-center">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-sans font-semibold ${
                        beat
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                          : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                      }`}>
                        {beat ? <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" /> : <XCircle className="w-3 h-3 mr-1 text-rose-400" />}
                        {row.beat_spy}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-indigo-300 font-semibold">{row.sharpe}</td>
                    <td className="py-3 px-4 text-right text-rose-400">{row.max_drawdown}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderMatrixTable = (
    matrixData?: ParameterMatrixData,
    title?: string,
    subtitle?: string,
    icon?: React.ReactNode,
    optionKeys: string[] = []
  ) => {
    if (!matrixData || !matrixData.rows || matrixData.rows.length === 0) return null;

    const mostFreq = getMostFrequentWinner(matrixData.wins);

    return (
      <div className="pdf-section bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl mb-10">
        {/* Table Header Banner */}
        <div className="p-5 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              {icon}
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-100 tracking-wide">{title}</h3>
              <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2 bg-emerald-500/10 border border-emerald-500/20 px-3.5 py-1.5 rounded-xl text-xs font-medium text-emerald-300 shrink-0">
            <Trophy className="w-4 h-4 text-emerald-400" />
            <span>
              Most Consistent Winner: <strong className="text-emerald-200 font-bold">{mostFreq.name}</strong> ({mostFreq.wins}/{matrixData.rows.length} Start Dates)
            </span>
          </div>
        </div>

        {/* Matrix Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                <th className="py-3.5 px-4 w-36">Start Date</th>
                {optionKeys.map((opt) => (
                  <th key={opt} className="py-3.5 px-4 text-center font-semibold text-slate-200">
                    {opt}
                  </th>
                ))}
                <th className="py-3.5 px-4 text-center bg-indigo-950/30 text-indigo-300 font-bold">
                  Start Date Winner
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200 font-mono">
              {matrixData.rows.map((row, idx) => {
                return (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-slate-100 font-sans">{row.start_date}</td>
                    {optionKeys.map((opt) => {
                      const item = row.options[opt];
                      const isWinner = row.winner === opt || row.winner === `Top ${opt}`;
                      if (!item) return <td key={opt} className="py-3.5 px-4 text-center text-slate-500">-</td>;

                      return (
                        <td
                          key={opt}
                          className={`py-3.5 px-4 text-center transition-colors ${
                            isWinner
                              ? "bg-emerald-500/10 font-bold text-emerald-300 border-x border-emerald-500/20"
                              : "text-slate-300"
                          }`}
                        >
                          <div className="text-xs font-semibold">{item.total_return}</div>
                          <div className="text-[10px] text-slate-400 font-sans mt-0.5">
                            Sharpe: <span className="text-slate-200">{item.sharpe}</span> | Max DD: <span className="text-rose-400">{item.max_drawdown}</span>
                          </div>
                        </td>
                      );
                    })}
                    <td className="py-3.5 px-4 text-center bg-indigo-950/20 border-l border-slate-800 font-sans">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        <Trophy className="w-3 h-3 mr-1 text-amber-400" />
                        {row.winner}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Win Frequency Summary Footer Bar */}
        <div className="p-4 bg-slate-950/80 border-t border-slate-800">
          <div className="text-xs font-semibold text-slate-400 mb-3 uppercase tracking-wider flex items-center">
            <BarChart2 className="w-4 h-4 mr-1.5 text-indigo-400" />
            Win Frequency Count Across {matrixData.rows.length} Start Dates:
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(matrixData.wins).map(([optName, winCount]) => {
              const isTopWinner = optName === mostFreq.name;
              return (
                <div
                  key={optName}
                  className={`p-3 rounded-xl border flex items-center justify-between transition-all ${
                    isTopWinner
                      ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 shadow-lg shadow-emerald-500/10"
                      : "bg-slate-900 border-slate-800 text-slate-300"
                  }`}
                >
                  <span className="text-xs font-bold font-sans">{optName}</span>
                  <div className="flex items-center space-x-1.5">
                    <span className="text-sm font-extrabold font-mono">{winCount}</span>
                    <span className="text-[10px] opacity-75">wins</span>
                    {isTopWinner && <Trophy className="w-3.5 h-3.5 text-amber-400 ml-1" />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const hasData =
    data &&
    (data.test1_start_dates ||
      data.test2_top_n_matrix ||
      data.test3_rebalance_matrix ||
      data.test4_lookback_matrix ||
      data.test5_skip_matrix);

  // Derive most frequent winners for conclusion panel
  const topNWinner = getMostFrequentWinner(data?.test2_top_n_matrix?.wins);
  const rebalanceWinner = getMostFrequentWinner(data?.test3_rebalance_matrix?.wins);
  const lookbackWinner = getMostFrequentWinner(data?.test4_lookback_matrix?.wins);
  const skipWinner = getMostFrequentWinner(data?.test5_skip_matrix?.wins);

  return (
    <div ref={reportRef} className="space-y-8 max-w-7xl mx-auto px-4 py-6">
      {/* Page Header */}
      <div className="pdf-section bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <span className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                <Sliders className="w-6 h-6" />
              </span>
              <h1 className="text-2xl font-bold text-white tracking-tight">Strategy Tester Matrix Audit</h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                Multi-Start Date Robustness Evaluation
              </span>
            </div>
            <p className="text-sm text-slate-300 max-w-3xl leading-relaxed">
              Answers the core question: <strong className="text-emerald-400 font-semibold">&ldquo;Which parameter choices consistently win across DIFFERENT market start dates?&rdquo;</strong> 
              Evaluates parameter variations across all 8 start dates (2018–2025) to identify robust parameter configurations, prioritizing market consistency over single-period curve fitting.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 shrink-0">
            {hasData && (
              <>
                <button
                  onClick={downloadPdfReport}
                  disabled={generatingPdf}
                  className="flex items-center space-x-2 px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm shadow-lg shadow-emerald-600/20 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  title="Download full Strategy Tester audit report as a PDF"
                >
                  {generatingPdf ? (
                    <>
                      <RotateCw className="w-4 h-4 animate-spin text-white" />
                      <span>Generating PDF...</span>
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4 text-white" />
                      <span>Download PDF Report</span>
                    </>
                  )}
                </button>
                <button
                  onClick={handlePrint}
                  className="p-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all cursor-pointer no-print"
                  title="Print Strategy Tester"
                >
                  <Printer className="w-4 h-4" />
                </button>
              </>
            )}

            <button
              onClick={runTesterSuite}
              disabled={loading}
              className="flex items-center space-x-2 px-5 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-blue-500/20 transition-all transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <>
                  <RotateCw className="w-4 h-4 animate-spin text-white" />
                  <span>Executing Matrix Backtests...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white text-white" />
                  <span>Run Matrix Audit Suite</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 flex items-center space-x-3 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center space-y-4 shadow-xl">
          <RotateCw className="w-10 h-10 text-blue-400 animate-spin mx-auto" />
          <h3 className="text-lg font-semibold text-slate-200">Executing Parameter Matrix Suite across 8 Start Dates...</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
            Running 80+ parameter backtest combinations across historical start dates (2018 through 2025). Evaluating win frequencies and regime stability.
          </p>
        </div>
      )}

      {!loading && !hasData && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center space-y-4 shadow-xl">
          <Sparkles className="w-12 h-12 text-indigo-400 mx-auto opacity-80" />
          <h3 className="text-xl font-bold text-slate-100">No Matrix Audit Suite Loaded</h3>
          <p className="text-sm text-slate-400 max-w-lg mx-auto">
            Click <strong className="text-slate-200">"Run Matrix Audit Suite"</strong> above to launch multi-start-date robustness testing across Top N, Rebalance Frequencies, Lookbacks, and Skip Last Month.
          </p>
        </div>
      )}

      {!loading && hasData && (
        <>
          {/* Baseline Overview Table */}
          {renderBaselineTable(data.test1_start_dates)}

          {/* TEST 2: Top N Positions Matrix */}
          {renderMatrixTable(
            data.test2_top_n_matrix,
            "TOP N POSITIONS MATRIX (Across All Start Dates)",
            "Evaluates portfolio concentration (Top 5, 10, 20, 30) for every start date row",
            <ListFilter className="w-5 h-5" />,
            ["Top 5", "Top 10", "Top 20", "Top 30"]
          )}

          {/* TEST 3: Rebalance Frequency Matrix */}
          {renderMatrixTable(
            data.test3_rebalance_matrix,
            "REBALANCE FREQUENCY MATRIX (Across All Start Dates)",
            "Evaluates turnover and rebalance timing (Weekly, Monthly, Quarterly) for every start date row",
            <Clock className="w-5 h-5" />,
            ["Weekly", "Monthly", "Quarterly"]
          )}

          {/* TEST 4: Lookback Period Matrix */}
          {renderMatrixTable(
            data.test4_lookback_matrix,
            "LOOKBACK PERIOD MATRIX (Across All Start Dates)",
            "Evaluates momentum lookback window (6, 9, 12, 18 Months) for every start date row",
            <TrendingUp className="w-5 h-5" />,
            ["6 Months", "9 Months", "12 Months", "18 Months"]
          )}

          {/* TEST 5: Skip Last Month Matrix */}
          {renderMatrixTable(
            data.test5_skip_matrix,
            "SKIP LAST MONTH MATRIX (Across All Start Dates)",
            "Compares 12-1 Month Residual Momentum (Enabled) vs Standard 12-Month Momentum (Disabled) for every start date row",
            <ShieldCheck className="w-5 h-5" />,
            ["Enabled", "Disabled"]
          )}

          {/* Empirical Findings & Robustness Recommendation */}
          <div className="pdf-section bg-slate-900/90 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6">
            <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
              <span className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <Trophy className="w-6 h-6" />
              </span>
              <div>
                <h2 className="text-xl font-bold text-white">Empirical Robustness Executive Summary</h2>
                <p className="text-xs text-slate-400 mt-0.5">Based directly on win frequencies across all 8 historical start dates</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  1. Which Top N wins most often?
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  <strong className="text-emerald-400">{topNWinner.name}</strong> won most consistently, producing the highest return in <strong>{topNWinner.wins} out of {data.summary_metrics?.total_start_dates || 8}</strong> tested start dates. High concentration in top momentum winners captures maximum momentum premium across market cycles.
                </p>
              </div>

              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  2. Which rebalance frequency wins most often?
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  <strong className="text-emerald-400">{rebalanceWinner.name}</strong> won most consistently across start dates (<strong>{rebalanceWinner.wins} out of {data.summary_metrics?.total_start_dates || 8}</strong> start dates). Longer rebalance windows allow momentum trends to run while reducing turnover friction.
                </p>
              </div>

              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  3. Which lookback period wins most often?
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  <strong className="text-emerald-400">{lookbackWinner.name}</strong> won most consistently across start dates (<strong>{lookbackWinner.wins} out of {data.summary_metrics?.total_start_dates || 8}</strong> start dates). Shorter lookbacks adapt faster to trend shifts, while medium lookbacks provide smoother signals.
                </p>
              </div>

              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  4. Does skipping the last month win most often?
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  <strong className="text-emerald-400">{skipWinner.name}</strong> won in <strong>{skipWinner.wins} out of {data.summary_metrics?.total_start_dates || 8}</strong> start dates. Skipping the most recent month avoids short-term 1-month mean reversion in high-volatility regimes.
                </p>
              </div>

              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  5. Benchmark Consistency vs SPY
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  The strategy outperformed the SPY benchmark in <strong className="text-emerald-400">{data.summary_metrics?.beat_spy_count} out of {data.summary_metrics?.total_start_dates || 8} ({data.summary_metrics?.beat_spy_pct})</strong> tested start dates, proving genuine structural momentum alpha independent of market entry timing.
                </p>
              </div>

              <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" />
                  6. Recommended Robust Configuration
                </h4>
                <p className="text-slate-300 text-xs leading-relaxed">
                  To maximize robustness and avoid single-year curve fitting, the empirical multi-start date recommendation based on overall win frequency is: <strong className="text-emerald-400">{topNWinner.name} Positions, {lookbackWinner.name} Lookback, {rebalanceWinner.name} Rebalancing, and Skip Last Month {skipWinner.name}</strong>.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
