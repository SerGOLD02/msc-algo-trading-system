import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { resilient } from '../utils/resilient';
import {
  BacktestParams, BacktestResponse, RegimeStatus
} from '../models/backtest.model';

const EMPTY_BT: BacktestResponse = {
  params_hash: '', is_default: false, series: [],
  cagr: 0, sharpe: 0, max_drawdown: 0, calmar: 0,
  total_return: 0, n_crisis_weeks: 0, n_normal_weeks: 0,
  spy_series: [], spy_cagr: 0, spy_sharpe: 0,
  spy_max_drawdown: 0, spy_calmar: 0, spy_total_return: 0
} as BacktestResponse;

@Injectable({ providedIn: 'root' })
export class BacktestService {
  constructor(private api: ApiService) {}

  getDefault(startDate?: string): Observable<BacktestResponse> {
    let path = '/backtest/default';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.get<BacktestResponse>(path).pipe(
      resilient<BacktestResponse>({ ...EMPTY_BT, is_default: true })
    );
  }

  compute(params: BacktestParams, startDate?: string): Observable<BacktestResponse> {
    let path = '/backtest/compute';
    if (startDate) path += `?start_date=${startDate}`;
    return this.api.post<BacktestResponse>(path, params).pipe(
      resilient<BacktestResponse>({ ...EMPTY_BT }, 0)
    );
  }

  getCurrentRegime(): Observable<RegimeStatus> {
    return this.api.get<RegimeStatus>('/hmm/current').pipe(
      resilient({
        regime_id: 0, regime_name: 'N/D',
        is_crisis: false, decay_value: 1.0,
        last_friday: '', prob_crisis: 0.0
      } as RegimeStatus)
    );
  }
}
