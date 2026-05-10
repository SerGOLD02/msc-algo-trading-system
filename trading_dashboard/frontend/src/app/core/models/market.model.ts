export interface IndexSummary {
  name: string;
  ticker: string;
  last_price: number;
  change_1d_pct: number;
  change_1w_pct: number;
  change_1m_pct: number;
  change_1y_pct: number;
  change_ytd_pct: number;
}

export interface AssetPrice {
  ticker: string;
  last_price: number;
  change_1d_pct: number;
  change_1w_pct: number;
  change_1m_pct: number;
  change_1y_pct: number;
  change_ytd_pct: number;
  volume: number;
  is_etf: boolean;
}

export interface MarketSnapshot {
  indices: IndexSummary[];
  assets: AssetPrice[];
  last_updated: string;
  market_open: boolean;
  next_friday: string;
  seconds_to_friday_close: number;
}
