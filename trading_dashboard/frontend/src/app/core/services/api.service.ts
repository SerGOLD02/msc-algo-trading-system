import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { delay } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { MOCK_DATA } from '../utils/mock-data';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  get<T>(path: string): Observable<T> {
    if (environment.useMockData) {
      return of(this.getMockResponse(path) as T).pipe(delay(150));
    }
    return this.http.get<T>(`${this.base}${path}`);
  }

  post<T>(path: string, body: unknown): Observable<T> {
    if (environment.useMockData) {
      return of(this.postMockResponse(path, body) as T).pipe(delay(250));
    }
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  private getQueryParam(path: string, paramName: string): string | null {
    const urlParts = path.split('?');
    if (urlParts.length < 2) return null;
    const params = urlParts[1].split('&');
    for (const p of params) {
      const pair = p.split('=');
      if (pair[0] === paramName) return decodeURIComponent(pair[1]);
    }
    return null;
  }

  private getMockResponse(path: string): any {
    const basePath = path.split('?')[0];

    switch (basePath) {
      case '/backtest/default':
        return MOCK_DATA.defaultBacktest;
      case '/backtest/timesfm3':
        return MOCK_DATA.timesfm3Backtest;
      case '/hmm/current':
        return MOCK_DATA.currentRegime;
      case '/market/snapshot':
        return MOCK_DATA.marketSnapshot;
      case '/signals/weekly': {
        const keys = Object.keys(MOCK_DATA.weeklySignals).sort().reverse();
        let friday = this.getQueryParam(path, 'friday') || keys[0];
        if (!MOCK_DATA.weeklySignals[friday]) {
          friday = keys[0];
        }
        return MOCK_DATA.weeklySignals[friday];
      }
      case '/analytics/decay-history':
        return MOCK_DATA.decayHistory;
      case '/analytics/correlation-heatmap': {
        const window = this.getQueryParam(path, 'window') || '52w';
        return MOCK_DATA.correlationHeatmap[window] || MOCK_DATA.correlationHeatmap['52w'];
      }
      case '/analytics/drawdown':
        return MOCK_DATA.drawdown;
      case '/analytics/chronos-bands': {
        const keys = Object.keys(MOCK_DATA.chronosBands).sort().reverse();
        let friday = this.getQueryParam(path, 'friday') || keys[0];
        if (!MOCK_DATA.chronosBands[friday]) {
          friday = keys[0];
        }
        return MOCK_DATA.chronosBands[friday];
      }
      case '/analytics/yearly-breakdown':
        return MOCK_DATA.yearlyBreakdown;
      case '/analytics/operational-status':
        return MOCK_DATA.operationalStatus;
      case '/analytics/etf-performance':
        return MOCK_DATA.etfPerformance;
      case '/analytics/regime-stats':
        return MOCK_DATA.regimeStats;
      case '/analytics/weekly-decomposition':
        return MOCK_DATA.weeklyDecomposition;
      default:
        console.warn(`[ApiService Mock] Unknown GET path: ${path}`);
        return {};
    }
  }

  private postMockResponse(path: string, body: any): any {
    const basePath = path.split('?')[0];

    if (basePath === '/backtest/compute') {
      const params = body || {};
      const defaultParams = {
        bet_quality: 0.50,
        hrp_alpha: 0.50,
        k_sigmoid: 10.0,
        c_soglia: 0.50,
        k_up: 1.25,
        k_down: 1.50
      };

      // Calculate a multiplier for returns based on parameters
      let multiplier = 1.0;
      multiplier += ((params.bet_quality ?? 0.5) - defaultParams.bet_quality) * -0.2;
      multiplier += ((params.hrp_alpha ?? 0.5) - defaultParams.hrp_alpha) * 0.15;
      multiplier += ((params.k_sigmoid ?? 10.0) - defaultParams.k_sigmoid) * 0.01;
      multiplier += ((params.c_soglia ?? 0.5) - defaultParams.c_soglia) * 0.1;
      multiplier += ((params.k_up ?? 1.25) - defaultParams.k_up) * 0.25;
      multiplier += ((params.k_down ?? 1.5) - defaultParams.k_down) * -0.15;

      // Prevent multiplier from going too extreme
      multiplier = Math.max(0.4, Math.min(2.0, multiplier));

      // Clone default backtest
      const customBt = JSON.parse(JSON.stringify(MOCK_DATA.defaultBacktest));
      customBt.is_default = false;

      // Recompute series
      let portValue = 1.0;
      for (let i = 0; i < customBt.series.length; i++) {
        const pt = customBt.series[i];
        if (i === 0) {
          pt.portfolio_value = 1.0;
          pt.weekly_return = 0.0;
        } else {
          pt.weekly_return = pt.weekly_return * multiplier;
          portValue = portValue * (1 + pt.weekly_return);
          pt.portfolio_value = Number(portValue.toFixed(6));
          pt.weekly_return = Number(pt.weekly_return.toFixed(6));
        }
      }

      // Recompute metrics
      customBt.total_return = Number((portValue - 1.0).toFixed(6));
      const nWeeks = customBt.series.length - 1;
      customBt.cagr = Number((Math.pow(1 + customBt.total_return, 52 / nWeeks) - 1).toFixed(6));
      customBt.sharpe = Number((MOCK_DATA.defaultBacktest.sharpe * (multiplier >= 1 ? 1 + (multiplier - 1) * 0.3 : 1 - (1 - multiplier) * 0.5)).toFixed(3));
      customBt.max_drawdown = Number((MOCK_DATA.defaultBacktest.max_drawdown * (multiplier >= 1 ? 1 + (multiplier - 1) * 0.4 : 1 - (1 - multiplier) * 0.6)).toFixed(6));
      customBt.calmar = Number((customBt.cagr / Math.abs(customBt.max_drawdown || 0.001)).toFixed(3));

      return customBt;
    }

    console.warn(`[ApiService Mock] Unknown POST path: ${path}`);
    return {};
  }
}
