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
      <div class="horizon-bar">
        <span class="horizon-label">{{ 'equity_chart.horizon_label' | translate }}</span>
        <button *ngFor="let h of horizons"
                [class.active]="selectedHorizon === h.key"
                (click)="setHorizon(h.key)">
          {{ h.label }}
        </button>
      </div>
      <div *ngIf="hasData" class="returns-box">
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
        <div *ngIf="hasCustom" class="ret-row custom">
          <span class="ret-dot" style="background:#3b82f6"></span>
          <span class="ret-label">{{ 'equity.interactive' | translate }}</span>
          <span class="ret-val" [class.positive]="customReturn >= 0" [class.negative]="customReturn < 0">
            {{ customReturn >= 0 ? '+' : '' }}{{ customReturn.toFixed(2) }}%
          </span>
        </div>
      </div>

      <div *ngIf="hasData" class="metrics-overlay-box">
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
              <tr *ngIf="hasCustom">
                <td class="m-name">{{ 'equity.interactive' | translate }}</td>
                <td>{{ metrics.custom.sharpe.toFixed(2) }}</td>
                <td class="m-neg">{{ metrics.custom.maxDD.toFixed(1) }}%</td>
                <td>{{ metrics.custom.calmar.toFixed(2) }}</td>
              </tr>
            </tbody>
         </table>
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
    .chart-wrapper { position: relative; }
    .equity-chart { height: 540px; width: 100%; }
    .horizon-bar {
      display: flex; gap: 8px; margin-bottom: 12px; align-items: center;
    }
    .horizon-label { font-size: 11px; color: var(--color-text-muted); font-weight: 600; margin-right: 4px; }
    .horizon-bar button {
      padding: 5px 14px; border: 1px solid var(--color-border);
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
    .returns-box {
      position: absolute; top: -52px; right: 0px; z-index: 5;
      background: var(--color-surface, rgba(35,38,53,0.95)); backdrop-filter: blur(8px);
      border: 1px solid var(--color-border); border-radius: 8px;
      padding: 6px 12px; display: flex; flex-direction: column; gap: 3px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .ret-row {
      display: flex; align-items: center; gap: 6px; font-size: 11px;
      font-family: var(--font-numbers, monospace);
    }
    .ret-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .ret-label { color: var(--color-text-muted); font-weight: 500; min-width: 68px; }
    .ret-val { font-weight: 700; font-size: 12px; }
    .ret-val.positive { color: #10b981; }
    .ret-val.negative { color: #ef4444; }

    .metrics-overlay-box {
      position: absolute; top: -52px; right: 190px; z-index: 5;
      background: var(--color-surface, rgba(35,38,53,0.95)); backdrop-filter: blur(8px);
      border: 1px solid var(--color-border); border-radius: 8px;
      padding: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .metrics-title { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--color-text-muted); margin-bottom: 6px; letter-spacing: 0.5px; }
    .metrics-mini-table { border-collapse: collapse; width: 100%; font-size: 11px; }
    .metrics-mini-table th { padding: 4px 8px; text-align: right; color: var(--color-text-muted); font-weight: 600; border-bottom: 1px solid var(--color-border); font-size: 9px; }
    .metrics-mini-table td { padding: 4px 8px; text-align: right; color: var(--color-text-secondary); font-family: var(--font-numbers); font-weight: 600; }
    .m-name { text-align: left !important; color: var(--color-text-muted) !important; font-family: var(--font-sans) !important; font-weight: 500 !important; }
    .m-neg { color: #ef4444 !important; }

    .loading-overlay {
      position: absolute; top: 48px; left: 0; right: 0; bottom: 0;
      background: var(--color-surface, rgba(35,38,53,0.88));
      display: flex; align-items: center; justify-content: center;
      color: var(--color-warning); font-size: 13px; z-index: 10;
      border-radius: 10px; backdrop-filter: blur(4px);
    }
    .no-data {
      height: 540px; display: flex; align-items: center;
      justify-content: center; color: var(--color-text-muted); font-size: 13px;
    }
  `]
})
export class EquityChartComponent implements OnChanges {
  private themeService = inject(ThemeService);
  private langService = inject(LanguageService);

  @Input() defaultBacktest: BacktestResponse | null = null;
  @Input() customBacktest: BacktestResponse | null = null;
  @Input() isLoadingCustom = false;

  chartOptions: EChartsOption = {};
  hasData = false;
  selectedHorizon: HorizonKey = 'MAX';

  algoReturn = 0;
  spyReturn = 0;
  customReturn = 0;
  hasCustom = false;

  metrics = {
    algo: { sharpe: 0, maxDD: 0, calmar: 0 },
    spy: { sharpe: 0, maxDD: 0, calmar: 0 },
    custom: { sharpe: 0, maxDD: 0, calmar: 0 }
  };

  horizons: { key: HorizonKey; label: string; weeks: number }[] = [
    { key: '1M',  label: '1M',  weeks: 4 },
    { key: '3M',  label: '3M',  weeks: 13 },
    { key: '6M',  label: '6M',  weeks: 26 },
    { key: '1A',  label: '1A',  weeks: 52 },
    { key: 'YTD', label: 'YTD', weeks: 0 }, // Special handling
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

    const defaultSeries = this.filterByHorizon(allDefault);
    const customSeries  = this.filterByHorizon(allCustom);
    const spySeries     = this.filterByHorizon(allSpy);

    const rebaseVal = (series: any[], key: string): number[] => {
      if (series.length === 0) return [];
      const first = (series[0] as any)[key] || 1;
      return series.map(p => ((p as any)[key] || 1) / first);
    };

    const defValues = rebaseVal(defaultSeries, 'portfolio_value');
    const spyValues = rebaseVal(spySeries, 'value');
    const custValues = customSeries.length > 0 ? rebaseVal(customSeries, 'portfolio_value') : [];

    this.algoReturn = defValues.length > 0 ? (defValues[defValues.length - 1] - 1) * 100 : 0;
    this.spyReturn = spyValues.length > 0 ? (spyValues[spyValues.length - 1] - 1) * 100 : 0;
    this.hasCustom = custValues.length > 0;
    this.customReturn = custValues.length > 0 ? (custValues[custValues.length - 1] - 1) * 100 : 0;

    this.metrics.algo = this.computeMetrics(defValues);
    this.metrics.spy = this.computeMetrics(spyValues);
    if (this.hasCustom) this.metrics.custom = this.computeMetrics(custValues);

    const allValues = [...defValues, ...spyValues, ...custValues].filter(v => !isNaN(v));
    const dataMin = Math.min(...allValues, 1.0); // Ensure 0% is reachable
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
        textStyle: { color: c.textSecondary, fontSize: 12, fontFamily: 'Inter, sans-serif' },
        itemGap: 20,
        data: [t('equity.legend.system'),
               ...(custValues.length > 0 ? [t('equity.legend.interactive')] : []),
               t('equity.legend.spy')]
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
          name: t('equity.legend.spy'),
          type: 'line',
          data: spyValues,
          lineStyle: { color: '#f97316', width: 2, type: 'dashed' },
          itemStyle: { color: '#f97316' },
          symbol: 'none',
          smooth: 0.3,
        },
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
