export interface RatioSignal {
  ratio_id: string;
  numerator: string;
  denominator: string;
  direction: string;
  long_ticker: string;
  short_ticker: string;
  bet_quality: number;
  is_active: boolean;
  status: string;
  tfm_t5: number | null;
  tfm_projection: string | null;  // "BULLISH" | "BEARISH" | null
  current_ratio: number | null;
  chr_median_t5: number | null;
  chr_width_t5: number | null;
  realized_return: number | null;
}

export interface WeeklySignalResponse {
  friday_date: string;
  available_fridays: string[];
  regime_id: number;
  regime_name: string;
  is_crisis: boolean;
  n_active: number;
  n_filtered: number;
  signals: RatioSignal[];
}

export interface DecayPoint {
  date: string;
  decay_value: number;
  avg_correlation: number;
  regime: number;
}

export interface DecayHistoryResponse {
  series: DecayPoint[];
}

export interface CorrelationHeatmapResponse {
  tickers: string[];
  matrix: number[][];
  as_of_date: string;
  window: string;
  avg_correlation: number;
  max_correlation: number;
  n_high_pairs: number;
}

export interface DrawdownInfo {
  current_drawdown_pct: number;
  max_drawdown_pct: number;
  days_since_peak: number;
  peak_date: string;
  peak_value: number;
  current_value: number;
}

export interface DrawdownHistoryPoint {
  date: string;
  drawdown_pct: number;
}

export interface DrawdownResponse {
  normal: DrawdownInfo;
  crisis: DrawdownInfo;
  combined: DrawdownInfo;
  as_of_date: string;
  history: DrawdownHistoryPoint[];
}

export interface ChronosBand {
  ratio_id: string;
  numerator: string;
  denominator: string;
  current_value: number;
  median: number;
  upper_95: number;
  lower_5: number;
  tfm_t5: number | null;
  tfm_projection: string | null;  // "BULLISH" | "BEARISH" | null
  direction: string;
  is_active: boolean;
}

export interface ChronosBandsResponse {
  friday_date: string;
  available_fridays: string[];
  bands: ChronosBand[];
}

export interface YearlyMetrics {
  year: number;
  cagr: number;
  sharpe: number;
  max_drawdown: number;
  total_return: number;
  n_weeks: number;
  spy_cagr: number;
  spy_sharpe: number;
  spy_max_drawdown: number;
  spy_total_return: number;
}

export interface YearlyBreakdownResponse {
  years: YearlyMetrics[];
}

export interface OperationalStatus {
  n_active_trades: number;
  regime_name: string;
  regime_id: number;
  is_crisis: boolean;
  decay_value: number;
  last_friday: string;
}

// Task 2.2 — ETF Performance
export interface EtfPerformanceItem {
  ticker: string;
  algo_return: number;
  bh_return: number;
  alpha: number;
  n_trades: number;
}

export interface EtfPerformanceResponse {
  start_date: string;
  end_date: string;
  etfs: EtfPerformanceItem[];
}

// Task 2.3 — Regime Stats
export interface RegimeStatItem {
  regime_id: number;
  regime_name: string;
  n_weeks: number;
  win_rate: number;
  avg_return: number;
  total_trades: number;
}

export interface RegimeStatsResponse {
  start_date: string;
  regimes: RegimeStatItem[];
}

// Task 2.6 — Weekly Decomposition
export interface ContributionItem {
  ticker: string;
  weight: number;
  return_pct: number;
  contribution: number;
  trigger_state: 'tp' | 'sl' | 'hold';
}

export interface WeeklyDecompositionResponse {
  friday_date: string;
  next_friday: string;
  contributions: ContributionItem[];
  total_return: number;
}
