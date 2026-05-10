import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { resilient } from '../utils/resilient';
import {
  WeeklySignalResponse, DecayHistoryResponse,
  CorrelationHeatmapResponse, DrawdownResponse,
  ChronosBandsResponse, OperationalStatus,
  YearlyBreakdownResponse, EtfPerformanceResponse,
  RegimeStatsResponse, WeeklyDecompositionResponse
} from '../models/analytics.model';

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  constructor(private api: ApiService) {}

  getWeeklySignals(friday?: string, threshold?: number): Observable<WeeklySignalResponse> {
    let path = '/signals/weekly';
    const params: string[] = [];
    if (friday) params.push(`friday=${friday}`);
    if (threshold !== undefined) params.push(`threshold=${threshold}`);
    if (params.length > 0) path += '?' + params.join('&');

    return this.api.get<WeeklySignalResponse>(path).pipe(
      resilient({
        friday_date: '', available_fridays: [],
        regime_id: 0, regime_name: 'N/D',
        is_crisis: false, n_active: 0, n_filtered: 0,
        signals: []
      } as WeeklySignalResponse)
    );
  }

  getDecayHistory(startDate?: string): Observable<DecayHistoryResponse> {
    let path = '/analytics/decay-history';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<DecayHistoryResponse>(path).pipe(
      resilient({ series: [] } as DecayHistoryResponse)
    );
  }

  getCorrelationHeatmap(window?: string): Observable<CorrelationHeatmapResponse> {
    let path = '/analytics/correlation-heatmap';
    if (window) path += `?window=${window}`;
    return this.api.get<CorrelationHeatmapResponse>(path).pipe(
      resilient({ tickers: [], matrix: [], as_of_date: '', window: window || '52w', avg_correlation: 0, max_correlation: 0, n_high_pairs: 0 } as CorrelationHeatmapResponse)
    );
  }

  getDrawdown(startDate?: string): Observable<DrawdownResponse> {
    const empty = {
      current_drawdown_pct: 0, max_drawdown_pct: 0,
      days_since_peak: 0, peak_date: '', peak_value: 1, current_value: 1
    };
    let path = '/analytics/drawdown';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<DrawdownResponse>(path).pipe(
      resilient({ normal: empty, crisis: empty, combined: empty, as_of_date: '' } as DrawdownResponse)
    );
  }

  getChronosBands(friday?: string): Observable<ChronosBandsResponse> {
    let path = '/analytics/chronos-bands';
    if (friday) path += `?friday=${friday}`;
    return this.api.get<ChronosBandsResponse>(path).pipe(
      resilient({ friday_date: '', available_fridays: [], bands: [] } as ChronosBandsResponse)
    );
  }

  getYearlyBreakdown(startDate?: string): Observable<YearlyBreakdownResponse> {
    let path = '/analytics/yearly-breakdown';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<YearlyBreakdownResponse>(path).pipe(
      resilient({ years: [] } as YearlyBreakdownResponse)
    );
  }

  getOperationalStatus(): Observable<OperationalStatus> {
    return this.api.get<OperationalStatus>('/analytics/operational-status').pipe(
      resilient({
        n_active_trades: 0, regime_name: 'N/D', regime_id: 0,
        is_crisis: false, decay_value: 1.0, last_friday: ''
      } as OperationalStatus)
    );
  }

  getEtfPerformance(startDate?: string): Observable<EtfPerformanceResponse> {
    let path = '/analytics/etf-performance';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<EtfPerformanceResponse>(path).pipe(
      resilient({ start_date: '', end_date: '', etfs: [] } as EtfPerformanceResponse)
    );
  }

  getRegimeStats(startDate?: string): Observable<RegimeStatsResponse> {
    let path = '/analytics/regime-stats';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<RegimeStatsResponse>(path).pipe(
      resilient({ start_date: '', regimes: [] } as RegimeStatsResponse)
    );
  }

  getWeeklyDecomposition(): Observable<WeeklyDecompositionResponse> {
    return this.api.get<WeeklyDecompositionResponse>('/analytics/weekly-decomposition').pipe(
      resilient({ friday_date: '', next_friday: '', contributions: [], total_return: 0 } as WeeklyDecompositionResponse)
    );
  }
}
