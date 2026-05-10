import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import { TreemapChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { EChartsOption } from 'echarts';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { WeeklySignalResponse } from '../../../core/models/analytics.model';
import { RegimeStatus } from '../../../core/models/backtest.model';

echarts.use([TreemapChart, TooltipComponent, CanvasRenderer]);

const ETF_NAMES: Record<string, string> = {
  SPY: 'SPDR S&P 500 ETF', QQQ: 'Invesco QQQ Trust', IWM: 'iShares Russell 2000',
  MDY: 'SPDR S&P MidCap 400', DIA: 'SPDR Dow Jones', EFA: 'iShares MSCI EAFE',
  EEM: 'iShares MSCI Emerging Markets', XLB: 'Materials Select Sector',
  XLE: 'Energy Select Sector', XLF: 'Financial Select Sector',
  XLI: 'Industrial Select Sector', XLK: 'Technology Select Sector',
  XLP: 'Consumer Staples Select', XLU: 'Utilities Select Sector',
  XLV: 'Health Care Select Sector', XLY: 'Consumer Discretionary',
  IYR: 'iShares US Real Estate', VNQ: 'Vanguard Real Estate',
  SOXX: 'iShares Semiconductor', TLT: 'iShares 20+ Year Treasury',
  IEF: 'iShares 7-10 Year Treasury', SHY: 'iShares 1-3 Year Treasury',
  LQD: 'iShares Investment Grade Corporate', SH: 'ProShares Short S&P500',
  PSQ: 'ProShares Short QQQ', RWM: 'ProShares Short Russell2000',
  VIXY: 'ProShares VIX Short-Term', UUP: 'Invesco DB US Dollar',
  GLD: 'SPDR Gold Shares', SLV: 'iShares Silver Trust', FXE: 'Invesco CurrencyShares Euro',
  Cash: 'Liquidità',
};

interface AllocItem {
  name: string;
  value: number;
  itemStyle?: { color: string };
}

@Component({
  selector: 'app-allocation-treemap',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective, TranslatePipe],
  providers: [provideEchartsCore({ echarts })],
  template: `
    <div class="treemap-controls" *ngIf="availableFridays.length > 0">
      <select class="friday-select" (change)="onFridayChange($event)">
        <option *ngFor="let f of availableFridays" [value]="f" [selected]="f === selectedFriday">
          {{ f }}
        </option>
      </select>
    </div>
    <div *ngIf="allocations.length > 0; else noData"
         echarts [options]="chartOptions" [autoResize]="true"
         class="treemap-chart"></div>
    <ng-template #noData>
      <div class="no-data">{{ 'allocation.no_data' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .treemap-controls {
      margin-bottom: 8px;
    }
    .friday-select {
      padding: 4px 8px; font-size: 11px; font-weight: 600;
      border: 1px solid var(--color-border);
      border-radius: 6px; background: var(--color-surface);
      color: var(--color-text-secondary);
      font-family: var(--font-numbers, monospace);
      cursor: pointer; outline: none;
    }
    .friday-select:focus {
      border-color: var(--color-accent);
    }
    .treemap-chart { height: 240px; width: 100%; }
    .no-data {
      height: 180px; display: flex; align-items: center;
      justify-content: center; color: var(--color-text-muted);
      font-size: 12px;
    }
  `]
})
export class AllocationTreemapComponent implements OnChanges {
  private langService = inject(LanguageService);

  @Input() signals: WeeklySignalResponse | null = null;
  @Input() regime: RegimeStatus | null = null;
  @Output() fridayChanged = new EventEmitter<string>();

  chartOptions: EChartsOption = {};
  allocations: AllocItem[] = [];
  availableFridays: string[] = [];
  selectedFriday = '';

  private readonly COLORS = [
    '#059669', '#0891b2', '#3b82f6', '#6366f1', '#8b5cf6',
    '#d97706', '#0d9488', '#2563eb', '#7c3aed', '#dc2626',
    '#ea580c', '#65a30d', '#0369a1', '#4f46e5', '#be185d',
  ];

  constructor() {
    effect(() => {
      this.langService.lang();
      this.buildTreemap();
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (this.signals) {
      this.availableFridays = this.signals.available_fridays ?? [];
      this.selectedFriday = this.signals.friday_date ?? '';
    }
    this.buildTreemap();
  }

  onFridayChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.selectedFriday = val;
    this.fridayChanged.emit(val);
  }

  private buildTreemap(): void {
    const isCrisis = this.signals?.is_crisis ?? this.regime?.is_crisis ?? false;
    const t = (s: string) => this.langService.translate(s);

    if (isCrisis) {
      this.allocations = [
        { name: t('allocation.cash'), value: 80, itemStyle: { color: '#94a3b8' } },
        { name: 'SH', value: 5, itemStyle: { color: '#f87171' } },
        { name: 'PSQ', value: 5, itemStyle: { color: '#fb923c' } },
        { name: 'RWM', value: 5, itemStyle: { color: '#fbbf24' } },
        { name: 'VIXY', value: 5, itemStyle: { color: '#a78bfa' } },
      ];
    } else if (this.signals) {
      const active = this.signals.signals.filter(s => s.is_active);
      if (active.length === 0) {
        this.allocations = [{ name: t('allocation.cash'), value: 100, itemStyle: { color: '#94a3b8' } }];
      } else {
        const weight = 100 / active.length;
        const tickerMap = new Map<string, number>();
        for (const s of active) {
          const t = s.long_ticker;
          tickerMap.set(t, (tickerMap.get(t) ?? 0) + weight);
        }
        this.allocations = Array.from(tickerMap.entries()).map(([name, value], i) => ({
          name,
          value: Math.round(value * 10) / 10,
          itemStyle: { color: this.COLORS[i % this.COLORS.length] }
        })).sort((a, b) => b.value - a.value);
      }
    } else {
      this.allocations = [];
      return;
    }

    this.chartOptions = {
      tooltip: {
        formatter: (info: any) => {
          const ticker = info.name;
          const fullName = ETF_NAMES[ticker] || ticker;
          const weight = info.value ? (info.value).toFixed(1) : '0';
          return `<div style="font-size:13px;line-height:1.6">
            <b>${ticker}</b> — ${fullName}<br/>
            ${t('allocation.weight')}: <b>${weight}%</b>
          </div>`;
        }
      },
      series: [{
        type: 'treemap',
        left: 0, top: 0, right: 0, bottom: 0,
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: {
          show: true,
          formatter: '{b}\n{c}%',
          fontSize: 11,
          fontWeight: 600,
          fontFamily: 'Montserrat, sans-serif',
          color: '#fff',
          textShadowColor: 'rgba(0,0,0,0.3)',
          textShadowBlur: 2,
        },
        itemStyle: {
          borderColor: '#1a1d27',
          borderWidth: 2,
          gapWidth: 1,
        },
        data: this.allocations,
      }]
    };
  }
}
