export interface BacktestParams {
  bet_quality: number;
  hrp_alpha: number;
  k_sigmoid: number;
  c_soglia: number;
  k_up: number;
  k_down: number;
}

export interface WeeklyPoint {
  date: string;
  portfolio_value: number;
  weekly_return: number;
  regime: number;
  decay_value: number;
  n_trades: number;
  is_crisis: boolean;
}

export interface BacktestResponse {
  params_hash: string;
  is_default: boolean;
  series: WeeklyPoint[];
  cagr: number;
  sharpe: number;
  max_drawdown: number;
  calmar: number;
  total_return: number;
  n_crisis_weeks: number;
  n_normal_weeks: number;
  spy_series: { date: string; value: number }[];
  spy_cagr: number;
  spy_sharpe: number;
  spy_max_drawdown: number;
  spy_calmar: number;
  spy_total_return: number;
}

export interface RegimeStatus {
  regime_id: number;
  regime_name: string;
  is_crisis: boolean;
  decay_value: number;
  last_friday: string;
  prob_crisis: number;
}
