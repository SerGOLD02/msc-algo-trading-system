import {
  Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, effect, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, DataZoomComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { EChartsOption } from 'echarts';
import { BacktestResponse, WeeklyPoint } from '../../../core/models/backtest.model';
import { ThemeService } from '../../../core/services/theme.service';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { getChartColors } from '../../../core/utils/chart-colors';

echarts.use([
  LineChart, GridComponent, TooltipComponent,
  LegendComponent, MarkAreaComponent, DataZoomComponent, CanvasRenderer
]);

type HorizonKey = '1M' | '3M' | '6M' | '1A' | 'YTD' | 'MAX';

@Component({
  selector: 'app-equity-chart',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective, TranslatePipe],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="chart-wrapper">
      <div class="chart-top-bar">
        <div class="horizon-bar">
          <span class="horizon-label">{{ 'equity_chart.horizon_label' | translate }}</span>
          <button *ngFor="let h of horizons"
                  [class.active]="selectedHorizon === h.key"
                  (click)="setHorizon(h.key)">
            {{ h.label }}
          </button>
        </div>

        <div *ngIf="hasData" class="stats-container">
          <!-- Box 1: Tabella Metriche di Rischio (Sharpe, Max DD, Calmar) -->
          <div class="metrics-overlay-box">
            <div class="metrics-title">{{ 'equity_chart.metrics_title' | translate }}</div>
            <table class="metrics-mini-table">
              <thead>
                <tr>
                  <th></th>
                  <th>{{ 'equity_chart.metric_sharpe' | translate }}</th>
                  <th>{{ 'equity_chart.metric_max_dd' | translate }}</th>
                  <th>{{ 'equity_chart.metric_calmar' | translate }}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="m-name">{{ 'equity.algo' | translate }}</td>
                  <td>{{ metrics.algo.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.algo.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.algo.calmar.toFixed(2) }}</td>
                </tr>
                <tr>
                  <td class="m-name">S&P 500</td>
                  <td>{{ metrics.spy.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.spy.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.spy.calmar.toFixed(2) }}</td>
                </tr>
                <tr *ngIf="hasVwce">
                  <td class="m-name">VWCE (Acc)</td>
                  <td>{{ metrics.vwce.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.vwce.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.vwce.calmar.toFixed(2) }}</td>
                </tr>
                <tr *ngIf="hasTfm25XgbBase">
                  <td class="m-name">TFM 2.5 + CHR + XGB (Base)</td>
                  <td>{{ metrics.tfm25XgbBase.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.tfm25XgbBase.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.tfm25XgbBase.calmar.toFixed(2) }}</td>
                </tr>
                <tr *ngIf="hasTfm3XgbOptuna">
                  <td class="m-name">TFM 3.0 + CHR + XGB (Opt)</td>
                  <td>{{ metrics.tfm3XgbOptuna.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.tfm3XgbOptuna.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.tfm3XgbOptuna.calmar.toFixed(2) }}</td>
                </tr>
                <tr *ngIf="hasTimestralXgbOptuna || hasTimestralXgbBase">
                  <td class="m-name">Timestral + XGB (Opt)</td>
                  <td>{{ metrics.timestralXgb.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.timestralXgb.maxDD.toFixed(1) }}%</td>
                  <td>{{ metrics.timestralXgb.calmar.toFixed(2) }}</td>
                </tr>
                <tr *ngIf="hasTimestralChrXgbOptuna">
                  <td class="m-name" style="font-weight: 700 !important; color: #f59e0b !important;">Timestral + CHR + XGB (Opt)</td>
                  <td style="color: #f59e0b;">{{ metrics.timestralChrXgb.sharpe.toFixed(2) }}</td>
                  <td class="m-neg">{{ metrics.timestralChrXgb.maxDD.toFixed(1) }}%</td>
                  <td style="color: #f59e0b;">{{ metrics.timestralChrXgb.calmar.toFixed(2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Box 2: Box Rendimenti Cumulati (%) e Legenda -->
          <div class="returns-box">
            <div class="ret-header-title">{{ 'equity_chart.returns_title' | translate }}</div>
            <div class="ret-row algo">
              <span class="ret-dot" style="background:#059669"></span>
              <span class="ret-label">{{ 'equity.algo' | translate }}</span>
              <span class="ret-val" [class.positive]="algoReturn >= 0" [class.negative]="algoReturn < 0">
                {{ algoReturn >= 0 ? '+' : '' }}{{ algoReturn.toFixed(2) }}%
              </span>
            </div>
            <div class="ret-row spy">
              <span class="ret-dot" style="background:#f97316"></span>
              <span class="ret-label">S&P 500</span>
              <span class="ret-val" [class.positive]="spyReturn >= 0" [class.negative]="spyReturn < 0">
                {{ spyReturn >= 0 ? '+' : '' }}{{ spyReturn.toFixed(2) }}%
              </span>
            </div>
            <div *ngIf="hasVwce" class="ret-row vwce">
              <span class="ret-dot" style="background:#38bdf8"></span>
              <span class="ret-label">VWCE (Acc)</span>
              <span class="ret-val" [class.positive]="vwceReturn >= 0" [class.negative]="vwceReturn < 0">
                {{ vwceReturn >= 0 ? '+' : '' }}{{ vwceReturn.toFixed(2) }}%
              </span>
            </div>
            <div *ngIf="hasTfm25XgbBase" class="ret-row tfm25-xgb">
              <span class="ret-dot" style="background:#06b6d4"></span>
              <span class="ret-label">TFM 2.5 + CHR + XGB (Base)</span>
              <span class="ret-val" [class.positive]="tfm25XgbBaseReturn >= 0" [class.negative]="tfm25XgbBaseReturn < 0">
                {{ tfm25XgbBaseReturn >= 0 ? '+' : '' }}{{ tfm25XgbBaseReturn.toFixed(2) }}%
              </span>
            </div>
            <div *ngIf="hasTfm3XgbOptuna" class="ret-row tfm3-xgb">
              <span class="ret-dot" style="background:#a855f7"></span>
              <span class="ret-label">TFM 3.0 + CHR + XGB (Opt)</span>
              <span class="ret-val" [class.positive]="tfm3XgbOptunaReturn >= 0" [class.negative]="tfm3XgbOptunaReturn < 0">
                {{ tfm3XgbOptunaReturn >= 0 ? '+' : '' }}{{ tfm3XgbOptunaReturn.toFixed(2) }}%
              </span>
            </div>
            <div *ngIf="hasTimestralXgbOptuna || hasTimestralXgbBase" class="ret-row timestral-xgb">
              <span class="ret-dot" style="background:#ec4899"></span>
              <span class="ret-label">Timestral + XGB (Opt)</span>
              <span class="ret-val" [class.positive]="timestralXgbReturn >= 0" [class.negative]="timestralXgbReturn < 0">
                {{ timestralXgbReturn >= 0 ? '+' : '' }}{{ timestralXgbReturn.toFixed(2) }}%
              </span>
            </div>
            <div *ngIf="hasTimestralChrXgbOptuna" class="ret-row timestral-chr-xgb">
              <span class="ret-dot" style="background:#f59e0b"></span>
              <span class="ret-label" style="font-weight: 700; color: #f59e0b;">Timestral + CHR + XGB (Opt)</span>
              <span class="ret-val" [class.positive]="timestralChrXgbReturn >= 0" [class.negative]="timestralChrXgbReturn < 0">
                {{ timestralChrXgbReturn >= 0 ? '+' : '' }}{{ timestralChrXgbReturn.toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>
      </div>

      <div *ngIf="isLoadingCustom" class="loading-overlay">
        <span>{{ 'equity.loading' | translate }}</span>
      </div>
      <div *ngIf="hasData; else noData"
           echarts
           [options]="chartOptions"
           [autoResize]="true"
           class="equity-chart">
      </div>
      <ng-template #noData>
        <div class="no-data">
          <span>{{ 'equity.waiting' | translate }}</span>
        </div>
      </ng-template>
    </div>
  `,
  styles: [`
    .chart-wrapper { position: relative; width: 100%; }
    .equity-chart { height: 560px; width: 100%; margin-top: 8px; }
    
    .chart-top-bar {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 12px;
      width: 100%;
    }
    
    .horizon-bar {
      display: flex; gap: 6px; align-items: center; flex-wrap: wrap; padding-top: 4px;
    }
    .horizon-label { font-size: 11px; color: var(--color-text-muted); font-weight: 600; margin-right: 4px; }
    .horizon-bar button {
      padding: 5px 12px; border: 1px solid var(--color-border);
      background: var(--color-surface); color: var(--color-text-muted); font-size: 11px;
      font-weight: 600; border-radius: 6px; cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      font-family: var(--font-numbers, monospace);
    }
    .horizon-bar button:hover {
      background: var(--color-border-subtle); color: var(--color-text-secondary);
    }
    .horizon-bar button.active {
      background: var(--color-accent); color: #ffffff; border-color: var(--color-accent);
    }

    .stats-container {
      display: flex;
      align-items: stretch;
      gap: 18px;
      flex-wrap: wrap;
      margin-left: auto;
    }

    .metrics-overlay-box {
      background: var(--color-surface, rgba(35,38,53,0.95)); backdrop-filter: blur(8px);
      border: 1px solid var(--color-border); border-radius: 8px;
      padding: 8px 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      min-width: 290px;
    }
    .metrics-title, .ret-header-title {
      font-size: 9.5px; font-weight: 700; text-transform: uppercase;
      color: var(--color-text-muted); margin-bottom: 6px; letter-spacing: 0.5px;
      border-bottom: 1px solid var(--color-border-subtle, rgba(255,255,255,0.06));
      padding-bottom: 3px;
    }
    .metrics-mini-table { border-collapse: collapse; width: 100%; font-size: 10px; }
    .metrics-mini-table th { padding: 3px 6px; text-align: right; color: var(--color-text-muted); font-weight: 600; border-bottom: 1px solid var(--color-border); font-size: 8.5px; }
    .metrics-mini-table td { padding: 3px 6px; text-align: right; color: var(--color-text-secondary); font-family: var(--font-numbers); font-weight: 600; }
    .m-name { text-align: left !important; color: var(--color-text-muted) !important; font-family: var(--font-sans) !important; font-weight: 500 !important; font-size: 9.5px; }
    .m-neg { color: #ef4444 !important; }

    .returns-box {
      background: var(--color-surface, rgba(35,38,53,0.95)); backdrop-filter: blur(8px);
      border: 1px solid var(--color-border); border-radius: 8px;
      padding: 8px 12px; display: flex; flex-direction: column; gap: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      min-width: 260px;
    }
    .ret-row {
      display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 10px;
      font-family: var(--font-numbers, monospace);
    }
    .ret-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
    .ret-label { color: var(--color-text-muted); font-weight: 500; flex: 1; margin-left: 4px; font-family: var(--font-sans); font-size: 9.5px; }
    .ret-val { font-weight: 700; font-size: 11px; text-align: right; }
    .ret-val.positive { color: #10b981; }
    .ret-val.negative { color: #ef4444; }

    .loading-overlay {
      position: absolute; top: 48px; left: 0; right: 0; bottom: 0;
      background: var(--color-surface, rgba(35,38,53,0.88));
      display: flex; align-items: center; justify-content: center;
      color: var(--color-warning); font-size: 13px; z-index: 10;
      border-radius: 10px; backdrop-filter: blur(4px);
    }
    .no-data {
      height: 560px; display: flex; align-items: center;
      justify-content: center; color: var(--color-text-muted); font-size: 13px;
    }
  `]
})
export class EquityChartComponent implements OnChanges {
  private themeService = inject(ThemeService);
  private langService = inject(LanguageService);

  @Input() defaultBacktest: BacktestResponse | null = null;
  @Input() customBacktest: BacktestResponse | null = null;
  @Input() timesfm3Backtest: any = null;
  @Input() tfm3XgbOptunaBacktest: any = null;
  @Input() tfm25XgbBaseBacktest: any = null;
  @Input() timestralXgbOptunaBacktest: any = null;
  @Input() timestralXgbBaseBacktest: any = null;
  @Input() timestralChrXgbOptunaBacktest: any = null;
  @Input() vwceBacktest: any = null;
  @Input() isLoadingCustom = false;

  chartOptions: EChartsOption = {};
  hasData = false;
  selectedHorizon: HorizonKey = 'MAX';

  algoReturn = 0;
  spyReturn = 0;
  vwceReturn = 0;
  customReturn = 0;
  tfm3XgbOptunaReturn = 0;
  tfm25XgbBaseReturn = 0;
  timestralXgbReturn = 0;
  timestralChrXgbReturn = 0;

  hasCustom = false;
  hasVwce = false;
  hasTfm3XgbOptuna = false;
  hasTfm25XgbBase = false;
  hasTimestralXgbOptuna = false;
  hasTimestralXgbBase = false;
  hasTimestralChrXgbOptuna = false;

  metrics = {
    algo:             { sharpe: 0, maxDD: 0, calmar: 0 },
    spy:              { sharpe: 0, maxDD: 0, calmar: 0 },
    vwce:             { sharpe: 0, maxDD: 0, calmar: 0 },
    custom:           { sharpe: 0, maxDD: 0, calmar: 0 },
    tfm25XgbBase:     { sharpe: 0, maxDD: 0, calmar: 0 },
    tfm3XgbOptuna:    { sharpe: 0, maxDD: 0, calmar: 0 },
    timestralXgb:     { sharpe: 0, maxDD: 0, calmar: 0 },
    timestralChrXgb:  { sharpe: 0, maxDD: 0, calmar: 0 },
  };

  horizons: { key: HorizonKey; label: string; weeks: number }[] = [
    { key: '1M',  label: '1M',  weeks: 4 },
    { key: '3M',  label: '3M',  weeks: 13 },
    { key: '6M',  label: '6M',  weeks: 26 },
    { key: '1A',  label: '1A',  weeks: 52 },
    { key: 'YTD', label: 'YTD', weeks: 0 },
    { key: 'MAX', label: 'MAX', weeks: 9999 },
  ];

  constructor() {
    effect(() => {
      this.themeService.isDark();
      this.langService.lang();
      if (this.hasData) this.buildChart();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.defaultBacktest && this.defaultBacktest.series.length > 0) {
      this.hasData = true;
      this.buildChart();
    }
  }

  setHorizon(key: HorizonKey): void {
    this.selectedHorizon = key;
    this.buildChart();
  }

  private filterByHorizon<T extends { date: string }>(series: T[]): T[] {
    if (this.selectedHorizon === 'MAX') return series;
    
    if (this.selectedHorizon === 'YTD') {
      const currentYear = new Date().getFullYear().toString();
      return series.filter(p => p.date.startsWith(currentYear));
    }

    const h = this.horizons.find(x => x.key === this.selectedHorizon);
    if (!h || series.length <= h.weeks) return series;
    return series.slice(-h.weeks);
  }

  private computeMetrics(values: number[]): { sharpe: number, maxDD: number, calmar: number } {
    if (values.length < 2) return { sharpe: 0, maxDD: 0, calmar: 0 };
    
    const weeklyReturns: number[] = [];
    for (let i = 1; i < values.length; i++) {
        weeklyReturns.push((values[i] - values[i-1]) / values[i-1]);
    }
    
    const n = weeklyReturns.length;
    const avgRet = weeklyReturns.reduce((a, b) => a + b, 0) / n;
    const stdRet = Math.sqrt(weeklyReturns.reduce((a, b) => a + Math.pow(b - avgRet, 2), 0) / n);
    
    const sharpe = stdRet > 0 ? (avgRet * 52) / (stdRet * Math.sqrt(52)) : 0;
    
    let maxDD = 0;
    let peak = values[0];
    for (const v of values) {
      if (v > peak) peak = v;
      const dd = (v - peak) / peak;
      if (dd < maxDD) maxDD = dd;
    }

    const totalReturn = values[values.length - 1] / values[0] - 1;
    const cagr = n > 0 ? Math.pow(1 + totalReturn, 52 / n) - 1 : 0;
    const calmar = maxDD !== 0 ? cagr / Math.abs(maxDD) : 0;

    return { sharpe, maxDD: maxDD * 100, calmar };
  }

  private buildChart(): void {
    const allDefault = this.defaultBacktest?.series ?? [];
    const allCustom  = this.customBacktest?.series  ?? [];
    const allSpy     = this.defaultBacktest?.spy_series ?? [];
    const allVwce    = (this.vwceBacktest?.series ?? this.defaultBacktest?.vwce_series ?? []) as any[];

    const defaultSeries = this.filterByHorizon(allDefault);
    const customSeries  = this.filterByHorizon(allCustom);
    const spySeries     = this.filterByHorizon(allSpy);
    const vwceSeries    = this.filterByHorizon(allVwce);

    const rebaseVal = (series: any[], key: string): number[] => {
      if (series.length === 0) return [];
      const first = (series[0] as any)[key] || 1;
      return series.map(p => ((p as any)[key] || 1) / first);
    };

    const defValues  = rebaseVal(defaultSeries, 'portfolio_value');
    const spyValues  = rebaseVal(spySeries, 'value');
    const vwceValues = vwceSeries.length > 0 ? rebaseVal(vwceSeries, 'value') : [];
    const custValues = customSeries.length > 0 ? rebaseVal(customSeries, 'portfolio_value') : [];

    const allTfm3XgbOptuna = (this.tfm3XgbOptunaBacktest?.series ?? []) as any[];
    const tfm3XgbOptunaSeries = this.filterByHorizon(allTfm3XgbOptuna) as any[];
    const tfm3XgbOptunaValues = tfm3XgbOptunaSeries.length > 0
      ? (() => { const first = tfm3XgbOptunaSeries[0].value || 1; return tfm3XgbOptunaSeries.map((p: any) => (p.value || 1) / first); })()
      : [];

    const allTfm25XgbBase = (this.tfm25XgbBaseBacktest?.series ?? []) as any[];
    const tfm25XgbBaseSeries = this.filterByHorizon(allTfm25XgbBase) as any[];
    const tfm25XgbBaseValues = tfm25XgbBaseSeries.length > 0
      ? (() => { const first = tfm25XgbBaseSeries[0].value || 1; return tfm25XgbBaseSeries.map((p: any) => (p.value || 1) / first); })()
      : [];

    const allTimestralXgb = ((this.timestralXgbOptunaBacktest || this.timestralXgbBaseBacktest)?.series ?? []) as any[];
    const timestralXgbSeries = this.filterByHorizon(allTimestralXgb) as any[];
    const timestralXgbValues = timestralXgbSeries.length > 0
      ? (() => { const first = timestralXgbSeries[0].value || 1; return timestralXgbSeries.map((p: any) => (p.value || 1) / first); })()
      : [];

    const allTimestralChrXgb = (this.timestralChrXgbOptunaBacktest?.series ?? []) as any[];
    const timestralChrXgbSeries = this.filterByHorizon(allTimestralChrXgb) as any[];
    const timestralChrXgbValues = timestralChrXgbSeries.length > 0
      ? (() => { const first = timestralChrXgbSeries[0].value || 1; return timestralChrXgbSeries.map((p: any) => (p.value || 1) / first); })()
      : [];

    this.algoReturn             = defValues.length  > 0 ? (defValues[defValues.length - 1] - 1) * 100 : 0;
    this.spyReturn              = spyValues.length  > 0 ? (spyValues[spyValues.length - 1] - 1) * 100 : 0;
    this.hasVwce                = vwceValues.length > 0;
    this.vwceReturn             = vwceValues.length > 0 ? (vwceValues[vwceValues.length - 1] - 1) * 100 : 0;
    this.hasCustom              = custValues.length > 0;
    this.customReturn           = custValues.length > 0 ? (custValues[custValues.length - 1] - 1) * 100 : 0;
    this.hasTfm3XgbOptuna       = tfm3XgbOptunaValues.length > 0;
    this.tfm3XgbOptunaReturn    = tfm3XgbOptunaValues.length > 0 ? (tfm3XgbOptunaValues[tfm3XgbOptunaValues.length - 1] - 1) * 100 : 0;
    this.hasTfm25XgbBase        = tfm25XgbBaseValues.length > 0;
    this.tfm25XgbBaseReturn     = tfm25XgbBaseValues.length > 0 ? (tfm25XgbBaseValues[tfm25XgbBaseValues.length - 1] - 1) * 100 : 0;
    this.hasTimestralXgbOptuna  = !!this.timestralXgbOptunaBacktest;
    this.hasTimestralXgbBase    = !!this.timestralXgbBaseBacktest;
    this.timestralXgbReturn     = timestralXgbValues.length > 0 ? (timestralXgbValues[timestralXgbValues.length - 1] - 1) * 100 : 0;
    this.hasTimestralChrXgbOptuna = timestralChrXgbValues.length > 0;
    this.timestralChrXgbReturn  = timestralChrXgbValues.length > 0 ? (timestralChrXgbValues[timestralChrXgbValues.length - 1] - 1) * 100 : 0;

    this.metrics.algo                = this.computeMetrics(defValues);
    this.metrics.spy                 = this.computeMetrics(spyValues);
    if (this.hasVwce)                this.metrics.vwce                = this.computeMetrics(vwceValues);
    if (this.hasCustom)              this.metrics.custom              = this.computeMetrics(custValues);
    if (this.hasTfm25XgbBase)        this.metrics.tfm25XgbBase        = this.computeMetrics(tfm25XgbBaseValues);
    if (this.hasTfm3XgbOptuna)       this.metrics.tfm3XgbOptuna       = this.computeMetrics(tfm3XgbOptunaValues);
    if (timestralXgbValues.length > 0) this.metrics.timestralXgb      = this.computeMetrics(timestralXgbValues);
    if (timestralChrXgbValues.length > 0) this.metrics.timestralChrXgb = this.computeMetrics(timestralChrXgbValues);

    const allValues = [
      ...defValues, ...spyValues, ...vwceValues, ...custValues,
      ...tfm25XgbBaseValues, ...tfm3XgbOptunaValues,
      ...timestralXgbValues, ...timestralChrXgbValues
    ].filter(v => !isNaN(v));

    const dataMin = Math.min(...allValues, 1.0);
    const dataMax = Math.max(...allValues, 1.0);
    const range = dataMax - dataMin || 0.01;
    const yMin = dataMin - range * 0.15;
    const yMax = dataMax + range * 0.15;

    const markAreas: [object, object][] = [];
    let start: string | null = null;
    for (const p of defaultSeries) {
      if (p.is_crisis && !start) start = p.date;
      if (!p.is_crisis && start) {
        markAreas.push([{ xAxis: start }, { xAxis: p.date }]);
        start = null;
      }
    }
    if (start) markAreas.push([{ xAxis: start }, { xAxis: defaultSeries.at(-1)?.date ?? start }]);

    const c = getChartColors(this.themeService.isDark());
    const t = (s: string) => this.langService.translate(s);

    this.chartOptions = {
      backgroundColor: 'transparent',
      animation: true,
      animationDuration: 600,
      tooltip: {
        trigger: 'axis',
        backgroundColor: c.tooltipBg,
        borderColor: c.tooltipBorder,
        borderWidth: 1,
        borderRadius: 10,
        padding: [12, 16],
        textStyle: { color: c.tooltipText, fontSize: 12, fontFamily: 'Inter, sans-serif' },
        formatter: (params: any) => {
          const date = params[0]?.axisValue ?? '';
          let html = `<div style="font-weight:600;margin-bottom:6px;color:${c.tooltipText}">${date}</div>`;
          for (const p of params) {
            const val = ((Number(p.value) - 1) * 100).toFixed(2);
            const sign = Number(p.value) >= 1 ? '+' : '';
            html += `<div style="color:${p.color};margin:2px 0;font-weight:500">
              ${p.seriesName}: ${sign}${val}%
            </div>`;
          }
          return html;
        }
      },
      legend: {
        bottom: 4,
        textStyle: { color: c.textSecondary, fontSize: 11, fontFamily: 'Inter, sans-serif' },
        itemGap: 14,
        data: [
          t('equity.legend.system'),
          'S&P 500',
          ...(vwceValues.length > 0 ? ['VWCE (Acc)'] : []),
          ...(tfm25XgbBaseValues.length > 0 ? ['TFM 2.5 + CHR + XGB (Base)'] : []),
          ...(tfm3XgbOptunaValues.length > 0 ? ['TFM 3.0 + CHR + XGB (Opt)'] : []),
          ...(timestralXgbValues.length > 0 ? ['Timestral + XGB (Opt)'] : []),
          ...(timestralChrXgbValues.length > 0 ? ['Timestral + CHR + XGB (Opt)'] : []),
          ...(custValues.length > 0 ? [t('equity.legend.interactive')] : []),
        ]
      },
      grid: { left: '4%', right: '4%', top: '6%', bottom: '13%', containLabel: true },
      xAxis: {
        type: 'category',
        data: defaultSeries.map(p => p.date),
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel, fontSize: 10, rotate: 30 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        min: yMin,
        max: yMax,
        axisLine: { show: false },
        axisLabel: {
          color: c.axisLabel, fontSize: 11,
          formatter: (v: number) => {
            const pct = (v - 1) * 100;
            return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
          }
        },
        splitLine: { lineStyle: { color: c.splitLine, type: 'dashed' } },
      },
      series: [
        {
          name: 'S&P 500',
          type: 'line',
          data: spyValues,
          lineStyle: { color: '#f97316', width: 2, type: 'dashed' },
          itemStyle: { color: '#f97316' },
          symbol: 'none',
          smooth: 0.3,
        },
        ...(vwceValues.length > 0 ? [{
          name: 'VWCE (Acc)',
          type: 'line' as const,
          data: vwceValues,
          lineStyle: { color: '#38bdf8', width: 2, type: 'dashed' as const },
          itemStyle: { color: '#38bdf8' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
        {
          name: t('equity.legend.system'),
          type: 'line',
          data: defValues,
          lineStyle: { color: '#059669', width: 2.5 },
          itemStyle: { color: '#059669' },
          symbol: 'none',
          smooth: 0.3,
          areaStyle: {
            color: new (echarts as any).graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(5,150,105,0.12)' },
              { offset: 1, color: 'rgba(5,150,105,0.0)' }
            ])
          },
          markArea: markAreas.length > 0 ? {
            silent: true,
            itemStyle: { color: 'rgba(239, 68, 68, 0.08)' },
            data: markAreas,
          } : undefined,
        },
        ...(tfm25XgbBaseValues.length > 0 ? [{
          name: 'TFM 2.5 + CHR + XGB (Base)',
          type: 'line' as const,
          data: tfm25XgbBaseValues,
          lineStyle: { color: '#06b6d4', width: 2, type: 'dashed' as const },
          itemStyle: { color: '#06b6d4' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
        ...(tfm3XgbOptunaValues.length > 0 ? [{
          name: 'TFM 3.0 + CHR + XGB (Opt)',
          type: 'line' as const,
          data: tfm3XgbOptunaValues,
          lineStyle: { color: '#a855f7', width: 2.5, type: 'solid' as const },
          itemStyle: { color: '#a855f7' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
        ...(timestralXgbValues.length > 0 ? [{
          name: 'Timestral + XGB (Opt)',
          type: 'line' as const,
          data: timestralXgbValues,
          lineStyle: { color: '#ec4899', width: 2.5, type: 'solid' as const },
          itemStyle: { color: '#ec4899' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
        ...(timestralChrXgbValues.length > 0 ? [{
          name: 'Timestral + CHR + XGB (Opt)',
          type: 'line' as const,
          data: timestralChrXgbValues,
          lineStyle: { color: '#f59e0b', width: 2.5, type: 'solid' as const },
          itemStyle: { color: '#f59e0b' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
        ...(custValues.length > 0 ? [{
          name: t('equity.legend.interactive'),
          type: 'line' as const,
          data: custValues,
          lineStyle: { color: '#3b82f6', width: 2, type: 'dotted' as const },
          itemStyle: { color: '#3b82f6' },
          symbol: 'none',
          smooth: 0.3,
        }] : []),
      ],
    };
  }
}
