import { Component, Input, OnChanges, SimpleChanges, effect, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, MarkLineComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { EChartsOption } from 'echarts';
import { DrawdownResponse } from '../../../core/models/analytics.model';
import { ThemeService } from '../../../core/services/theme.service';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { getChartColors } from '../../../core/utils/chart-colors';
import { CountUpDirective } from '../../directives/count-up.directive';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

@Component({
  selector: 'app-drawdown-gauge',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective, CountUpDirective, TranslatePipe],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="dd-wrapper" *ngIf="data && data.combined; else noData">
      <div class="dd-header">
        <div class="dd-big-value" [style.color]="getDdColor(data.combined.current_drawdown_pct)">
          <span [appCountUp]="data.combined.current_drawdown_pct"
                [countDecimals]="2" countSuffix="%"></span>
        </div>
        <div class="dd-meta">
          <span class="dd-days">{{ data.combined.days_since_peak }} {{ 'drawdown_gauge.days' | translate }}</span>
          <span class="dd-max">{{ 'drawdown_gauge.max' | translate }} {{ data.combined.max_drawdown_pct.toFixed(2) }}%</span>
        </div>
      </div>

      <div *ngIf="hasHistory" echarts [options]="chartOptions" [autoResize]="true"
           class="dd-chart"></div>
    </div>

    <ng-template #noData>
      <div class="no-data">{{ 'drawdown_gauge.waiting' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .dd-wrapper {
      display: flex; flex-direction: column; gap: 12px;
    }
    .dd-header {
      display: flex; align-items: flex-end; justify-content: space-between;
      padding: 0 4px;
    }
    .dd-big-value {
      font-size: 28px; font-weight: 800;
      font-family: var(--font-numbers, monospace);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
    }
    .dd-meta {
      display: flex; flex-direction: column; align-items: flex-end; gap: 2px;
    }
    .dd-days {
      font-size: 11px; color: var(--color-text-muted);
    }
    .dd-max {
      font-size: 11px; color: var(--color-text-muted);
      font-family: var(--font-numbers, monospace);
    }
    .dd-chart { height: 140px; width: 100%; }
    .no-data {
      text-align: center; padding: 40px;
      color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class DrawdownGaugeComponent implements OnChanges {
  private themeService = inject(ThemeService);
  private langService = inject(LanguageService);

  @Input() data: DrawdownResponse | null = null;

  chartOptions: EChartsOption = {};
  hasHistory = false;

  constructor() {
    effect(() => {
      this.themeService.isDark();
      this.langService.lang();
      if (this.hasHistory) this.buildChart();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.data?.history && this.data.history.length > 0) {
      this.hasHistory = true;
      this.buildChart();
    }
  }

  getDdColor(dd: number): string {
    const abs = Math.abs(dd);
    if (abs < 1) return '#10b981';
    if (abs < 3) return '#f59e0b';
    if (abs < 5) return '#f97316';
    return '#ef4444';
  }

  private buildChart(): void {
    const c = getChartColors(this.themeService.isDark());
    const t = (s: string) => this.langService.translate(s);
    const history = this.data!.history;
    const dates = history.map(h => h.date);
    const values = history.map(h => h.drawdown_pct);

    this.chartOptions = {
      backgroundColor: 'transparent',
      animation: true,
      animationDuration: 600,
      tooltip: {
        trigger: 'axis',
        backgroundColor: c.tooltipBg,
        borderColor: c.tooltipBorder,
        borderWidth: 1,
        borderRadius: 8,
        padding: [8, 12],
        textStyle: { color: c.tooltipText, fontSize: 11, fontFamily: 'monospace' },
        formatter: (params: any) => {
          const p = params[0];
          return `<b>${p.axisValue}</b><br/>Drawdown: <b style="color:${this.getDdColor(p.value)}">${p.value.toFixed(2)}%</b>`;
        }
      },
      grid: { left: '2%', right: '4%', top: '8%', bottom: '12%', containLabel: true },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: c.axisLine } },
        axisLabel: { color: c.axisLabel, fontSize: 9, rotate: 0,
          formatter: (v: string) => v.slice(5)
        },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisLabel: {
          color: c.axisLabel, fontSize: 9,
          formatter: (v: number) => v.toFixed(1) + '%'
        },
        splitLine: { lineStyle: { color: c.splitLine, type: 'dashed' } },
      },
      series: [{
        type: 'line',
        data: values,
        lineStyle: { color: '#ef4444', width: 2 },
        itemStyle: { color: '#ef4444' },
        symbol: 'none',
        smooth: 0.3,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(239, 68, 68, 0.20)' },
            { offset: 1, color: 'rgba(239, 68, 68, 0.02)' }
          ])
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: c.textMuted, type: 'dashed', width: 1 },
          label: {
            show: true, position: 'insideEndTop',
            formatter: 'Thesis -5.67%',
            color: c.textMuted, fontSize: 9,
          },
          data: [{ yAxis: -5.67 }]
        },
      }]
    };
  }
}
