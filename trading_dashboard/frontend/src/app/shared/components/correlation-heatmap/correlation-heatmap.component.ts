import {
  Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, effect, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { HeatmapChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, VisualMapComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { EChartsOption } from 'echarts';
import { CorrelationHeatmapResponse } from '../../../core/models/analytics.model';
import { ThemeService } from '../../../core/services/theme.service';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { getChartColors } from '../../../core/utils/chart-colors';

echarts.use([
  HeatmapChart, GridComponent, TooltipComponent,
  VisualMapComponent, CanvasRenderer
]);

interface WindowTab {
  key: string;
  label: string;
}

@Component({
  selector: 'app-correlation-heatmap',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective, TranslatePipe],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="heatmap-wrapper">
      <div class="tab-bar">
        <button *ngFor="let tab of tabs"
                [class.active]="selectedWindow === tab.key"
                (click)="selectWindow(tab.key)">
          {{ tab.label }}
        </button>
      </div>
      <div class="kpi-row" *ngIf="hasData && data">
        <div class="kpi-card">
          <span class="kpi-label">{{ 'heatmap_chart.avg_corr' | translate }}</span>
          <span class="kpi-value" [style.color]="getAvgColor()">
            {{ data.avg_correlation.toFixed(3) }}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">{{ 'heatmap_chart.max_corr' | translate }}</span>
          <span class="kpi-value" [style.color]="getMaxColor()">
            {{ data.max_correlation.toFixed(3) }}
          </span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">{{ 'heatmap_chart.high_pairs' | translate }}</span>
          <span class="kpi-value" [class.high-count]="data.n_high_pairs > 20">
            {{ data.n_high_pairs }} / {{ getTotalPairs() }}
          </span>
        </div>
      </div>
      <div *ngIf="hasData; else noData"
           echarts [options]="chartOptions" [autoResize]="true"
           class="heatmap-chart"></div>
      <ng-template #noData>
        <div class="no-data">{{ 'heatmap_chart.waiting' | translate }}</div>
      </ng-template>
    </div>
  `,
  styles: [`
    .heatmap-wrapper { position: relative; }
    .tab-bar {
      display: flex; gap: 4px; margin-bottom: 14px;
    }
    .tab-bar button {
      padding: 5px 14px; border: 1px solid var(--color-border);
      background: var(--color-surface); color: var(--color-text-muted);
      font-size: 11px; font-weight: 600; border-radius: 6px; cursor: pointer;
      font-family: var(--font-numbers, monospace);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .tab-bar button:hover {
      background: var(--color-border); color: var(--color-text-secondary);
    }
    .tab-bar button.active {
      background: #0891b2; color: #fff; border-color: #0891b2;
    }
    .kpi-row {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;
      margin-bottom: 14px;
    }
    .kpi-card {
      display: flex; flex-direction: column; align-items: center;
      padding: 8px 6px; border-radius: 8px;
      background: var(--color-bg); border: 1px solid var(--color-border);
    }
    .kpi-label {
      font-size: 10px; color: var(--color-text-muted); font-weight: 500;
      text-transform: uppercase; letter-spacing: 0.3px;
      margin-bottom: 4px;
    }
    .kpi-value {
      font-size: 16px; font-weight: 800;
      font-family: var(--font-numbers, monospace);
      font-variant-numeric: tabular-nums;
      color: var(--color-text-primary);
    }
    .kpi-value.high-count { color: #ef4444; }
    .heatmap-chart { height: 1080px; width: 100%; }
    .no-data {
      height: 1080px; display: flex; align-items: center;
      justify-content: center; color: var(--color-text-muted); font-size: 13px;
    }
  `]
})
export class CorrelationHeatmapComponent implements OnChanges {
  private themeService = inject(ThemeService);
  private langService = inject(LanguageService);

  @Input() data: CorrelationHeatmapResponse | null = null;
  @Output() windowChanged = new EventEmitter<string>();

  chartOptions: EChartsOption = {};
  hasData = false;
  selectedWindow = '52w';

  tabs: WindowTab[] = [
    { key: '1w', label: '1S' },
    { key: '1m', label: '1M' },
    { key: '3m', label: '3M' },
    { key: '6m', label: '6M' },
    { key: '52w', label: '1Y' },
  ];

  constructor() {
    effect(() => {
      this.themeService.isDark();
      this.langService.lang();
      if (this.hasData) this.buildChart();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.data && this.data.tickers.length > 0) {
      this.hasData = true;
      if (this.data.window) this.selectedWindow = this.data.window;
      this.buildChart();
    }
  }

  getAvgColor(): string {
    if (!this.data) return '#e8eaf0';
    const avg = this.data.avg_correlation;
    if (avg < 0.40) return '#10b981';
    if (avg < 0.60) return '#f59e0b';
    return '#ef4444';
  }

  getMaxColor(): string {
    if (!this.data) return '#e8eaf0';
    const max = this.data.max_correlation;
    if (max < 0.70) return '#10b981';
    if (max < 0.85) return '#f59e0b';
    return '#ef4444';
  }

  getTotalPairs(): number {
    if (!this.data) return 0;
    const n = this.data.tickers.length;
    return n * (n - 1) / 2;
  }

  selectWindow(key: string): void {
    this.selectedWindow = key;
    this.windowChanged.emit(key);
  }

  private buildChart(): void {
    const c = getChartColors(this.themeService.isDark());
    const t = (s: string) => this.langService.translate(s);
    const tickers = this.data!.tickers;
    const matrix = this.data!.matrix;

    const heatData: any[] = [];
    for (let i = 0; i < tickers.length; i++) {
      for (let j = 0; j < tickers.length; j++) {
        const v = matrix[i][j];
        heatData.push([j, i, v]);
      }
    }

    this.chartOptions = {
      backgroundColor: 'transparent',
      animation: false,
      visualMap: {
        show: true,
        type: 'continuous',
        min: -1,
        max: 1,
        calculable: true,
        orient: 'vertical',
        right: 0,
        top: 'center',
        itemHeight: 500,
        itemWidth: 14,
        text: ['+1.0', '−1.0'],
        textStyle: { color: c.textMuted, fontSize: 12, fontFamily: 'JetBrains Mono, monospace' },
        inRange: {
          color: [
            '#dc2626',  // -1.0  extreme negative
            '#f87171',  // -0.8
            '#22c55e',  // -0.5  moderate negative
            '#86efac',  // -0.3
            '#ffffff',  // 0.0   zero
            '#86efac',  // +0.3
            '#22c55e',  // +0.5  moderate positive
            '#f87171',  // +0.8
            '#dc2626',  // +1.0  extreme positive
          ]
        },
        outOfRange: {
          color: c.border,
          opacity: 0.12,
        },
        precision: 2,
      },
      tooltip: {
        position: 'top',
        backgroundColor: c.tooltipBg,
        borderColor: c.tooltipBorder,
        borderWidth: 1,
        borderRadius: 8,
        padding: [8, 12],
        textStyle: { color: c.tooltipText, fontSize: 12, fontFamily: 'Inter, sans-serif' },
        formatter: (params: any) => {
          const d = params.data ?? params.value;
          const x = tickers[d[0]];
          const y = tickers[d[1]];
          const v = d[2].toFixed(3);
          return `<b>${y}</b> x <b>${x}</b><br/>${t('Regime.prob_crisis').replace('P(Crisis)', 'Corr')}: <b>${v}</b>`;
        }
      },
      grid: {
        left: '8%', right: '6%', top: '2%', bottom: '9%',
        containLabel: false
      },
      xAxis: {
        type: 'category',
        data: tickers,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.textSecondary, fontSize: 10, rotate: 45, fontFamily: 'JetBrains Mono, monospace' },
        axisTick: { show: false },
        splitArea: { show: false },
      },
      yAxis: {
        type: 'category',
        data: tickers,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.textSecondary, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
        axisTick: { show: false },
        splitArea: { show: false },
      },
      series: [{
        type: 'heatmap',
        data: heatData,
        label: {
          show: tickers.length <= 26,
          fontSize: 8,
          fontFamily: 'JetBrains Mono, monospace',
          formatter: (params: any) => {
            const d = params.data ?? params.value;
            const v = d[2];
            if (d[0] === d[1]) return '';
            return v.toFixed(2);
          },
          color: '#1f2937',
        },
        emphasis: {
          itemStyle: {
            borderColor: c.textPrimary,
            borderWidth: 1,
          }
        },
        itemStyle: {
          borderColor: c.surface,
          borderWidth: 1,
          borderRadius: 1,
        },
      }]
    };
  }
}
