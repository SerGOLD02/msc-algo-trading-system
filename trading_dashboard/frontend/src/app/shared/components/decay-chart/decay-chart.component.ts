import {
  Component, Input, OnChanges, SimpleChanges, effect, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { EChartsOption } from 'echarts';
import { DecayHistoryResponse } from '../../../core/models/analytics.model';
import { ThemeService } from '../../../core/services/theme.service';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { getChartColors } from '../../../core/utils/chart-colors';

echarts.use([
  LineChart, GridComponent, TooltipComponent,
  LegendComponent, MarkAreaComponent, MarkLineComponent, CanvasRenderer
]);

@Component({
  selector: 'app-decay-chart',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective, TranslatePipe],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="decay-wrapper">
      <div class="decay-info">
        <div class="info-item">
          <span class="info-label">{{ 'decay_chart.current_decay' | translate }}</span>
          <span class="info-val" [class.low]="currentDecay < 0.5">
            {{ currentDecay.toFixed(3) }}
          </span>
        </div>
        <div class="info-item">
          <span class="info-label">{{ 'decay_chart.avg_corr' | translate }}</span>
          <span class="info-val" [class.high]="currentCorr > 0.5">
            {{ currentCorr.toFixed(3) }}
          </span>
        </div>
        <div class="info-item">
          <span class="info-label">{{ 'decay_chart.exposure' | translate }}</span>
          <span class="info-val" [class.low]="currentDecay < 0.5">
            {{ (currentDecay * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
      <div *ngIf="hasData; else noData"
           echarts [options]="chartOptions" [autoResize]="true"
           class="decay-chart"></div>
      <div class="decay-explain">
        <span>{{ 'decay_chart.explain_high' | translate }}</span>
        <span>{{ 'decay_chart.explain_low' | translate }}</span>
      </div>
      <ng-template #noData>
        <div class="no-data">{{ 'decay_chart.waiting' | translate }}</div>
      </ng-template>
    </div>
  `,
  styles: [`
    .decay-wrapper { position: relative; }
    .decay-chart { height: 420px; width: 100%; }
    .decay-info {
      display: flex; gap: 20px; margin-bottom: 10px;
    }
    .info-item {
      display: flex; flex-direction: column; gap: 2px;
    }
    .info-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px;
      color: var(--color-text-muted); font-weight: 600;
    }
    .info-val {
      font-size: 18px; font-weight: 700; color: #059669;
      font-family: var(--font-numbers, 'JetBrains Mono', monospace);
    }
    .info-val.low { color: #dc2626; }
    .info-val.high { color: #d97706; }
    .decay-explain {
      display: flex; justify-content: space-between;
      font-size: 10px; color: var(--color-text-muted); margin-top: 6px; padding: 0 4px;
    }
    .no-data {
      height: 420px; display: flex; align-items: center;
      justify-content: center; color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class DecayChartComponent implements OnChanges {
  private themeService = inject(ThemeService);
  private langService = inject(LanguageService);

  @Input() data: DecayHistoryResponse | null = null;

  chartOptions: EChartsOption = {};
  hasData = false;
  currentDecay = 0;
  currentCorr = 0;

  constructor() {
    effect(() => {
      this.themeService.isDark();
      this.langService.lang();
      if (this.hasData) this.buildChart();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.data && this.data.series.length > 0) {
      this.hasData = true;
      const last = this.data.series[this.data.series.length - 1];
      this.currentDecay = last.decay_value;
      this.currentCorr = last.avg_correlation;
      this.buildChart();
    }
  }

  private buildChart(): void {
    const c = getChartColors(this.themeService.isDark());
    const t = (s: string) => this.langService.translate(s);

    const series = this.data!.series;
    const dates = series.map(p => p.date);
    const decayVals = series.map(p => p.decay_value);
    const corrVals = series.map(p => p.avg_correlation);

    // Crisis areas
    const markAreas: [object, object][] = [];
    let start: string | null = null;
    for (const p of series) {
      if (p.regime === 4 && !start) start = p.date;
      if (p.regime !== 4 && start) {
        markAreas.push([{ xAxis: start }, { xAxis: p.date }]);
        start = null;
      }
    }
    if (start) markAreas.push([{ xAxis: start }, { xAxis: dates[dates.length - 1] }]);

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
        padding: [10, 14],
        textStyle: { color: c.tooltipText, fontSize: 12, fontFamily: 'Inter, sans-serif' },
        formatter: (params: any) => {
          const date = params[0]?.axisValue ?? '';
          let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
          for (const p of params) {
            const v = Number(p.value);
            const label = t(p.seriesName);
            const pct = (v * 100).toFixed(1);
            html += `<div style="color:${p.color};margin:3px 0;font-weight:500">
              ${label}: ${v.toFixed(4)} <span style="color:${c.textMuted}">(${pct}%)</span></div>`;
          }
          return html;
        }
      },
      legend: {
        bottom: 4,
        textStyle: { color: c.textMuted, fontSize: 11, fontFamily: 'Inter, sans-serif' },
        itemGap: 24,
        data: [t('decay_chart.legend_decay'), t('decay_chart.legend_corr')]
      },
      grid: { left: '6%', right: '6%', top: '4%', bottom: '13%', containLabel: true },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel, fontSize: 10, rotate: 30 },
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: 'value',
          min: 0, max: 1.0,
          axisLine: { show: false },
          axisLabel: {
            color: '#10b981', fontSize: 10,
            formatter: (v: number) => (v * 100).toFixed(0) + '%'
          },
          splitLine: { lineStyle: { color: c.splitLine, type: 'dashed' } },
        },
        {
          type: 'value',
          min: -0.2, max: 1.0,
          axisLine: { show: false },
          axisLabel: {
            color: '#06b6d4', fontSize: 10,
            formatter: (v: number) => v.toFixed(1)
          },
          splitLine: { show: false },
        }
      ],
      series: [
        {
          name: t('decay_chart.legend_decay'),
          type: 'line',
          yAxisIndex: 0,
          data: decayVals,
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
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: c.textMuted, type: 'dashed', width: 1 },
            label: {
              show: true, position: 'insideStartTop',
              formatter: t('decay_chart.threshold'),
              color: c.textMuted, fontSize: 9,
              fontFamily: 'JetBrains Mono, monospace',
            },
            data: [{ yAxis: 0.50 }]
          },
        },
        {
          name: t('decay_chart.legend_corr'),
          type: 'line',
          yAxisIndex: 1,
          data: corrVals,
          lineStyle: { color: '#0891b2', width: 2, type: 'dashed' },
          itemStyle: { color: '#0891b2' },
          symbol: 'none',
          smooth: 0.3,
        }
      ]
    };
  }
}
